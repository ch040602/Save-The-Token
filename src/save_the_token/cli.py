from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .active_retrieval import plan_active_retrieval
from .benchmark import (
    DEFAULT_BENCHMARK_TASKS,
    build_benchmark_report,
    render_markdown_report,
)
from .config import scan_configs
from .budget import analyze_tool_budget
from .context_budget import plan_context_budget
from .diagnostics import build_diagnostic_report
from .evaluation import evaluate_token_budget
from .evidence_ordering import order_prompt_evidence
from .evidence_cache import (
    fingerprint_file,
    fingerprint_tools,
    load_summary_cache,
    lookup_cached_summary,
    status_to_dict,
)
from .instruction_routing import route_instruction_sections
from .orchestration import plan_orchestration_advice
from .prompt_compression import compress_instruction_routes
from .probe import HttpMcpProbe, StdioMcpProbe
from .redaction import public_server_dict
from .schema_digest import digest_tool_schemas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="save-the-token")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser(
        "scan", help="Discover and lint MCP config files."
    )
    scan_parser.add_argument("--root", default=".", help="Project root to inspect.")
    scan_parser.add_argument(
        "--home", default=None, help="Override home directory for tests."
    )
    scan_parser.add_argument(
        "--cache", default=None, help="Optional evidence summary cache JSON path."
    )

    doctor_parser = subparsers.add_parser(
        "doctor", help="Probe configured MCP servers."
    )
    doctor_parser.add_argument("--root", default=".", help="Project root to inspect.")
    doctor_parser.add_argument(
        "--home", default=None, help="Override home directory for tests."
    )
    doctor_parser.add_argument(
        "--timeout", type=float, default=5.0, help="Per-request timeout in seconds."
    )

    tools_parser = subparsers.add_parser(
        "tools", help="Probe tools and report schema budget."
    )
    tools_parser.add_argument("--root", default=".", help="Project root to inspect.")
    tools_parser.add_argument(
        "--home", default=None, help="Override home directory for tests."
    )
    tools_parser.add_argument(
        "--timeout", type=float, default=5.0, help="Per-request timeout in seconds."
    )
    tools_parser.add_argument(
        "--budget", type=int, default=8000, help="Token budget per MCP server."
    )
    tools_parser.add_argument(
        "--task",
        default=None,
        help="Optional task query for task-aware tool selection.",
    )
    tools_parser.add_argument(
        "--schema-digest",
        action="store_true",
        help="Emit compact tool schema digests with required inputs, risk markers, and token savings.",
    )

    slim_parser = subparsers.add_parser(
        "slim", help="Emit Codex enabled_tools snippets for probed MCP servers."
    )
    slim_parser.add_argument("--root", default=".", help="Project root to inspect.")
    slim_parser.add_argument(
        "--home", default=None, help="Override home directory for tests."
    )
    slim_parser.add_argument(
        "--timeout", type=float, default=5.0, help="Per-request timeout in seconds."
    )
    slim_parser.add_argument(
        "--budget", type=int, default=8000, help="Token budget per MCP server."
    )
    slim_parser.add_argument(
        "--task",
        default=None,
        help="Optional task query for task-aware tool selection.",
    )

    report_parser = subparsers.add_parser(
        "report", help="Emit a grounded sufficiency report."
    )
    report_parser.add_argument("--root", default=".", help="Project root to inspect.")
    report_parser.add_argument(
        "--home", default=None, help="Override home directory for tests."
    )
    report_parser.add_argument(
        "--timeout", type=float, default=5.0, help="Per-request timeout in seconds."
    )
    report_parser.add_argument(
        "--budget", type=int, default=8000, help="Token budget per MCP server."
    )
    report_parser.add_argument(
        "--task",
        default=None,
        help="Optional task query for task-aware tool selection.",
    )
    report_parser.add_argument(
        "--cache", default=None, help="Optional evidence summary cache JSON path."
    )
    report_parser.add_argument(
        "--context-budget",
        type=int,
        default=None,
        help="Optional token budget for config and instruction evidence planning.",
    )
    report_parser.add_argument(
        "--fallback-instruction",
        action="append",
        default=[],
        help="Additional root-level instruction filename to include in context budget planning.",
    )
    report_parser.add_argument(
        "--include-guidance",
        action="store_true",
        help="Opt in to routing developer guidance files such as CONTRIBUTING.md and .github/copilot-instructions.md.",
    )
    report_parser.add_argument(
        "--include-nested-instructions",
        action="store_true",
        help="Opt in to bounded nested AGENTS.md and CLAUDE.md instruction discovery.",
    )
    report_parser.add_argument(
        "--route-instructions",
        action="store_true",
        help="Route root-level instruction sections by --task and include selected/skipped lineage.",
    )
    report_parser.add_argument(
        "--compress-instructions",
        action="store_true",
        help="Compress routed instruction snippets with deterministic extractive selection.",
    )
    report_parser.add_argument(
        "--order-evidence",
        action="store_true",
        help="Order compressed evidence and emit a lead digest to reduce lost-in-the-middle risk.",
    )
    report_parser.add_argument(
        "--active-retrieval",
        type=int,
        default=None,
        metavar="N",
        help="Plan up to N missing-fact follow-up retrieval steps without changing insufficient status.",
    )
    report_parser.add_argument(
        "--schema-digest",
        action="store_true",
        help="Include compact tool schema digests in the sufficiency report.",
    )
    report_parser.add_argument(
        "--orchestration-advice",
        action="store_true",
        help="Include recommend-only main-agent, skill, and explicit-subagent orchestration guidance.",
    )

    eval_parser = subparsers.add_parser(
        "eval",
        help="Evaluate token-reduction variants over local instruction evidence.",
    )
    eval_parser.add_argument("--root", default=".", help="Project root to inspect.")
    eval_parser.add_argument(
        "--task", required=True, help="Task query used for routing and recall checks."
    )
    eval_parser.add_argument(
        "--fallback-instruction",
        action="append",
        default=[],
        help="Additional root-level instruction filename to include in evaluation.",
    )
    eval_parser.add_argument(
        "--include-guidance",
        action="store_true",
        help="Opt in to evaluating developer guidance files such as CONTRIBUTING.md and .github/copilot-instructions.md.",
    )
    eval_parser.add_argument(
        "--include-nested-instructions",
        action="store_true",
        help="Opt in to bounded nested AGENTS.md and CLAUDE.md instruction discovery.",
    )

    benchmark_parser = subparsers.add_parser(
        "benchmark", help="Run strict token-reduction benchmark reports."
    )
    benchmark_parser.add_argument(
        "--repos-dir", required=True, help="Directory containing repo checkouts."
    )
    benchmark_parser.add_argument(
        "--task",
        action="append",
        default=[],
        help="Task query to benchmark. Repeat for multiple tasks; defaults to unit tests and security review.",
    )
    benchmark_parser.add_argument(
        "--fallback-instruction",
        action="append",
        default=[],
        help="Additional root-level instruction filename to include when present in each repo.",
    )
    benchmark_parser.add_argument(
        "--include-guidance",
        action="store_true",
        help="Opt in to benchmark developer guidance files such as CONTRIBUTING.md.",
    )
    benchmark_parser.add_argument(
        "--include-nested-instructions",
        action="store_true",
        help="Opt in to benchmark bounded nested AGENTS.md and CLAUDE.md instruction discovery.",
    )
    benchmark_parser.add_argument(
        "--repo-commits", default=None, help="Optional JSON file with repo/commit rows."
    )
    benchmark_parser.add_argument(
        "--json-out", default=None, help="Optional path to write benchmark JSON."
    )
    benchmark_parser.add_argument(
        "--markdown-out",
        default=None,
        help="Optional path to write benchmark Markdown.",
    )

    args = parser.parse_args(argv)
    if args.command == "scan":
        home = Path(args.home) if args.home else None
        root = Path(args.root).resolve()
        result = scan_configs(root, home)
        evidence_cache = _evidence_cache_statuses(root, result, (), args.cache)
        payload = {
            "sources": [
                asdict(source) | {"path": str(source.path)} for source in result.sources
            ],
            "servers": [public_server_dict(server) for server in result.servers],
            "findings": [asdict(finding) for finding in result.findings],
            "evidence_cache": [status_to_dict(status) for status in evidence_cache],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1 if any(f.severity == "error" for f in result.findings) else 0
    if args.command == "doctor":
        home = Path(args.home) if args.home else None
        result = scan_configs(Path(args.root).resolve(), home)
        probes = _probe_servers(result.servers, args.timeout)
        payload = {
            "config_findings": [asdict(finding) for finding in result.findings],
            "probes": [
                {
                    "server_id": probe_result.server.server_id,
                    "source": str(probe_result.server.source.path),
                    "ok": probe_result.ok,
                    "initialized": probe_result.initialized,
                    "tool_count": len(probe_result.tools),
                    "tools": [tool.name for tool in probe_result.tools],
                    "error": probe_result.error,
                    "stderr": probe_result.stderr,
                }
                for probe_result in probes
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return (
            1
            if any(f.severity == "error" for f in result.findings)
            or any(not p.ok for p in probes)
            else 0
        )
    if args.command == "tools":
        result, probes, reports = _probe_budget(
            args.root, args.home, args.timeout, args.budget, args.task
        )
        schema_digests = _schema_digests(probes, reports) if args.schema_digest else ()
        payload = {
            "task_query": args.task,
            "config_findings": [asdict(finding) for finding in result.findings],
            "probe_errors": [
                {"server_id": p.server.server_id, "error": p.error, "stderr": p.stderr}
                for p in probes
                if not p.ok
            ],
            "budget_reports": [
                {
                    "server_id": report.server.server_id,
                    "total_tools": report.total_tools,
                    "estimated_tokens": report.estimated_tokens,
                    "budget_tokens": report.budget_tokens,
                    "over_budget": report.over_budget,
                    "items": [
                        {
                            "name": item.name,
                            "estimated_tokens": item.estimated_tokens,
                            "relevance_score": item.relevance_score,
                            "matched_terms": list(item.matched_terms),
                        }
                        for item in report.items
                    ],
                    "recommended_enabled_tools": list(report.recommended_enabled_tools),
                    "codex_toml_snippet": report.codex_toml_snippet,
                    "client_snippet_format": report.client_snippet_format,
                    "client_snippet": report.client_snippet,
                }
                for report in reports
            ],
            "schema_digests": [
                _schema_digest_payload(digest) for digest in schema_digests
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return (
            1
            if any(f.severity == "error" for f in result.findings)
            or any(not p.ok for p in probes)
            else 0
        )
    if args.command == "slim":
        result, probes, reports = _probe_budget(
            args.root, args.home, args.timeout, args.budget, args.task
        )
        for report in reports:
            suffix = f" for task: {args.task}" if args.task else ""
            print(
                f"# {report.server.server_id}: {report.estimated_tokens}/{report.budget_tokens} estimated tokens{suffix}"
            )
            print(report.client_snippet)
            if not report.client_snippet.endswith("\n"):
                print()
        return (
            1
            if any(f.severity == "error" for f in result.findings)
            or any(not p.ok for p in probes)
            else 0
        )
    if args.command == "report":
        result, probes, reports = _probe_budget(
            args.root, args.home, args.timeout, args.budget, args.task
        )
        root = Path(args.root).resolve()
        evidence_cache = _evidence_cache_statuses(
            root, result, tuple(probes), args.cache
        )
        context_budget = (
            plan_context_budget(
                root,
                config_sources=result.sources,
                budget_tokens=args.context_budget,
                fallback_instruction_names=tuple(args.fallback_instruction),
            )
            if args.context_budget is not None
            else None
        )
        instruction_routes = (
            route_instruction_sections(
                root,
                task_query=args.task or "",
                fallback_instruction_names=tuple(args.fallback_instruction),
                include_guidance_sources=args.include_guidance,
                include_nested_instructions=args.include_nested_instructions,
            )
            if args.route_instructions
            or args.compress_instructions
            or args.order_evidence
            else None
        )
        prompt_compression = (
            compress_instruction_routes(instruction_routes)
            if (args.compress_instructions or args.order_evidence)
            and instruction_routes is not None
            else None
        )
        evidence_order = (
            order_prompt_evidence(prompt_compression)
            if args.order_evidence and prompt_compression is not None
            else None
        )
        schema_digests = _schema_digests(probes, reports) if args.schema_digest else ()
        orchestration_advice = (
            plan_orchestration_advice(args.task or "", result)
            if args.orchestration_advice
            else None
        )
        report = build_diagnostic_report(
            result,
            tuple(probes),
            tuple(reports),
            evidence_cache=tuple(evidence_cache),
            context_budget=context_budget,
            instruction_routes=instruction_routes,
            prompt_compression=prompt_compression,
            evidence_order=evidence_order,
            tool_schema_digests=tuple(schema_digests),
            orchestration_advice=orchestration_advice,
        )
        if args.active_retrieval is not None:
            active_retrieval = plan_active_retrieval(
                report,
                original_task=args.task or "",
                max_iterations=args.active_retrieval,
            )
            report = build_diagnostic_report(
                result,
                tuple(probes),
                tuple(reports),
                evidence_cache=tuple(evidence_cache),
                context_budget=context_budget,
                instruction_routes=instruction_routes,
                prompt_compression=prompt_compression,
                evidence_order=evidence_order,
                active_retrieval=active_retrieval,
                tool_schema_digests=tuple(schema_digests),
                orchestration_advice=orchestration_advice,
            )
        print(json.dumps(asdict(report), indent=2, ensure_ascii=False, default=str))
        return 0 if report.status == "sufficient" else 1
    if args.command == "eval":
        report = evaluate_token_budget(
            Path(args.root).resolve(),
            task_query=args.task,
            fallback_instruction_names=tuple(args.fallback_instruction),
            include_guidance_sources=args.include_guidance,
            include_nested_instructions=args.include_nested_instructions,
        )
        print(json.dumps(asdict(report), indent=2, ensure_ascii=False, default=str))
        return 0 if not report.regressions else 1
    if args.command == "benchmark":
        task_queries = tuple(args.task) if args.task else DEFAULT_BENCHMARK_TASKS
        report = build_benchmark_report(
            Path(args.repos_dir).resolve(),
            task_queries=task_queries,
            fallback_instruction_names=tuple(args.fallback_instruction),
            include_guidance_sources=args.include_guidance,
            include_nested_instructions=args.include_nested_instructions,
            repo_commits_path=Path(args.repo_commits).resolve()
            if args.repo_commits
            else None,
        )
        if args.json_out:
            Path(args.json_out).write_text(
                json.dumps(report, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        if args.markdown_out:
            Path(args.markdown_out).write_text(
                render_markdown_report(report), encoding="utf-8"
            )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    return 2


def _probe_budget(
    root: str,
    home_value: str | None,
    timeout: float,
    budget: int,
    task_query: str | None = None,
):
    home = Path(home_value) if home_value else None
    result = scan_configs(Path(root).resolve(), home)
    probes = _probe_servers(result.servers, timeout)
    reports = [
        analyze_tool_budget(p.server, p.tools, budget, task_query)
        for p in probes
        if p.ok
    ]
    return result, probes, reports


def _probe_servers(servers, timeout: float):
    stdio_probe = StdioMcpProbe(timeout_sec=timeout)
    http_probe = HttpMcpProbe(timeout_sec=timeout)
    probes = []
    for server in servers:
        if not server.enabled:
            continue
        if server.url and not server.command:
            probes.append(http_probe.probe(server))
        else:
            probes.append(stdio_probe.probe(server))
    return probes


def _schema_digests(probes, reports):
    report_by_server = {report.server.server_id: report for report in reports}
    return tuple(
        digest_tool_schemas(
            probe.server, probe.tools, report_by_server.get(probe.server.server_id)
        )
        for probe in probes
        if probe.ok
    )


def _schema_digest_payload(digest):
    return {
        "server_id": digest.server.server_id,
        "total_tools": digest.total_tools,
        "total_full_schema_tokens": digest.total_full_schema_tokens,
        "total_digest_tokens": digest.total_digest_tokens,
        "saved_tokens": digest.saved_tokens,
        "compression_ratio": digest.compression_ratio,
        "method": digest.method,
        "missing_facts": list(digest.missing_facts),
        "items": [
            {
                "name": item.name,
                "description": item.description,
                "required_inputs": list(item.required_inputs),
                "risk_markers": list(item.risk_markers),
                "full_schema_ref": item.full_schema_ref,
                "full_schema_tokens": item.full_schema_tokens,
                "digest_tokens": item.digest_tokens,
                "saved_tokens": item.saved_tokens,
                "missing_details": list(item.missing_details),
                "relevance_score": item.relevance_score,
                "matched_terms": list(item.matched_terms),
            }
            for item in digest.items
        ],
    }


def _evidence_cache_statuses(root: Path, scan_result, probes, cache_path: str | None):
    cache = load_summary_cache(Path(cache_path)) if cache_path else {}
    statuses = []
    for source in scan_result.sources:
        statuses.append(
            lookup_cached_summary(
                cache, fingerprint_file(source.path, kind="client-config")
            )
        )
    for path in _instruction_candidates(root):
        if path.exists():
            statuses.append(
                lookup_cached_summary(
                    cache, fingerprint_file(path, kind="instructions")
                )
            )
    for probe in probes:
        if probe.ok:
            statuses.append(
                lookup_cached_summary(
                    cache, fingerprint_tools(probe.server, probe.tools)
                )
            )
    return tuple(statuses)


def _instruction_candidates(root: Path) -> tuple[Path, ...]:
    return (
        root / "AGENTS.override.md",
        root / "AGENTS.md",
    )


if __name__ == "__main__":
    raise SystemExit(main())
