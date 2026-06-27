from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from save_the_token.budget import analyze_tool_budget
from save_the_token.cli import main
from save_the_token.models import ConfigSource, McpServerConfig, ToolSchema
from save_the_token.schema_digest import digest_tool_schemas


class SchemaDigestTests(unittest.TestCase):
    def test_digest_summarizes_required_inputs_risks_and_savings(self) -> None:
        server = _server("github")
        tools = (
            ToolSchema(
                name="issues_delete",
                description="Delete a GitHub issue with auth token",
                input_schema={
                    "type": "object",
                    "required": ["issue_number", "token"],
                    "properties": {
                        "issue_number": {"type": "integer"},
                        "token": {"type": "string"},
                        "body": {
                            "type": "string",
                            "description": "long optional body" * 80,
                        },
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                },
            ),
        )
        budget = analyze_tool_budget(
            server, tools, budget_tokens=100, task_query="delete issue"
        )

        digest = digest_tool_schemas(server, tools, budget)

        self.assertGreater(digest.total_full_schema_tokens, digest.total_digest_tokens)
        self.assertGreater(digest.saved_tokens, 0)
        item = digest.items[0]
        self.assertEqual(item.name, "issues_delete")
        self.assertEqual(item.required_inputs, ("issue_number", "token"))
        self.assertIn("destructive", item.risk_markers)
        self.assertIn("auth", item.risk_markers)
        self.assertIn("issue", item.matched_terms)
        self.assertTrue(item.full_schema_ref.endswith("/issues_delete/schema"))
        self.assertTrue(item.missing_details)

    def test_tools_cli_emits_schema_digest_without_breaking_routing(self) -> None:
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
                        "40",
                        "--task",
                        "delete issue",
                        "--schema-digest",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        report = payload["budget_reports"][0]
        digest = payload["schema_digests"][0]
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["recommended_enabled_tools"], ["issues_delete"])
        self.assertGreater(digest["saved_tokens"], 0)
        self.assertEqual(digest["items"][0]["name"], "issues_delete")
        self.assertIn("issue_number", digest["items"][0]["required_inputs"])

    def test_report_cli_emits_schema_digest_claim_and_payload(self) -> None:
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
                        "report",
                        "--root",
                        str(root),
                        "--home",
                        str(root / "home"),
                        "--timeout",
                        "2",
                        "--budget",
                        "80",
                        "--task",
                        "delete issue",
                        "--schema-digest",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertIn("tool_schema_digests", payload)
        self.assertEqual(
            payload["tool_schema_digests"][0]["server"]["server_id"], "github"
        )
        self.assertTrue(
            any("Tool schema digest" in claim["text"] for claim in payload["claims"])
        )


def _server(server_id: str) -> McpServerConfig:
    return McpServerConfig(
        source=ConfigSource(Path("config.toml"), "codex", "project"),
        server_id=server_id,
        command="fake",
    )


def _write_fake_server(root: Path) -> Path:
    server = root / "fake_mcp_server.py"
    server.write_text(
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
                        {"name": "issues_delete", "description": "Delete a GitHub issue", "inputSchema": {"type": "object", "required": ["issue_number"], "properties": {"issue_number": {"type": "integer"}, "body": {"type": "string", "description": "x" * 400}}}},
                        {"name": "repo_status", "description": "Show repository status", "inputSchema": {"type": "object"}}
                    ]}}), flush=True)
            """
        ).strip(),
        encoding="utf-8",
    )
    return server


if __name__ == "__main__":
    unittest.main()
