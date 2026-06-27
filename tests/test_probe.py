from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from save_the_token.models import ConfigSource, McpServerConfig
from save_the_token.probe import HttpMcpProbe, StdioMcpProbe


class ProbeTests(unittest.TestCase):
    def test_probe_collects_tools_from_fake_stdio_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server = _write_fake_server(Path(tmp))
            config = McpServerConfig(
                source=ConfigSource(Path(tmp) / "config.toml", "codex", "project"),
                server_id="fake",
                command=sys.executable,
                args=("-u", str(server)),
            )

            result = StdioMcpProbe(timeout_sec=2).probe(config)

            self.assertTrue(result.ok, result.error)
            self.assertTrue(result.initialized)
            self.assertEqual([tool.name for tool in result.tools], ["alpha", "beta"])

    def test_probe_reports_startup_failure(self) -> None:
        config = McpServerConfig(
            source=ConfigSource(Path("missing.toml"), "codex", "project"),
            server_id="missing",
            command="definitely-not-a-command",
        )

        result = StdioMcpProbe(timeout_sec=0.2).probe(config)

        self.assertFalse(result.ok)
        self.assertIn("Failed to start server", result.error or "")

    def test_probe_times_out_when_server_does_not_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server = Path(tmp) / "hang.py"
            server.write_text("import time\ntime.sleep(10)\n", encoding="utf-8")
            config = McpServerConfig(
                source=ConfigSource(Path(tmp) / "config.toml", "codex", "project"),
                server_id="hang",
                command=sys.executable,
                args=("-u", str(server)),
            )

            result = StdioMcpProbe(timeout_sec=0.1).probe(config)

            self.assertFalse(result.ok)
            self.assertIn("Timed out", result.error or "")

    def test_http_probe_collects_tools_and_preserves_session_headers(self) -> None:
        handler = _fake_http_handler()
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{httpd.server_port}/mcp"
            config = McpServerConfig(
                source=ConfigSource(Path("mcp.json"), "vscode", "project"),
                server_id="remote",
                url=url,
            )

            result = HttpMcpProbe(timeout_sec=2).probe(config)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

        self.assertTrue(result.ok, result.error)
        self.assertTrue(result.initialized)
        self.assertEqual([tool.name for tool in result.tools], ["remote_search"])
        self.assertIn(("tools/list", "session-123", "2025-11-25"), handler.requests)

    def test_http_probe_parses_sse_tool_response(self) -> None:
        handler = _fake_http_handler(sse_tools=True)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{httpd.server_port}/mcp"
            config = McpServerConfig(
                source=ConfigSource(Path("mcp.json"), "vscode", "project"),
                server_id="remote",
                url=url,
            )

            result = HttpMcpProbe(timeout_sec=2).probe(config)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

        self.assertTrue(result.ok, result.error)
        self.assertEqual([tool.name for tool in result.tools], ["remote_search"])


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
                        {"name": "alpha", "description": "Alpha tool", "inputSchema": {"type": "object"}},
                        {"name": "beta", "description": "Beta tool", "inputSchema": {"type": "object"}}
                    ]}}), flush=True)
            """
        ).strip(),
        encoding="utf-8",
    )
    return path


def _fake_http_handler(sse_tools: bool = False):
    class Handler(BaseHTTPRequestHandler):
        requests: list[tuple[str, str | None, str | None]] = []

        def log_message(self, format: str, *args: object) -> None:
            return

        def do_POST(self) -> None:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length))
            method = payload.get("method")
            self.__class__.requests.append(
                (
                    method,
                    self.headers.get("MCP-Session-Id"),
                    self.headers.get("MCP-Protocol-Version"),
                )
            )
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
                if self.headers.get("MCP-Session-Id") != "session-123":
                    self.send_response(400)
                    self.end_headers()
                    return
                response = {
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
                if sse_tools:
                    self._sse(response)
                else:
                    self._json(response)
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

        def _sse(self, payload: dict[str, object]) -> None:
            data = f"event: message\ndata: {json.dumps(payload)}\n\n".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


if __name__ == "__main__":
    unittest.main()
