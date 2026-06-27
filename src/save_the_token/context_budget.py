from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .models import ConfigSource, ContextBudgetItem, ContextBudgetReport


DEFAULT_INSTRUCTION_NAMES = ("AGENTS.override.md", "AGENTS.md")


def plan_context_budget(
    root: Path,
    config_sources: tuple[ConfigSource, ...],
    budget_tokens: int,
    fallback_instruction_names: tuple[str, ...] = (),
) -> ContextBudgetReport:
    root = root.resolve()
    candidates = _candidate_items(root, config_sources, fallback_instruction_names)
    budget = max(0, budget_tokens)
    selected: list[ContextBudgetItem] = []
    skipped: list[ContextBudgetItem] = []
    used_tokens = 0

    for item in sorted(candidates, key=lambda value: (value.priority, value.source)):
        if used_tokens + item.estimated_tokens <= budget:
            selected_item = replace(
                item, selected=True, reason="selected within context budget"
            )
            selected.append(selected_item)
            used_tokens += item.estimated_tokens
        else:
            skipped.append(
                replace(item, selected=False, reason="exceeds remaining context budget")
            )

    instruction_items = [item for item in candidates if item.kind == "instructions"]
    skipped_configs = [item for item in skipped if item.kind == "client-config"]
    skipped_instructions = [item for item in skipped if item.kind == "instructions"]
    missing_facts: list[str] = []
    if skipped_configs:
        names = ", ".join(Path(item.source).name for item in skipped_configs)
        missing_facts.append(f"Config evidence skipped by context budget: {names}.")
    if not instruction_items:
        missing_facts.append("No instruction evidence file was found.")
    if skipped_instructions:
        names = ", ".join(Path(item.source).name for item in skipped_instructions)
        missing_facts.append(
            f"Instruction evidence skipped by context budget: {names}."
        )

    return ContextBudgetReport(
        budget_tokens=budget,
        total_estimated_tokens=sum(item.estimated_tokens for item in candidates),
        selected_tokens=sum(item.estimated_tokens for item in selected),
        skipped_tokens=sum(item.estimated_tokens for item in skipped),
        selected=tuple(selected),
        skipped=tuple(skipped),
        missing_facts=tuple(missing_facts),
        preserves_orchestrator_baseline=True,
    )


def _candidate_items(
    root: Path,
    config_sources: tuple[ConfigSource, ...],
    fallback_instruction_names: tuple[str, ...],
) -> tuple[ContextBudgetItem, ...]:
    items: list[ContextBudgetItem] = []
    seen: set[Path] = set()

    for source in config_sources:
        path = source.path.resolve()
        if path.exists() and path not in seen:
            seen.add(path)
            items.append(_item(path, kind="client-config", priority=0))

    instruction_names = DEFAULT_INSTRUCTION_NAMES + tuple(fallback_instruction_names)
    for index, name in enumerate(dict.fromkeys(instruction_names)):
        path = (root / name).resolve()
        if path.exists() and path not in seen:
            seen.add(path)
            items.append(_item(path, kind="instructions", priority=10 + index))

    return tuple(items)


def _item(path: Path, kind: str, priority: int) -> ContextBudgetItem:
    size_bytes = path.stat().st_size
    return ContextBudgetItem(
        source=str(path),
        kind=kind,
        size_bytes=size_bytes,
        estimated_tokens=_estimate_tokens(size_bytes),
        selected=False,
        reason="unplanned",
        priority=priority,
    )


def _estimate_tokens(size_bytes: int) -> int:
    return max(1, (size_bytes + 3) // 4)
