from __future__ import annotations

import re
from pathlib import Path

from .context_budget import DEFAULT_INSTRUCTION_NAMES
from .models import InstructionRouteLineage, InstructionRouteReport, InstructionSection
from .redaction import REDACTED


GUIDANCE_SOURCE_NAMES = ("CONTRIBUTING.md", ".github/copilot-instructions.md")
NESTED_INSTRUCTION_NAMES = ("AGENTS.override.md", "AGENTS.md", "CLAUDE.md")
DEFAULT_MAX_NESTED_INSTRUCTION_FILES = 64
DEFAULT_MAX_NESTED_INSTRUCTION_DEPTH = 6
_IGNORED_NESTED_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".ruff_cache",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}
_BASELINE_TERMS = {
    "approval",
    "permission",
    "safety",
    "sandbox",
    "secret",
    "secrets",
    "security",
}
_SECRET_LINE_RE = re.compile(
    r"(?i)\b(api[_-]?key|authorization|bearer|cookie|password|secret|token)\b"
)


def route_instruction_sections(
    root: Path,
    task_query: str,
    fallback_instruction_names: tuple[str, ...] = (),
    include_guidance_sources: bool = False,
    include_nested_instructions: bool = False,
    max_nested_instruction_files: int = DEFAULT_MAX_NESTED_INSTRUCTION_FILES,
    max_nested_instruction_depth: int = DEFAULT_MAX_NESTED_INSTRUCTION_DEPTH,
    max_snippet_chars: int = 360,
) -> InstructionRouteReport:
    root = root.resolve()
    query_terms = _tokenize(task_query)
    sections = _instruction_sections(
        root,
        fallback_instruction_names,
        include_guidance_sources=include_guidance_sources,
        include_nested_instructions=include_nested_instructions,
        max_nested_instruction_files=max_nested_instruction_files,
        max_nested_instruction_depth=max_nested_instruction_depth,
    )
    selected: list[InstructionSection] = []
    skipped: list[InstructionSection] = []
    lineage: list[InstructionRouteLineage] = []

    for section in sections:
        baseline = bool(_tokenize(section.heading_path) & _BASELINE_TERMS)
        matched_terms = tuple(sorted(query_terms & _section_terms(section)))
        should_select = baseline or bool(matched_terms)
        reason = _selection_reason(baseline, matched_terms)
        routed = InstructionSection(
            source=section.source,
            heading_path=section.heading_path,
            byte_start=section.byte_start,
            byte_end=section.byte_end,
            estimated_tokens=section.estimated_tokens,
            matched_terms=matched_terms,
            selected=should_select,
            reason=reason,
            snippet=_snippet(section.snippet, max_snippet_chars)
            if should_select
            else "",
            source_kind=section.source_kind,
            scope_path=section.scope_path,
            scope_depth=section.scope_depth,
        )
        if should_select:
            selected.append(routed)
        else:
            skipped.append(routed)
        lineage.append(
            InstructionRouteLineage(
                original_task=task_query,
                source=section.source,
                heading_path=section.heading_path,
                selected=should_select,
                reason=reason,
                matched_terms=matched_terms,
                source_kind=section.source_kind,
                scope_path=section.scope_path,
                scope_depth=section.scope_depth,
            )
        )

    missing_facts: list[str] = []
    if not sections:
        missing_facts.append("No instruction section evidence was found.")
    elif query_terms and not any(item.matched_terms for item in selected):
        missing_facts.append("No instruction section matched the task query.")

    return InstructionRouteReport(
        original_task=task_query,
        selected_sections=tuple(selected),
        skipped_sections=tuple(skipped),
        lineage=tuple(lineage),
        missing_facts=tuple(missing_facts),
        preserves_orchestrator_baseline=True,
    )


