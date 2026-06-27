from __future__ import annotations

import contextlib
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from save_the_token.cli import main
from save_the_token.evidence_cache import cache_entry, fingerprint_file


class CliTests(unittest.TestCase):
    def test_tools_cli_passes_task_query_to_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            server = _write_fake_server(root)
            (root / ".codex").mkdir()
            (root / ".codex" / "config.toml").write_text(
                textwrap.dedent(
                    f"""
                    [mcp_servers.github]
                    command = {json.dumps(sys.executable)}
                    args = ["-u", {json.dumps(str(server))}]
                    """
                ).strip(),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "tools",
                        "--root",
                        str(root),
                        "--home",
                        str(root / "home"),
                        "--timeout",
                        "2",
                        "--budget",
                        "20",
                        "--task",
                        "create issue",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        report = payload["budget_reports"][0]
        issue_item = next(
            item for item in report["items"] if item["name"] == "issues_create"
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["recommended_enabled_tools"], ["issues_create"])
        self.assertEqual(issue_item["matched_terms"], ["create", "issue"])
        self.assertGreater(issue_item["relevance_score"], 0)

    def test_tools_cli_probes_url_mcp_server(self) -> None:
        handler = _fake_http_handler(expected_authorization="Bearer secret-token")
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / ".vscode").mkdir()
                (root / ".vscode" / "mcp.json").write_text(
                    json.dumps(
                        {
                            "mcpServers": {
                                "remote": {
                                    "url": f"http://127.0.0.1:{httpd.server_port}/mcp",
                                    "headers": {
                                        "Authorization": "Bearer secret-token",
                                    },
                                }
                            }
                        }
                    ),
                    encoding="utf-8",
                )

                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "tools",
                            "--root",
                            str(root),
                            "--home",
                            str(root / "home"),
                            "--timeout",
                            "2",
                            "--budget",
                            "100",
                        ]
                    )
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

        payload = json.loads(stdout.getvalue())
        report = payload["budget_reports"][0]
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["server_id"], "remote")
        self.assertEqual(report["total_tools"], 1)
        self.assertEqual(report["recommended_enabled_tools"], ["remote_search"])

    def test_slim_cli_prints_json_snippet_for_mcp_json_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            server = _write_fake_server(root)
            (root / ".vscode").mkdir()
            (root / ".vscode" / "mcp.json").write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "github": {
                                "command": sys.executable,
                                "args": ["-u", str(server)],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "slim",
                        "--root",
                        str(root),
                        "--home",
                        str(root / "home"),
                        "--timeout",
                        "2",
                        "--budget",
                        "20",
                        "--task",
                        "create issue",
                    ]
                )

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn('"mcpServers"', output)
        self.assertIn('"enabledTools"', output)
        self.assertIn('"issues_create"', output)

    def test_scan_cli_redacts_header_env_and_raw_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".vscode").mkdir()
            (root / ".vscode" / "mcp.json").write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "remote": {
                                "url": "https://example.com/mcp",
                                "headers": {"Authorization": "Bearer secret-token"},
                                "env": {"API_TOKEN": "secret-token"},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    ["scan", "--root", str(root), "--home", str(root / "home")]
                )

        output = stdout.getvalue()
        payload = json.loads(output)
        server = payload["servers"][0]
        self.assertEqual(exit_code, 0)
        self.assertNotIn("secret-token", output)
        self.assertEqual(server["headers"]["Authorization"], "<redacted>")
        self.assertEqual(server["env"]["API_TOKEN"], "<redacted>")
        self.assertEqual(server["raw"]["headers"]["Authorization"], "<redacted>")

    def test_scan_cli_reports_evidence_cache_hits_and_misses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".codex").mkdir()
            config_path = root / ".codex" / "config.toml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    [mcp_servers.github]
                    command = "gh"
                    """
                ).strip(),
                encoding="utf-8",
            )
            agents_path = root / "AGENTS.md"
            agents_path.write_text(
                "# Policy\nRun tests before final.\n", encoding="utf-8"
            )
            cache_path = root / "cache.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "entries": [
                            cache_entry(
                                fingerprint_file(config_path, kind="client-config"),
                                "cached config summary",
                            )
                        ]
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "scan",
                        "--root",
                        str(root),
                        "--home",
                        str(root / "home"),
                        "--cache",
                        str(cache_path),
                    ]
                )

        payload = json.loads(stdout.getvalue())
        statuses = payload["evidence_cache"]
        config_status = next(
            item for item in statuses if item["fingerprint"]["kind"] == "client-config"
        )
        instruction_status = next(
            item for item in statuses if item["fingerprint"]["kind"] == "instructions"
        )
        self.assertEqual(exit_code, 0)
        self.assertTrue(config_status["cache_hit"])
        self.assertEqual(config_status["cached_summary"], "cached config summary")
        self.assertFalse(instruction_status["cache_hit"])

    def test_report_cli_marks_cache_status_without_hiding_misses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            server = _write_fake_server(root)
            (root / ".codex").mkdir()
            config_path = root / ".codex" / "config.toml"
            config_path.write_text(
                textwrap.dedent(
                    f"""
                    [mcp_servers.github]
                    command = {json.dumps(sys.executable)}
                    args = ["-u", {json.dumps(str(server))}]
                    """
                ).strip(),
                encoding="utf-8",
            )
            cache_path = root / "cache.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "entries": [
                            cache_entry(
                                fingerprint_file(config_path, kind="client-config"),
                                "cached config summary",
                            )
                        ]
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "report",
                        "--root",
                        str(root),
                        "--home",
                        str(root / "home"),
                        "--timeout",
                        "2",
                        "--cache",
                        str(cache_path),
                    ]
                )

        payload = json.loads(stdout.getvalue())
        statuses = payload["evidence_cache"]
        self.assertEqual(exit_code, 0)
        self.assertTrue(any(item["cache_hit"] for item in statuses))
        self.assertTrue(any(not item["cache_hit"] for item in statuses))
        self.assertTrue(
            any(item["fingerprint"]["kind"] == "tools" for item in statuses)
        )


def _write_fake_server(root: Path) -> Path:
    path = root / "fake_mcp_server.py"
    path.write_text(
        textwrap.dedent(
            """
            import json
            import sys

            for line in sys.stdin:
                message = json.loads(line)
                method = message.get("method")
                if method == "initialize":
                    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}}}), flush=True)
                elif method == "notifications/initialized":
                    continue
                elif method == "tools/list":
                    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"tools": [
                        {"name": "repo_status", "description": "Show repository status", "inputSchema": {"type": "object"}},
                        {"name": "issues_create", "description": "Create a GitHub issue", "inputSchema": {"type": "object"}},
                        {"name": "pulls_merge", "description": "Merge a pull request", "inputSchema": {"type": "object"}}
                    ]}}), flush=True)
            """
        ).strip(),
        encoding="utf-8",
    )
    return path


def _fake_http_handler(expected_authorization: str | None = None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_POST(self) -> None:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length))
            method = payload.get("method")
            if method == "initialize":
                self._json(
                    {
                        "jsonrpc": "2.0",
                        "id": payload["id"],
                        "result": {
                            "protocolVersion": "2025-11-25",
                            "capabilities": {"tools": {}},
                        },
                    },
                    session_id="session-123",
                )
                return
            if method == "notifications/initialized":
                self.send_response(202)
                self.end_headers()
                return
            if method == "tools/list":
                if (
                    expected_authorization
                    and self.headers.get("Authorization") != expected_authorization
                ):
                    self.send_response(401)
                    self.end_headers()
                    return
                self._json(
                    {
                        "jsonrpc": "2.0",
                        "id": payload["id"],
                        "result": {
                            "tools": [
                                {
                                    "name": "remote_search",
                                    "description": "Search remote data",
                                    "inputSchema": {"type": "object"},
                                }
                            ]
                        },
                    }
                )
                return
            self.send_response(404)
            self.end_headers()

        def _json(
            self, payload: dict[str, object], session_id: str | None = None
        ) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if session_id:
                self.send_header("MCP-Session-Id", session_id)
            self.end_headers()
            self.wfile.write(data)

    return Handler


if __name__ == "__main__":
    unittest.main()
