from __future__ import annotations

import re
from pathlib import Path

from .models import (
    CompressionItem,
    InstructionRouteReport,
    InstructionSection,
    PromptCompressionReport,
)
from .redaction import REDACTED


_WARNING_RE = re.compile(
    r"(?i)\b(always|must|never|required|warning|do not|don't|before final)\b"
)
_COMMAND_RE = re.compile(
    r"(?i)^\s*(python|pytest|npm|pnpm|yarn|uv|ruff|mypy|git|gh|cargo|go|make)\b"
)
_SECRET_LINE_RE = re.compile(
    r"(?i)\b(api[_-]?key|authorization|bearer|cookie|password|secret|token)\b"
)


def compress_instruction_routes(
    routes: InstructionRouteReport,
    max_lines_per_section: int = 6,
) -> PromptCompressionReport:
    items = tuple(
        _compress_section(section, max_lines_per_section)
        for section in routes.selected_sections
    )
    missing_facts: list[str] = []
    if not items:
        missing_facts.append(
            "No selected instruction sections were available for compression."
        )
    for item in items:
        if not item.required_facts_preserved:
            missing_facts.append(
                f"Compression dropped required matched terms for {item.citation_id}."
            )

    original_tokens = sum(item.original_tokens for item in items)
    compressed_tokens = sum(item.compressed_tokens for item in items)
    return PromptCompressionReport(
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
        compression_ratio=_ratio(compressed_tokens, original_tokens),
        items=items,
        missing_facts=tuple(missing_facts),
    )


def _compress_section(section: InstructionSection, max_lines: int) -> CompressionItem:
    source_text = _section_text(section)
    lines = [
        _safe_line(line.rstrip()) for line in source_text.splitlines() if line.strip()
    ]
    heading = (
        lines[0]
        if lines and lines[0].lstrip().startswith("#")
        else f"# {section.heading_path}"
    )
    important = [heading]
    matched_terms = set(section.matched_terms)

    for line in lines:
        if line == heading:
            continue
        if _is_important_line(line, matched_terms):
            important.append(line)

    if len(important) == 1 and len(lines) > 1:
        important.append(lines[1])

    compressed_lines = _dedupe(important)[: max(1, max_lines)]
    compressed_text = "\n".join(compressed_lines)
    original_tokens = max(section.estimated_tokens, _estimate_tokens(len(source_text)))
    compressed_tokens = _estimate_tokens(len(compressed_text))
    preserved_terms = tuple(
        term
        for term in section.matched_terms
        if term.lower() in compressed_text.lower()
    )
    return CompressionItem(
        citation_id=_citation_id(section),
        source=section.source,
        heading_path=section.heading_path,
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
        compression_ratio=_ratio(compressed_tokens, original_tokens),
        required_facts_preserved=set(section.matched_terms).issubset(
            set(preserved_terms)
        ),
        preserved_terms=preserved_terms,
        compressed_text=compressed_text,
    )


def _is_important_line(line: str, matched_terms: set[str]) -> bool:
    lower = line.lower()
    if (
        matched_terms
        and len(line) <= 180
        and any(term.lower() in lower for term in matched_terms)
    ):
        return True
    if _WARNING_RE.search(line):
        return True
    if _COMMAND_RE.search(line):
        return True
    if line.lstrip().startswith(("-", "*", "`")):
        return True
    return False


def _section_text(section: InstructionSection) -> str:
    path = Path(section.source)
    if not path.exists():
        return section.snippet
    data = path.read_bytes()[section.byte_start : section.byte_end]
    return data.decode("utf-8", errors="replace")


def _safe_line(line: str) -> str:
    return REDACTED if _SECRET_LINE_RE.search(line) else line


def _citation_id(section: InstructionSection) -> str:
    return f"{section.source}#{section.byte_start}-{section.byte_end}:{section.heading_path}"


def _dedupe(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        result.append(line)
    return result


def _estimate_tokens(chars: int) -> int:
    return max(1, (chars + 3) // 4)


def _ratio(compressed_tokens: int, original_tokens: int) -> float:
    if original_tokens <= 0:
        return 1.0
    return round(compressed_tokens / original_tokens, 4)
