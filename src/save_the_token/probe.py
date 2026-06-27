from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from itertools import count
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import McpServerConfig, ProbeResult, ToolSchema

PROTOCOL_VERSION = "2025-11-25"


class StdioMcpProbe:
    """Small stdio MCP probe for health checks and tool inventory."""

    def __init__(self, timeout_sec: float = 5.0) -> None:
        self.timeout_sec = timeout_sec
        self._ids = count(1)

    def probe(self, server: McpServerConfig) -> ProbeResult:
        if not server.command:
            return ProbeResult(
                server=server,
                ok=False,
                error="Only stdio `command` servers can be probed.",
            )

        env = os.environ.copy()
        env.update(server.env)
        try:
            process = subprocess.Popen(
                [server.command, *server.args],
                cwd=server.cwd or None,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001 - preserve startup diagnostics.
            return ProbeResult(
                server=server, ok=False, error=f"Failed to start server: {exc}"
            )

        try:
            initialize = self._request(
                process,
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "Save-The-Token", "version": "0.1.0"},
                },
            )
            if "error" in initialize:
                return self._finish(
                    process, server, False, False, error=json.dumps(initialize["error"])
                )
            self._notify(process, "notifications/initialized")
            tools_response = self._request(process, "tools/list", {})
            if "error" in tools_response:
                return self._finish(
                    process,
                    server,
                    False,
                    True,
                    error=json.dumps(tools_response["error"]),
                )
            tools = _parse_tools(tools_response.get("result", {}).get("tools", []))
            return self._finish(process, server, True, True, tools=tools)
        except TimeoutError as exc:
            return self._finish(process, server, False, False, error=str(exc))
        except Exception as exc:  # noqa: BLE001 - diagnostic command should not crash.
            return self._finish(
                process, server, False, False, error=f"Probe failed: {exc}"
            )

    def _request(
        self, process: subprocess.Popen[str], method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        request_id = next(self._ids)
        self._write(
            process,
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
        )
        deadline = time.monotonic() + self.timeout_sec
        while time.monotonic() < deadline:
            line = _readline_with_timeout(
                process, max(0.01, deadline - time.monotonic())
            )
            if not line:
                if process.poll() is not None:
                    raise RuntimeError(f"Server exited with code {process.returncode}")
                continue
            message = json.loads(line)
            if message.get("id") == request_id:
                return message
        raise TimeoutError(f"Timed out waiting for {method} response")

    def _notify(self, process: subprocess.Popen[str], method: str) -> None:
        self._write(process, {"jsonrpc": "2.0", "method": method})

    def _write(self, process: subprocess.Popen[str], payload: dict[str, Any]) -> None:
        if process.stdin is None:
            raise RuntimeError("Server stdin is not available")
        process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        process.stdin.flush()

    def _finish(
        self,
        process: subprocess.Popen[str],
        server: McpServerConfig,
        ok: bool,
        initialized: bool,
        tools: tuple[ToolSchema, ...] = (),
        error: str | None = None,
    ) -> ProbeResult:
        stderr = ""
        try:
            process.terminate()
            try:
                _, stderr = process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                _, stderr = process.communicate(timeout=1)
        except Exception:
            stderr = ""
        return ProbeResult(
            server=server,
            ok=ok,
            initialized=initialized,
            tools=tools,
            error=error,
            stderr=stderr or "",
        )


class HttpMcpProbe:
    """Streamable HTTP MCP probe for remote URL-based servers."""

    def __init__(self, timeout_sec: float = 5.0) -> None:
        self.timeout_sec = timeout_sec
        self._ids = count(1)

    def probe(self, server: McpServerConfig) -> ProbeResult:
        if not server.url:
            return ProbeResult(
                server=server, ok=False, error="Only HTTP `url` servers can be probed."
            )

        session_id: str | None = None
        try:
            initialize, session_id = self._request(
                server,
                server.url,
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "Save-The-Token", "version": "0.1.0"},
                },
                session_id,
            )
            if "error" in initialize:
                return ProbeResult(
                    server=server,
                    ok=False,
                    initialized=False,
                    error=json.dumps(initialize["error"]),
                )
            self._notify(server, server.url, "notifications/initialized", session_id)
            tools_response, _ = self._request(
                server, server.url, "tools/list", {}, session_id
            )
            if "error" in tools_response:
                return ProbeResult(
                    server=server,
                    ok=False,
                    initialized=True,
                    error=json.dumps(tools_response["error"]),
                )
            tools = _parse_tools(tools_response.get("result", {}).get("tools", []))
            return ProbeResult(server=server, ok=True, initialized=True, tools=tools)
        except TimeoutError as exc:
            return ProbeResult(
                server=server, ok=False, initialized=False, error=str(exc)
            )
        except Exception as exc:  # noqa: BLE001 - diagnostic command should not crash.
            return ProbeResult(
                server=server,
                ok=False,
                initialized=False,
                error=f"HTTP probe failed: {exc}",
            )

    def _request(
        self,
        server: McpServerConfig,
        url: str,
        method: str,
        params: dict[str, Any],
        session_id: str | None,
    ) -> tuple[dict[str, Any], str | None]:
        request_id = next(self._ids)
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        response = self._post(server, url, payload, session_id)
        message = response["message"]
        if message.get("id") != request_id:
            raise RuntimeError(f"Unexpected response id for {method}")
        return message, response["session_id"] or session_id

    def _notify(
        self, server: McpServerConfig, url: str, method: str, session_id: str | None
    ) -> None:
        self._post(
            server,
            url,
            {"jsonrpc": "2.0", "method": method},
            session_id,
            expect_body=False,
        )

    def _post(
        self,
        server: McpServerConfig,
        url: str,
        payload: dict[str, Any],
        session_id: str | None,
        expect_body: bool = True,
    ) -> dict[str, Any]:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = _safe_custom_headers(server.headers)
        headers.update(
            {
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "MCP-Protocol-Version": PROTOCOL_VERSION,
            }
        )
        if session_id:
            headers["MCP-Session-Id"] = session_id
        request = Request(url, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout_sec) as response:  # noqa: S310 - user-configured diagnostic URL.
                response_body = response.read().decode("utf-8")
                new_session_id = response.headers.get("MCP-Session-Id")
                if not expect_body:
                    return {"message": {}, "session_id": new_session_id}
                content_type = response.headers.get("Content-Type", "")
                if "text/event-stream" in content_type:
                    return {
                        "message": _parse_sse_response(response_body),
                        "session_id": new_session_id,
                    }
                return {
                    "message": json.loads(response_body),
                    "session_id": new_session_id,
                }
        except TimeoutError:
            raise
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc


