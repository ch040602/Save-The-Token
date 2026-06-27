from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .models import (
    EvidenceCacheStatus,
    EvidenceFingerprint,
    McpServerConfig,
    ToolSchema,
)


SummaryCache = Mapping[str, Mapping[str, Any]]


def fingerprint_file(path: Path, kind: str) -> EvidenceFingerprint:
    resolved = path.resolve()
    data = resolved.read_bytes()
    stat = resolved.stat()
    return EvidenceFingerprint(
        source=str(resolved),
        kind=kind,
        size_bytes=len(data),
        estimated_tokens=_estimate_tokens(len(data.decode("utf-8", errors="replace"))),
        sha256=_sha256(data),
        mtime_ns=stat.st_mtime_ns,
    )


def fingerprint_text(source: str, text: str, kind: str) -> EvidenceFingerprint:
    data = text.encode("utf-8")
    return EvidenceFingerprint(
        source=source,
        kind=kind,
        size_bytes=len(data),
        estimated_tokens=_estimate_tokens(len(text)),
        sha256=_sha256(data),
    )


def fingerprint_tools(
    server: McpServerConfig, tools: tuple[ToolSchema, ...]
) -> EvidenceFingerprint:
    payload = json.dumps(
        [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
                "outputSchema": tool.output_schema,
                "raw": tool.raw,
            }
            for tool in tools
        ],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    source = f"{server.source.path.resolve()}#{server.server_id}/tools-list"
    return fingerprint_text(source, payload, kind="tools")


def cache_entry(fingerprint: EvidenceFingerprint, summary: str) -> dict[str, Any]:
    return {
        "source": fingerprint.source,
        "kind": fingerprint.kind,
        "sha256": fingerprint.sha256,
        "size_bytes": fingerprint.size_bytes,
        "estimated_tokens": fingerprint.estimated_tokens,
        "summary": summary,
    }


def load_summary_cache(path: Path) -> dict[str, Mapping[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries", data) if isinstance(data, dict) else data
    if isinstance(entries, dict):
        return {
            str(key): value
            for key, value in entries.items()
            if isinstance(value, Mapping)
        }
    if not isinstance(entries, list):
        return {}
    normalized: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        source = entry.get("source")
        kind = entry.get("kind")
        sha256 = entry.get("sha256")
        if (
            not isinstance(source, str)
            or not isinstance(kind, str)
            or not isinstance(sha256, str)
        ):
            continue
        normalized[_cache_key(kind, source, sha256)] = entry
    return normalized


def lookup_cached_summary(
    cache: SummaryCache, fingerprint: EvidenceFingerprint
) -> EvidenceCacheStatus:
    entry = cache.get(fingerprint.cache_key)
    if entry is None:
        return EvidenceCacheStatus(fingerprint=fingerprint, cache_hit=False)
    summary = entry.get("summary")
    estimated_tokens = entry.get("estimated_tokens", fingerprint.estimated_tokens)
    return EvidenceCacheStatus(
        fingerprint=fingerprint,
        cache_hit=True,
        cached_summary=summary if isinstance(summary, str) else None,
        cached_estimated_tokens=estimated_tokens
        if isinstance(estimated_tokens, int)
        else None,
    )


def status_to_dict(status: EvidenceCacheStatus) -> dict[str, Any]:
    return {
        "fingerprint": status.fingerprint.to_dict(),
        "cache_hit": status.cache_hit,
        "cached_summary": status.cached_summary,
        "cached_estimated_tokens": status.cached_estimated_tokens,
    }


def _cache_key(kind: str, source: str, sha256: str) -> str:
    return f"{kind}:{source}:{sha256}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _estimate_tokens(chars: int) -> int:
    return max(1, (chars + 3) // 4)
