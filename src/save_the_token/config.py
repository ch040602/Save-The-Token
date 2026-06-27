from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from .models import ConfigFinding, ConfigSource, McpServerConfig, ScanResult


def discover_config_sources(root: Path, home: Path | None = None) -> list[ConfigSource]:
    """Discover supported MCP config files without executing any server."""
    home = home or Path.home()
    candidates = [
        ConfigSource(home / ".codex" / "config.toml", "codex", "user"),
        ConfigSource(root / ".codex" / "config.toml", "codex", "project"),
        ConfigSource(root / ".vscode" / "mcp.json", "vscode", "project"),
        ConfigSource(root / ".cursor" / "mcp.json", "cursor", "project"),
        ConfigSource(root / ".mcp.json", "claude-code", "project"),
        ConfigSource(home / ".claude.json", "claude-code", "user-local"),
        ConfigSource(
            home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
            "claude-desktop",
            "user",
        ),
        ConfigSource(
            home
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json",
            "claude-desktop",
            "user",
        ),
    ]
    return [source for source in candidates if source.path.exists()]


def scan_configs(root: Path, home: Path | None = None) -> ScanResult:
    root = root.resolve()
    sources = discover_config_sources(root, home)
    servers: list[McpServerConfig] = []
    findings: list[ConfigFinding] = []
    for source in sources:
        parsed, parse_findings = _load_source(source)
        findings.extend(parse_findings)
        if parsed is None:
            continue
        source_servers, lint_findings = _extract_servers(source, parsed, root)
        servers.extend(source_servers)
        findings.extend(lint_findings)
    return ScanResult(tuple(sources), tuple(servers), tuple(findings))


def _load_source(
    source: ConfigSource,
) -> tuple[dict[str, Any] | None, list[ConfigFinding]]:
    try:
        if source.path.suffix == ".toml":
            return tomllib.loads(source.path.read_text(encoding="utf-8")), []
        return json.loads(source.path.read_text(encoding="utf-8")), []
    except Exception as exc:  # noqa: BLE001 - diagnostic should preserve parse failure.
        return None, [
            ConfigFinding(
                severity="error",
                code="config_parse_failed",
                message=str(exc),
                source=str(source.path),
            )
        ]


def _extract_servers(
    source: ConfigSource, parsed: dict[str, Any], root: Path
) -> tuple[list[McpServerConfig], list[ConfigFinding]]:
    if source.client == "codex":
        return _extract_codex_servers(source, parsed)
    if source.client == "claude-code":
        return _extract_claude_code_servers(source, parsed, root)
    return _extract_mcp_json_servers(source, parsed)


def _extract_codex_servers(
    source: ConfigSource, parsed: dict[str, Any]
) -> tuple[list[McpServerConfig], list[ConfigFinding]]:
    table = parsed.get("mcp_servers", {})
    if not isinstance(table, dict):
        return [], [
            ConfigFinding(
                "error",
                "mcp_servers_not_table",
                "`mcp_servers` must be a TOML table.",
                str(source.path),
            )
        ]
    servers = [
        _server_from_mapping(source, server_id, value)
        for server_id, value in table.items()
    ]
    findings = _lint_servers(servers)
    return servers, findings


def _extract_mcp_json_servers(
    source: ConfigSource, parsed: dict[str, Any]
) -> tuple[list[McpServerConfig], list[ConfigFinding]]:
    table = parsed.get("mcpServers", {})
    if not isinstance(table, dict):
        return [], [
            ConfigFinding(
                "error",
                "mcpServers_not_object",
                "`mcpServers` must be a JSON object.",
                str(source.path),
            )
        ]
    servers = [
        _server_from_mapping(source, server_id, value)
        for server_id, value in table.items()
    ]
    findings = _lint_servers(servers)
    return servers, findings