def _parse_tools(raw_tools: Any) -> tuple[ToolSchema, ...]:
    if not isinstance(raw_tools, list):
        return ()
    tools: list[ToolSchema] = []
    for item in raw_tools:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        input_schema = item.get("inputSchema", {})
        tools.append(
            ToolSchema(
                name=name,
                description=item.get("description", "")
                if isinstance(item.get("description"), str)
                else "",
                input_schema=input_schema if isinstance(input_schema, dict) else {},
                output_schema=item.get("outputSchema")
                if isinstance(item.get("outputSchema"), dict)
                else None,
                raw=item,
            )
        )
    return tuple(tools)


def _readline_with_timeout(process: subprocess.Popen[str], timeout_sec: float) -> str:
    stdout = process.stdout
    if stdout is None:
        return ""
    output: queue.Queue[str] = queue.Queue(maxsize=1)

    def read() -> None:
        try:
            output.put(stdout.readline())
        except Exception:
            output.put("")

    thread = threading.Thread(target=read, daemon=True)
    thread.start()
    try:
        return output.get(timeout=timeout_sec)
    except queue.Empty:
        return ""


def _parse_sse_response(body: str) -> dict[str, Any]:
    for event in body.split("\n\n"):
        data_lines = [
            line.removeprefix("data:").strip()
            for line in event.splitlines()
            if line.startswith("data:")
        ]
        if not data_lines:
            continue
        data = "\n".join(data_lines)
        if not data:
            continue
        message = json.loads(data)
        if isinstance(message, dict) and "id" in message:
            return message
    raise RuntimeError("SSE response did not contain a JSON-RPC response")


def _safe_custom_headers(headers: dict[str, str]) -> dict[str, str]:
    reserved = {
        "accept",
        "content-type",
        "mcp-protocol-version",
        "mcp-session-id",
    }
    safe: dict[str, str] = {}
    for name, value in headers.items():
        normalized = name.lower()
        if normalized in reserved:
            continue
        if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
            continue
        safe[name] = value
    return safe
