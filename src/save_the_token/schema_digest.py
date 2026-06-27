from __future__ import annotations

import json
import re
from typing import Any

from .models import (
    McpServerConfig,
    ToolBudgetItem,
    ToolBudgetReport,
    ToolSchema,
    ToolSchemaDigestItem,
    ToolSchemaDigestReport,
)


def digest_tool_schemas(
    server: McpServerConfig,
    tools: tuple[ToolSchema, ...],
    budget: ToolBudgetReport | None = None,
) -> ToolSchemaDigestReport:
    budget_items = {item.name: item for item in budget.items} if budget else {}
    items = tuple(
        _digest_item(server, tool, budget_items.get(tool.name)) for tool in tools
    )
    full_tokens = sum(item.full_schema_tokens for item in items)
    digest_tokens = sum(item.digest_tokens for item in items)
    saved_tokens = max(0, full_tokens - digest_tokens)
    missing_facts: tuple[str, ...] = ()
    if not items:
        missing_facts = ("No tool schema evidence was available for digesting.",)
    return ToolSchemaDigestReport(
        server=server,
        total_tools=len(items),
        total_full_schema_tokens=full_tokens,
        total_digest_tokens=digest_tokens,
        saved_tokens=saved_tokens,
        compression_ratio=_ratio(digest_tokens, full_tokens),
        items=items,
        missing_facts=missing_facts,
    )


def _digest_item(
    server: McpServerConfig,
    tool: ToolSchema,
    budget_item: ToolBudgetItem | None,
) -> ToolSchemaDigestItem:
    full_payload = {
        "name": tool.name,
        "description": tool.description,
        "inputSchema": tool.input_schema,
        "outputSchema": tool.output_schema,
    }
    required_inputs = _required_inputs(tool.input_schema)
    risk_markers = _risk_markers(tool)
    digest_payload = {
        "name": tool.name,
        "description": _shorten(tool.description, 180),
        "required_inputs": required_inputs,
        "risk_markers": risk_markers,
        "full_schema_ref": _schema_ref(server, tool),
    }
    full_tokens = _estimate_tokens(_stable_json(full_payload))
    digest_tokens = _estimate_tokens(_stable_json(digest_payload))
    return ToolSchemaDigestItem(
        name=tool.name,
        description=_shorten(tool.description, 180),
        required_inputs=required_inputs,
        risk_markers=risk_markers,
        full_schema_ref=_schema_ref(server, tool),
        full_schema_tokens=full_tokens,
        digest_tokens=digest_tokens,
        saved_tokens=max(0, full_tokens - digest_tokens),
        missing_details=_missing_details(tool),
        relevance_score=budget_item.relevance_score if budget_item else 0,
        matched_terms=budget_item.matched_terms if budget_item else (),
    )


def _required_inputs(schema: dict[str, Any]) -> tuple[str, ...]:
    required = schema.get("required", ())
    if not isinstance(required, list):
        return ()
    return tuple(str(item) for item in required if isinstance(item, str))


def _risk_markers(tool: ToolSchema) -> tuple[str, ...]:
    text = " ".join(
        (
            tool.name,
            tool.description,
            _stable_json(tool.input_schema),
            _stable_json(tool.output_schema),
            _stable_json(tool.raw),
        )
    ).lower()
    markers: list[str] = []
    if re.search(r"\b(delete|remove|destroy|drop|truncate|terminate)\b", text):
        markers.append("destructive")
    if re.search(r"\b(create|update|write|patch|modify|merge|commit|publish)\b", text):
        markers.append("write")
    if re.search(
        r"\b(auth|authorization|token|secret|password|api[_-]?key|credential)\b", text
    ):
        markers.append("auth")
    if re.search(r"\b(url|http|https|network|request|remote|webhook)\b", text):
        markers.append("network")
    if re.search(r"\b(file|path|directory|folder|filesystem)\b", text):
        markers.append("filesystem")
    return tuple(markers)


def _missing_details(tool: ToolSchema) -> tuple[str, ...]:
    details = ["full inputSchema omitted; use full_schema_ref when invoking the tool."]
    if tool.output_schema is not None:
        details.append("full outputSchema omitted from digest.")
    properties = tool.input_schema.get("properties")
    if isinstance(properties, dict):
        optional_count = len(set(properties) - set(_required_inputs(tool.input_schema)))
        if optional_count:
            details.append(
                f"{optional_count} optional input field(s) omitted or summarized."
            )
    if tool.raw:
        details.append("raw tool payload omitted from digest.")
    return tuple(details)


def _schema_ref(server: McpServerConfig, tool: ToolSchema) -> str:
    return f"{server.source.path}#{server.server_id}/tools/{tool.name}/schema"


def _estimate_tokens(serialized: str) -> int:
    return max(1, (len(serialized) + 3) // 4)


def _ratio(part: int, whole: int) -> float:
    if whole <= 0:
        return 1.0
    return round(part / whole, 3)


def _shorten(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _stable_json(value: Any) -> str:
    if value is None:
        return "null"
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
