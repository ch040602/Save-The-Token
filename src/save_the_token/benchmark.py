from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from .evaluation import evaluate_token_budget
from .instruction_routing import route_instruction_sections


DEFAULT_BENCHMARK_TASKS = ("unit tests", "security review")


class _BestSufficient(TypedDict):
    variant: str
    tokens: int
    saving_pct: float


def build_benchmark_report(
    repos_dir: Path,
    task_queries: tuple[str, ...] = DEFAULT_BENCHMARK_TASKS,
    fallback_instruction_names: tuple[str, ...] = (),
    include_guidance_sources: bool = False,
    include_nested_instructions: bool = False,
    repo_commits_path: Path | None = None,
) -> dict[str, Any]:
    repos_dir = repos_dir.resolve()
    commits = _load_repo_commits(repo_commits_path)
    rows: list[dict[str, Any]] = []
    for repo_dir in sorted(path for path in repos_dir.iterdir() if path.is_dir()):
        repo_name = _repo_name(repo_dir, commits)
        fallbacks = tuple(
            name for name in fallback_instruction_names if (repo_dir / name).exists()
        )
        for task_query in task_queries:
            rows.append(
                _row(
                    repo_dir,
                    repo_name=repo_name,
                    commit=commits.get(repo_name, ""),
                    task_query=task_query,
                    fallback_instruction_names=fallbacks,
                    include_guidance_sources=include_guidance_sources,
                    include_nested_instructions=include_nested_instructions,
                )
            )

    return {
        "method": "strict-token-budget-benchmark",
        "benchmark_options": {
            "repos_dir": str(repos_dir),
            "task_queries": list(task_queries),
            "fallback_instruction_names": list(fallback_instruction_names),
            "include_guidance_sources": include_guidance_sources,
            "include_nested_instructions": include_nested_instructions,
            "repo_commits_path": str(repo_commits_path.resolve())
            if repo_commits_path
            else None,
        },
        "summary": _summary(rows),
        "rows": rows,
        "caveats": _caveats(include_nested_instructions),
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Save-The-Token Benchmark Report",
        "",
        "## Summary",
        "",
        f"- total cases: {summary['total_cases']}",
        f"- eligible full-sufficient cases: {summary['eligible_full_sufficient_cases']}",
        f"- successful reduced cases: {summary['successful_reduced_cases']}",
        f"- success rate across all cases: {summary.get('success_rate_all_cases_pct', 0.0)}%",
        f"- success rate among eligible cases: {summary.get('success_rate_eligible_pct', 0.0)}%",
        f"- weighted saving on successful cases: {_pct(summary.get('weighted_saving_successes_pct'))}",
        f"- median saving on successful cases: {_pct(summary.get('median_saving_successes_pct'))}",
        f"- compression/reorder successes: {summary.get('compression_or_reorder_successes', 0)}",
        f"- selected-only successes: {summary.get('selected_only_successes', 0)}",
        "",
        "## Successful Reductions",
        "",
        "| repo | task | best variant | tokens | saving |",
        "|---|---|---|---:|---:|",
    ]
    successes = [row for row in report["rows"] if row["best_sufficient"]]
    if successes:
        for row in successes:
            best = row["best_sufficient"]
            lines.append(
                "| {repo} | {task} | {variant} | {full}->{reduced} | {saving}% |".format(
                    repo=row["repo"],
                    task=row["task_query"],
                    variant=best["variant"],
                    full=row["full_tokens"],
                    reduced=best["tokens"],
                    saving=best["saving_pct"],
                )
            )
    else:
        lines.append("| none | none | none | 0->0 | 0% |")
    lines.extend(["", "## Caveats", ""])
    lines.extend(f"- {item}" for item in report["caveats"])
    lines.append("")
    return "\n".join(lines)


