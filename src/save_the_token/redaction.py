from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .models import McpServerConfig

REDACTED = "<redacted>"

_SECRET_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "bearer",
    "client_secret",
    "cookie",
    "key",
    "password",
    "secret",
    "token",
)


def public_server_dict(server: McpServerConfig) -> dict[str, Any]:
    payload = asdict(server)
    payload["source"]["path"] = str(server.source.path)
    return redact_mapping(payload)


def redact_mapping(value: Any, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        return {key: redact_mapping(item, str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_mapping(item, parent_key) for item in value]
    if isinstance(value, tuple):
        return [redact_mapping(item, parent_key) for item in value]
    if isinstance(value, str) and _is_secret_key(parent_key):
        return REDACTED
    return value


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(marker in normalized for marker in _SECRET_MARKERS)