def _instruction_sections(
    root: Path,
    fallback_instruction_names: tuple[str, ...],
    include_guidance_sources: bool = False,
    include_nested_instructions: bool = False,
    max_nested_instruction_files: int = DEFAULT_MAX_NESTED_INSTRUCTION_FILES,
    max_nested_instruction_depth: int = DEFAULT_MAX_NESTED_INSTRUCTION_DEPTH,
) -> tuple[InstructionSection, ...]:
    sections: list[InstructionSection] = []
    seen: set[Path] = set()
    candidates: list[tuple[str, str]] = [
        (name, "orchestrator-instruction") for name in DEFAULT_INSTRUCTION_NAMES
    ]
    candidates.extend(
        (name, "fallback-instruction") for name in fallback_instruction_names
    )
    if include_guidance_sources:
        candidates.extend(
            (name, "developer-guidance") for name in GUIDANCE_SOURCE_NAMES
        )
    for name, source_kind in dict.fromkeys(candidates):
        path = (root / name).resolve()
        if not path.exists() or path in seen:
            continue
        seen.add(path)
        sections.extend(
            _parse_markdown_sections(path, source_kind=source_kind, root=root)
        )
    if include_nested_instructions:
        nested_names = tuple(
            dict.fromkeys(NESTED_INSTRUCTION_NAMES + tuple(fallback_instruction_names))
        )
        for path in _nested_instruction_paths(
            root,
            nested_names,
            max_files=max_nested_instruction_files,
            max_depth=max_nested_instruction_depth,
        ):
            if path in seen:
                continue
            seen.add(path)
            sections.extend(
                _parse_markdown_sections(
                    path,
                    source_kind="nested-instruction",
                    root=root,
                )
            )
    return tuple(sections)


def _parse_markdown_sections(
    path: Path,
    source_kind: str = "orchestrator-instruction",
    root: Path | None = None,
) -> tuple[InstructionSection, ...]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    starts: list[tuple[int, str]] = []
    byte_offset = 0
    for line in lines:
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            starts.append((byte_offset, match.group(2).strip()))
        byte_offset += len(line.encode("utf-8"))

    if not starts:
        starts = [(0, path.name)]

    sections: list[InstructionSection] = []
    file_bytes = len(text.encode("utf-8"))
    scope_path, scope_depth = _scope(path, root)
    for index, (start, heading) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else file_bytes
        raw = text.encode("utf-8")[start:end].decode("utf-8", errors="replace")
        sections.append(
            InstructionSection(
                source=str(path),
                heading_path=heading,
                byte_start=start,
                byte_end=end,
                estimated_tokens=_estimate_tokens(len(raw)),
                matched_terms=(),
                selected=False,
                reason="unrouted",
                snippet=raw,
                source_kind=source_kind,
                scope_path=scope_path,
                scope_depth=scope_depth,
            )
        )
    return tuple(sections)


def _nested_instruction_paths(
    root: Path,
    names: tuple[str, ...],
    max_files: int,
    max_depth: int,
) -> tuple[Path, ...]:
    if max_files <= 0 or max_depth < 0:
        return ()
    root = root.resolve()
    paths: list[Path] = []
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack and len(paths) < max_files:
        current, depth = stack.pop(0)
        for name in names:
            path = (current / name).resolve()
            if path.exists() and path.is_file():
                paths.append(path)
                if len(paths) >= max_files:
                    break
        if depth >= max_depth:
            continue
        children = []
        for child in current.iterdir():
            if (
                child.is_dir()
                and not child.is_symlink()
                and child.name not in _IGNORED_NESTED_DIRS
            ):
                children.append(child)
        stack.extend((child, depth + 1) for child in sorted(children))
    return tuple(paths)


def _scope(path: Path, root: Path | None) -> tuple[str, int]:
    if root is None:
        return ".", 0
    try:
        relative_parent = path.resolve().relative_to(root.resolve()).parent
    except ValueError:
        return ".", 0
    if str(relative_parent) == ".":
        return ".", 0
    scope_path = relative_parent.as_posix()
    return scope_path, len(relative_parent.parts)


def _selection_reason(baseline: bool, matched_terms: tuple[str, ...]) -> str:
    if baseline:
        return "selected as orchestrator-baseline policy section"
    if matched_terms:
        return "selected by task-query term match"
    return "skipped because section did not match task query"


def _section_terms(section: InstructionSection) -> frozenset[str]:
    return _tokenize(f"{section.heading_path}\n{section.snippet}")


def _snippet(text: str, max_chars: int) -> str:
    safe_lines = []
    for line in text.splitlines():
        safe_lines.append(REDACTED if _SECRET_LINE_RE.search(line) else line)
    value = "\n".join(safe_lines).strip()
    if len(value) <= max_chars:
        return value
    return value[: max(0, max_chars - 3)].rstrip() + "..."


def _tokenize(text: str) -> frozenset[str]:
    terms = re.findall(r"[a-z0-9]+", text.lower().replace("_", " "))
    stop_words = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}
    return frozenset(term for term in terms if len(term) > 1 and term not in stop_words)


def _estimate_tokens(chars: int) -> int:
    return max(1, (chars + 3) // 4)