def _row(
    repo_dir: Path,
    repo_name: str,
    commit: str,
    task_query: str,
    fallback_instruction_names: tuple[str, ...],
    include_guidance_sources: bool,
    include_nested_instructions: bool,
) -> dict[str, Any]:
    report = evaluate_token_budget(
        repo_dir,
        task_query=task_query,
        fallback_instruction_names=fallback_instruction_names,
        include_guidance_sources=include_guidance_sources,
        include_nested_instructions=include_nested_instructions,
    )
    routes = route_instruction_sections(
        repo_dir,
        task_query=task_query,
        fallback_instruction_names=fallback_instruction_names,
        include_guidance_sources=include_guidance_sources,
        include_nested_instructions=include_nested_instructions,
    )
    variants = {variant.name: variant for variant in report.variants}
    full = variants["full_context"]
    best_sufficient: _BestSufficient | None = None
    if full.sufficiency_status == "sufficient" and full.estimated_tokens > 0:
        for name in ("reordered_context", "compressed_context", "selected_context"):
            variant = variants[name]
            if variant.sufficiency_status == "sufficient":
                saving_pct = round(
                    (1 - variant.estimated_tokens / full.estimated_tokens) * 100, 1
                )
                if (
                    best_sufficient is None
                    or saving_pct > best_sufficient["saving_pct"]
                ):
                    best_sufficient = {
                        "variant": name,
                        "tokens": variant.estimated_tokens,
                        "saving_pct": saving_pct,
                    }

    return {
        "repo": repo_name,
        "commit": commit,
        "task_query": task_query,
        "fallback_instruction_names": list(fallback_instruction_names),
        "source_kinds": sorted(
            {
                section.source_kind
                for section in routes.selected_sections + routes.skipped_sections
            }
        ),
        "selected_sections": len(routes.selected_sections),
        "skipped_sections": len(routes.skipped_sections),
        "full_tokens": full.estimated_tokens,
        "full_status": full.sufficiency_status,
        "selected_tokens": variants["selected_context"].estimated_tokens,
        "selected_status": variants["selected_context"].sufficiency_status,
        "compressed_tokens": variants["compressed_context"].estimated_tokens,
        "compressed_status": variants["compressed_context"].sufficiency_status,
        "compressed_missing_fact_count": variants[
            "compressed_context"
        ].missing_fact_count,
        "reordered_tokens": variants["reordered_context"].estimated_tokens,
        "reordered_status": variants["reordered_context"].sufficiency_status,
        "reordered_missing_fact_count": variants[
            "reordered_context"
        ].missing_fact_count,
        "regressions": list(report.regressions),
        "best_sufficient": best_sufficient,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [
        row
        for row in rows
        if row["full_status"] == "sufficient" and row["full_tokens"] > 0
    ]
    successes = [row for row in eligible if row["best_sufficient"]]
    compression_successes = [
        row
        for row in successes
        if row["best_sufficient"]["variant"]
        in {"compressed_context", "reordered_context"}
    ]
    selected_successes = [
        row
        for row in successes
        if row["best_sufficient"]["variant"] == "selected_context"
    ]
    full_tokens = sum(row["full_tokens"] for row in successes)
    reduced_tokens = sum(row["best_sufficient"]["tokens"] for row in successes)
    savings = sorted(row["best_sufficient"]["saving_pct"] for row in successes)
    return {
        "total_cases": len(rows),
        "eligible_full_sufficient_cases": len(eligible),
        "successful_reduced_cases": len(successes),
        "success_rate_all_cases_pct": _ratio(len(successes), len(rows)),
        "success_rate_eligible_pct": _ratio(len(successes), len(eligible)),
        "weighted_saving_successes_pct": (
            round((1 - reduced_tokens / full_tokens) * 100, 1) if full_tokens else None
        ),
        "median_saving_successes_pct": _median(savings),
        "compression_or_reorder_successes": len(compression_successes),
        "selected_only_successes": len(selected_successes),
    }


def _load_repo_commits(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {str(row["repo"]): str(row.get("commit", "")) for row in rows}


def _repo_name(repo_dir: Path, commits: dict[str, str]) -> str:
    candidate = repo_dir.name.replace("__", "/")
    if candidate in commits:
        return candidate
    for name in commits:
        if name.replace("/", "__") == repo_dir.name:
            return name
    return candidate


def _caveats(include_nested_instructions: bool = False) -> tuple[str, ...]:
    caveats = [
        "Savings are counted only when full_context and the reduced variant are both sufficient.",
        "Cases without sufficient full_context are coverage gaps, not token-saving successes.",
        "Evaluation is lexical over task terms and missing-fact counters; it is not semantic answer-quality grading.",
        "Compression and reordering savings should not be claimed when they introduce missing facts.",
    ]
    if include_nested_instructions:
        caveats.append(
            "This run includes bounded nested instruction discovery; compare it separately from root-only benchmarks."
        )
    else:
        caveats.append(
            "By default, benchmark coverage is root-level instruction coverage only; use nested instruction mode for subdirectory AGENTS.md or CLAUDE.md files."
        )
    return tuple(caveats)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    midpoint = len(values) // 2
    if len(values) % 2:
        return values[midpoint]
    return round((values[midpoint - 1] + values[midpoint]) / 2, 1)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value}%"
