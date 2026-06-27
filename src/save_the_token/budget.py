from __future__ import annotations

import json
import re
from typing import Any

from .models import McpServerConfig, ToolBudgetItem, ToolBudgetReport, ToolSchema


def analyze_tool_budget(
    server: McpServerConfig,
    tools: tuple[ToolSchema, ...],
    budget_tokens: int = 8000,
    task_query: str | None = None,
) -> ToolBudgetReport:
    query_terms = _tokenize(task_query or "")
    items = tuple(_budget_item(tool, query_terms) for tool in tools)
    total_schema_chars = sum(item.schema_chars for item in items)
    estimated_tokens = _estimate_tokens(total_schema_chars)
    recommended = _recommend_tools(server, items, budget_tokens, task_query)
    client_snippet_format, client_snippet = client_enabled_tools_snippet(
        server, recommended
    )
    return ToolBudgetReport(
        server=server,
        total_tools=len(tools),
        total_schema_chars=total_schema_chars,
        estimated_tokens=estimated_tokens,
        budget_tokens=budget_tokens,
        over_budget=estimated_tokens > budget_tokens,
        items=items,
        recommended_enabled_tools=recommended,
        codex_toml_snippet=codex_enabled_tools_snippet(server.server_id, recommended),
        client_snippet_format=client_snippet_format,
        client_snippet=client_snippet,
    )


def codex_enabled_tools_snippet(server_id: str, enabled_tools: tuple[str, ...]) -> str:
    tools = ", ".join(json.dumps(tool) for tool in enabled_tools)
    return f"[mcp_servers.{_toml_key(server_id)}]\nenabled_tools = [{tools}]\n"


def client_enabled_tools_snippet(
    server: McpServerConfig, enabled_tools: tuple[str, ...]
) -> tuple[str, str]:
    if server.source.client in {"vscode", "cursor"}:
        return "json", json.dumps(
            {
                "mcpServers": {
                    server.server_id: {
                        "enabledTools": list(enabled_tools),
                    }
                }
            },
            indent=2,
            ensure_ascii=False,
        )
    if server.source.client in {"claude-code", "claude-desktop"}:
        return (
            "deferred",
            "# Claude MCP enabled-tools snippet is deferred: official Claude MCP docs do not document an enabledTools allowlist field for this config surface.\n",
        )
    return "toml", codex_enabled_tools_snippet(server.server_id, enabled_tools)


def _budget_item(tool: ToolSchema, query_terms: frozenset[str]) -> ToolBudgetItem:
    compact = json.dumps(
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.input_schema,
            "outputSchema": tool.output_schema,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    tool_terms = _tool_terms(tool)
    matched_terms = tuple(sorted(query_terms & tool_terms))
    return ToolBudgetItem(
        name=tool.name,
        schema_chars=len(compact),
        estimated_tokens=_estimate_tokens(len(compact)),
        relevance_score=_relevance_score(tool, matched_terms),
        matched_terms=matched_terms,
    )


def _estimate_tokens(chars: int) -> int:
    return max(1, (chars + 3) // 4)


def _recommend_tools(
    server: McpServerConfig,
    items: tuple[ToolBudgetItem, ...],
    budget_tokens: int,
    task_query: str | None,
) -> tuple[str, ...]:
    item_by_name = {item.name: item for item in items}
    if server.enabled_tools:
        return tuple(tool for tool in server.enabled_tools if tool in item_by_name)

    if task_query and task_query.strip():
        relevant = tuple(item for item in items if item.relevance_score > 0)
        if relevant:
            return _select_within_budget(
                tuple(
                    sorted(
                        relevant,
                        key=lambda value: (
                            -value.relevance_score,
                            value.estimated_tokens,
                            value.name,
                        ),
                    )
                ),
                budget_tokens,
                denied=set(server.disabled_tools),
            )

    return _select_within_budget(
        tuple(sorted(items, key=lambda value: (value.estimated_tokens, value.name))),
        budget_tokens,
        denied=set(server.disabled_tools),
    )


def _select_within_budget(
    items: tuple[ToolBudgetItem, ...], budget_tokens: int, denied: set[str]
) -> tuple[str, ...]:
    selected: list[str] = []
    used_tokens = 0
    for item in items:
        if item.name in denied:
            continue
        if used_tokens + item.estimated_tokens > budget_tokens and selected:
            continue
        selected.append(item.name)
        used_tokens += item.estimated_tokens
        if used_tokens >= budget_tokens:
            break
    return tuple(selected)


def _tool_terms(tool: ToolSchema) -> frozenset[str]:
    return _tokenize(
        " ".join(
            (
                tool.name,
                tool.description,
                _json_terms(tool.input_schema),
                _json_terms(tool.output_schema),
            )
        )
    )


def _json_terms(value: Any) -> str:
    if value is None:
        return ""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _relevance_score(tool: ToolSchema, matched_terms: tuple[str, ...]) -> int:
    if not matched_terms:
        return 0
    name_terms = _tokenize(tool.name)
    name_hits = sum(1 for term in matched_terms if term in name_terms)
    return len(matched_terms) + name_hits


def _tokenize(text: str) -> frozenset[str]:
    stop_words = {
        "a",
        "an",
        "and",
        "for",
        "in",
        "of",
        "on",
        "the",
        "to",
        "with",
    }
    terms = re.findall(r"[a-z0-9]+", text.lower().replace("_", " "))
    return frozenset(term for term in terms if len(term) > 1 and term not in stop_words)


def _toml_key(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return value
    return json.dumps(value)