def _extract_claude_code_servers(
    source: ConfigSource, parsed: dict[str, Any], root: Path
) -> tuple[list[McpServerConfig], list[ConfigFinding]]:
    if source.path.name == ".mcp.json":
        return _extract_mcp_json_servers(source, parsed)

    servers: list[McpServerConfig] = []
    findings: list[ConfigFinding] = []
    user_table = parsed.get("mcpServers", {})
    if isinstance(user_table, dict):
        user_source = ConfigSource(source.path, source.client, "user")
        servers.extend(
            _server_from_mapping(user_source, server_id, value)
            for server_id, value in user_table.items()
        )
    elif "mcpServers" in parsed:
        findings.append(
            ConfigFinding(
                "error",
                "mcpServers_not_object",
                "`mcpServers` must be a JSON object.",
                str(source.path),
            )
        )

    projects = parsed.get("projects", {})
    if isinstance(projects, dict):
        project_entry = _project_entry(projects, root)
        if isinstance(project_entry, dict):
            local_table = project_entry.get("mcpServers", {})
            if isinstance(local_table, dict):
                local_source = ConfigSource(source.path, source.client, "local")
                servers.extend(
                    _server_from_mapping(local_source, server_id, value)
                    for server_id, value in local_table.items()
                )
            elif "mcpServers" in project_entry:
                findings.append(
                    ConfigFinding(
                        "error",
                        "mcpServers_not_object",
                        "`projects[<root>].mcpServers` must be a JSON object.",
                        str(source.path),
                    )
                )
    elif "projects" in parsed:
        findings.append(
            ConfigFinding(
                "error",
                "projects_not_object",
                "`projects` must be a JSON object.",
                str(source.path),
            )
        )

    findings.extend(_lint_servers(servers))
    return servers, findings


def _project_entry(projects: dict[str, Any], root: Path) -> Any:
    root_strings = {str(root), str(root.resolve())}
    for key, value in projects.items():
        try:
            if str(Path(key).resolve()) in root_strings:
                return value
        except OSError:
            if key in root_strings:
                return value
    return None


def _server_from_mapping(
    source: ConfigSource, server_id: str, value: Any
) -> McpServerConfig:
    mapping = value if isinstance(value, dict) else {}
    args = mapping.get("args", ())
    enabled_tools = mapping.get("enabled_tools", mapping.get("enabledTools", ()))
    disabled_tools = mapping.get("disabled_tools", mapping.get("disabledTools", ()))
    return McpServerConfig(
        source=source,
        server_id=server_id,
        command=_string_or_none(mapping.get("command")),
        args=tuple(str(arg) for arg in args) if isinstance(args, list) else (),
        url=_string_or_none(mapping.get("url")),
        cwd=_string_or_none(mapping.get("cwd")),
        env={str(k): str(v) for k, v in mapping.get("env", {}).items()}
        if isinstance(mapping.get("env", {}), dict)
        else {},
        headers={str(k): str(v) for k, v in mapping.get("headers", {}).items()}
        if isinstance(mapping.get("headers", {}), dict)
        else {},
        enabled=bool(mapping.get("enabled", True)),
        enabled_tools=tuple(str(tool) for tool in enabled_tools)
        if isinstance(enabled_tools, list)
        else (),
        disabled_tools=tuple(str(tool) for tool in disabled_tools)
        if isinstance(disabled_tools, list)
        else (),
        raw=mapping,
    )


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _lint_servers(servers: list[McpServerConfig]) -> list[ConfigFinding]:
    findings: list[ConfigFinding] = []
    for server in servers:
        source = str(server.source.path)
        if not server.command and not server.url:
            findings.append(
                ConfigFinding(
                    "error",
                    "server_missing_transport",
                    "MCP server must define either `command` or `url`.",
                    source,
                    server.server_id,
                )
            )
        if server.command and server.url:
            findings.append(
                ConfigFinding(
                    "warning",
                    "server_multiple_transports",
                    "MCP server defines both `command` and `url`; clients may not support both.",
                    source,
                    server.server_id,
                )
            )
        if server.enabled_tools and server.disabled_tools:
            overlap = sorted(
                set(server.enabled_tools).intersection(server.disabled_tools)
            )
            if overlap:
                findings.append(
                    ConfigFinding(
                        "warning",
                        "tool_allow_deny_overlap",
                        f"Tools appear in both allow and deny lists: {', '.join(overlap)}",
                        source,
                        server.server_id,
                    )
                )
        for name, value in server.headers.items():
            if not _is_safe_header(name, value):
                findings.append(
                    ConfigFinding(
                        "error",
                        "unsafe_http_header",
                        f"HTTP header `{name}` contains unsafe characters.",
                        source,
                        server.server_id,
                    )
                )
    return findings


def _is_safe_header(name: str, value: str) -> bool:
    if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
        return False
    return bool(re.fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", name))
