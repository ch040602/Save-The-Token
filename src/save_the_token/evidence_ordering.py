from __future__ import annotations

import re
from pathlib import Path

from .models import (
    CompressionItem,
    EvidenceOrderItem,
    EvidenceOrderReport,
    PromptCompressionReport,
)


_SAFETY_TERMS = {
    "approval",
    "permission",
    "safety",
    "sandbox",
    "secret",
    "secrets",
    "security",
}


def order_prompt_evidence(compression: PromptCompressionReport) -> EvidenceOrderReport:
    scored = [_score_item(item) for item in compression.items]
    ordered_raw = sorted(
        scored,
        key=lambda value: (
            -value[0],
            -value[1],
            -value[2],
            value[3].source,
            value[3].heading_path,
            value[3].citation_id,
        ),
    )
    ordered_items = tuple(
        EvidenceOrderItem(
            rank=index + 1,
            placement="front" if index < 2 else "body",
            citation_id=item.citation_id,
            source=item.source,
            heading_path=item.heading_path,
            priority_score=priority_score,
            recency_ns=recency_ns,
            rationale=_rationale(item, priority_score, recency_ns),
            compressed_tokens=item.compressed_tokens,
            compressed_text=item.compressed_text,
        )
        for index, (priority_score, recency_ns, citation_need, item) in enumerate(
            ordered_raw
        )
    )
    missing_facts: tuple[str, ...] = ()
    if not ordered_items:
        missing_facts = ("No compressed evidence was available for ordering.",)
    return EvidenceOrderReport(
        ordered_items=ordered_items,
        lead_digest=_lead_digest(ordered_items),
        ordering_rationale=(
            "Ordered by safety/task priority, citation availability, recency, then stable source "
            "and heading tie-breakers to reduce lost-in-the-middle risk."
        ),
        missing_facts=missing_facts,
    )


def _score_item(item: CompressionItem) -> tuple[int, int, int, CompressionItem]:
    heading_terms = _tokenize(item.heading_path)
    safety_score = 100 if heading_terms & _SAFETY_TERMS else 0
    task_score = len(item.preserved_terms) * 20
    warning_score = 10 if _has_warning(item.compressed_text) else 0
    command_score = 5 if _has_command(item.compressed_text) else 0
    citation_need = 1 if item.citation_id else 0
    priority_score = (
        safety_score + task_score + warning_score + command_score + citation_need
    )
    return priority_score, _mtime_ns(item.source), citation_need, item


def _rationale(item: CompressionItem, priority_score: int, recency_ns: int) -> str:
    reasons = [f"priority_score={priority_score}", f"recency_ns={recency_ns}"]
    if _tokenize(item.heading_path) & _SAFETY_TERMS:
        reasons.append("baseline safety/security evidence")
    if item.preserved_terms:
        reasons.append(f"task terms={list(item.preserved_terms)}")
    if item.citation_id:
        reasons.append("citation id available")
    return "; ".join(reasons)


def _lead_digest(items: tuple[EvidenceOrderItem, ...]) -> str:
    if not items:
        return ""
    lines = ["Lead digest:"]
    for item in items[:3]:
        lines.append(f"- [{item.citation_id}] {item.heading_path}: {item.rationale}")
    return "\n".join(lines)


def _mtime_ns(source: str) -> int:
    path = Path(source)
    if not path.exists():
        return 0
    return path.stat().st_mtime_ns


def _has_warning(text: str) -> bool:
    return bool(
        re.search(r"(?i)\b(always|must|never|required|warning|do not|don't)\b", text)
    )


def _has_command(text: str) -> bool:
    return bool(
        re.search(r"(?im)^\s*(python|pytest|npm|pnpm|yarn|uv|ruff|mypy|git|gh)\b", text)
    )


def _tokenize(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", text.lower().replace("_", " ")))
