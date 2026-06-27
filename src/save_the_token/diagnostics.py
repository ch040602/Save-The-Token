from __future__ import annotations

from .models import (
    ActiveRetrievalReport,
    ContextBudgetReport,
    DiagnosticClaim,
    DiagnosticReport,
    Evidence,
    EvidenceCacheStatus,
    EvidenceFingerprint,
    EvidenceOrderReport,
    InstructionRouteReport,
    PromptCompressionReport,
    ProbeResult,
    OrchestrationAdviceReport,
    ScanResult,
    ToolBudgetReport,
    ToolSchemaDigestReport,
)


def build_diagnostic_report(
    scan: ScanResult,
    probes: tuple[ProbeResult, ...],
    budgets: tuple[ToolBudgetReport, ...],
    evidence_cache: tuple[EvidenceCacheStatus, ...] = (),
    context_budget: ContextBudgetReport | None = None,
    instruction_routes: InstructionRouteReport | None = None,
    prompt_compression: PromptCompressionReport | None = None,
    evidence_order: EvidenceOrderReport | None = None,
    active_retrieval: ActiveRetrievalReport | None = None,
    tool_schema_digests: tuple[ToolSchemaDigestReport, ...] = (),
    orchestration_advice: OrchestrationAdviceReport | None = None,
) -> DiagnosticReport:
    evidence_builder = _EvidenceBuilder()
    claims: list[DiagnosticClaim] = []
    missing_facts: list[str] = []
    cache_by_key = {
        (status.fingerprint.kind, status.fingerprint.source): status
        for status in evidence_cache
    }

    source_evidence_ids = []
    for source in scan.sources:
        cache_status = cache_by_key.get(("client-config", str(source.path.resolve())))
        source_evidence_ids.append(
            evidence_builder.add(
                corpus="client-config",
                source=str(source.path),
                subject=f"{source.client}:{source.scope}",
                summary=_cache_summary(
                    "Supported MCP config source discovered.",
                    cache_status,
                ),
                fingerprint=cache_status.fingerprint if cache_status else None,
            )
        )
    if source_evidence_ids:
        claims.append(
            DiagnosticClaim(
                text=f"Found {len(source_evidence_ids)} supported MCP config source(s).",
                evidence_ids=tuple(source_evidence_ids),
            )
        )
    else:
        missing_facts.append("No supported MCP config source was found.")

    for finding in scan.findings:
        finding_id = evidence_builder.add(
            corpus="client-config",
            source=finding.source,
            subject=finding.server_id or "global",
            summary=f"{finding.severity}:{finding.code}: {finding.message}",
        )
        claims.append(
            DiagnosticClaim(
                text=f"Config finding {finding.code}: {finding.message}",
                evidence_ids=(finding_id,),
            )
        )
        if finding.severity == "error":
            missing_facts.append(
                f"Resolvable config evidence is missing because {finding.message}"
            )

    if scan.sources and not scan.servers:
        missing_facts.append(
            "No MCP server entry was found in supported config sources."
        )

    if context_budget is not None:
        selected_ids = [
            evidence_builder.add(
                corpus=f"context-budget:{item.kind}",
                source=item.source,
                subject="selected",
                summary=(
                    f"selected=True, estimated_tokens={item.estimated_tokens}, "
                    f"reason={item.reason}."
                ),
            )
            for item in context_budget.selected
        ]
        skipped_ids = [
            evidence_builder.add(
                corpus=f"context-budget:{item.kind}",
                source=item.source,
                subject="skipped",
                summary=(
                    f"selected=False, estimated_tokens={item.estimated_tokens}, "
                    f"reason={item.reason}."
                ),
            )
            for item in context_budget.skipped
        ]
        claims.append(
            DiagnosticClaim(
                text=(
                    f"Context budget selected {len(context_budget.selected)} item(s) "
                    f"and skipped {len(context_budget.skipped)} item(s) while preserving "
                    "the orchestrator instruction baseline."
                ),
                evidence_ids=tuple(selected_ids + skipped_ids),
            )
        )
        missing_facts.extend(context_budget.missing_facts)

    if instruction_routes is not None:
        route_ids = [
            evidence_builder.add(
                corpus="instruction-route",
                source=section.source,
                subject=section.heading_path,
                summary=(
                    f"selected={section.selected}, matched_terms={list(section.matched_terms)}, "
                    f"reason={section.reason}, estimated_tokens={section.estimated_tokens}."
                ),
            )
            for section in instruction_routes.selected_sections
            + instruction_routes.skipped_sections
        ]
        claims.append(
            DiagnosticClaim(
                text=(
                    f"Instruction routing selected {len(instruction_routes.selected_sections)} "
                    f"section(s) and skipped {len(instruction_routes.skipped_sections)} section(s) "
                    "after preserving the orchestrator instruction baseline."
                ),
                evidence_ids=tuple(route_ids),
            )
        )
        missing_facts.extend(instruction_routes.missing_facts)

    if prompt_compression is not None:
        compression_ids = [
            evidence_builder.add(
                corpus="prompt-compression",
                source=item.source,
                subject=item.citation_id,
                summary=(
                    f"{item.heading_path}: {item.original_tokens}->{item.compressed_tokens} "
                    f"tokens, ratio={item.compression_ratio}, "
                    f"required_facts_preserved={item.required_facts_preserved}."
                ),
            )
            for item in prompt_compression.items
        ]
        claims.append(
            DiagnosticClaim(
                text=(
                    f"Prompt compression reduced selected instruction evidence from "
                    f"{prompt_compression.original_tokens} to "
                    f"{prompt_compression.compressed_tokens} estimated tokens "
                    f"(ratio={prompt_compression.compression_ratio})."
                ),
                evidence_ids=tuple(compression_ids),
            )
        )
        missing_facts.extend(prompt_compression.missing_facts)

    if evidence_order is not None:
        order_ids = [
            evidence_builder.add(
                corpus="evidence-order",
                source=item.source,
                subject=item.citation_id,
                summary=(
                    f"rank={item.rank}, placement={item.placement}, "
                    f"priority_score={item.priority_score}, rationale={item.rationale}."
                ),
            )
            for item in evidence_order.ordered_items
        ]
        claims.append(
            DiagnosticClaim(
                text=(
                    f"Evidence ordering placed {len(evidence_order.ordered_items)} item(s) "
                    "with a lead digest to reduce lost-in-the-middle risk."
                ),
                evidence_ids=tuple(order_ids),
            )
        )
        missing_facts.extend(evidence_order.missing_facts)

    if active_retrieval is not None:
        summary_id = evidence_builder.add(
            corpus="active-retrieval",
            source="planner",
            subject=active_retrieval.stop_reason,
            summary=(
                f"steps={len(active_retrieval.steps)}, "
                f"max_iterations={active_retrieval.max_iterations}, "
                f"final_status={active_retrieval.final_status}, "
                f"preserves_insufficient_draft={active_retrieval.preserves_insufficient_draft}."
            ),
        )
        active_ids = [
            evidence_builder.add(
                corpus="active-retrieval",
                source=step.target_corpus,
                subject=step.missing_fact,
                summary=(
                    f"iteration={step.iteration}, query={step.follow_up_query}, "
                    f"retrieved_evidence_ids={list(step.retrieved_evidence_ids)}, "
                    f"status_after_iteration={step.status_after_iteration}."
                ),
            )
            for step in active_retrieval.steps
        ]
        claims.append(
            DiagnosticClaim(
                text=(
                    f"Active retrieval planned {len(active_retrieval.steps)} follow-up "
                    f"step(s) and stopped because {active_retrieval.stop_reason}."
                ),
                evidence_ids=tuple([summary_id] + active_ids),
            )
        )

    if tool_schema_digests:
        digest_ids = []
        for digest in tool_schema_digests:
            digest_ids.append(
                evidence_builder.add(
                    corpus="tool-schema-digest",
                    source=str(digest.server.source.path),
                    subject=digest.server.server_id,
                    summary=(
                        f"{digest.total_tools} tool digest(s), "
                        f"{digest.total_full_schema_tokens}->{digest.total_digest_tokens} "
                        f"tokens, saved={digest.saved_tokens}, ratio={digest.compression_ratio}."
                    ),
                )
            )
            missing_facts.extend(digest.missing_facts)
        claims.append(
            DiagnosticClaim(
                text=(
                    f"Tool schema digest reduced {sum(d.total_tools for d in tool_schema_digests)} "
                    "tool schema record(s) while preserving full schema references."
                ),
                evidence_ids=tuple(digest_ids),
            )
        )

    if orchestration_advice is not None:
        advice_ids = [
            evidence_builder.add(
                corpus="orchestration-advice",
                source=item.category,
                subject=item.recommendation.split(":", 1)[0],
                summary=(
                    f"auto_spawn={item.auto_spawn}, rationale={item.rationale}, "
                    f"token_cost_warning={item.token_cost_warning}"
                ),
            )
            for item in orchestration_advice.recommendations
        ]
        claims.append(
            DiagnosticClaim(
                text=(
                    f"Orchestration advice produced {len(orchestration_advice.recommendations)} "
                    "recommendation(s) without spawning subagents or overriding Codex."
                ),
                evidence_ids=tuple(advice_ids),
            )
        )

    probes_by_server = {probe.server.server_id: probe for probe in probes}
    budgets_by_server = {budget.server.server_id: budget for budget in budgets}
    for server in scan.servers:
        if not server.enabled:
            continue
        probe = probes_by_server.get(server.server_id)
        if probe is None:
            missing_facts.append(
                f"Runtime probe evidence is missing for {server.server_id}."
            )
            continue

        probe_id = evidence_builder.add(
            corpus="runtime-probe",
            source=str(server.source.path),
            subject=server.server_id,
            summary=_probe_summary(probe),
        )
        claims.append(
            DiagnosticClaim(
                text=(
                    f"Server {server.server_id} runtime probe "
                    f"{'succeeded' if probe.ok else 'failed'}."
                ),
                evidence_ids=(probe_id,),
            )
        )
        if not probe.ok:
            missing_facts.append(
                f"Successful runtime probe evidence is missing for {server.server_id}."
            )
            continue

        budget = budgets_by_server.get(server.server_id)
        if budget is None:
            missing_facts.append(
                f"Tool budget evidence is missing for {server.server_id}."
            )
            continue

        budget_id = evidence_builder.add(
            corpus="tool-budget",
            source=str(server.source.path),
            subject=server.server_id,
            summary=(
                f"{budget.total_tools} tool(s), {budget.estimated_tokens}/"
                f"{budget.budget_tokens} estimated tokens, over_budget={budget.over_budget}."
            ),
            fingerprint=_tool_fingerprint(
                evidence_cache, server.source.path, server.server_id
            ),
        )
        claims.append(
            DiagnosticClaim(
                text=(
                    f"Server {server.server_id} exposes {budget.total_tools} tool(s) "
                    f"at about {budget.estimated_tokens}/{budget.budget_tokens} schema tokens."
                ),
                evidence_ids=(probe_id, budget_id),
            )
        )

    return DiagnosticReport(
        status=_status(scan, tuple(missing_facts)),
        claims=tuple(claims),
        missing_facts=tuple(dict.fromkeys(missing_facts)),
        feedback_queries=tuple(_feedback_queries(missing_facts)),
        evidence=evidence_builder.items,
        evidence_cache=evidence_cache,
        context_budget=context_budget,
        instruction_routes=instruction_routes,
        prompt_compression=prompt_compression,
        evidence_order=evidence_order,
        active_retrieval=active_retrieval,
        tool_schema_digests=tool_schema_digests,
        orchestration_advice=orchestration_advice,
    )


def _status(scan: ScanResult, missing_facts: tuple[str, ...]) -> str:
    if not scan.sources or (scan.sources and not scan.servers):
        return "unanswerable"
    if missing_facts:
        return "insufficient"
    return "sufficient"


def _feedback_queries(missing_facts: list[str]) -> list[str]:
    queries: list[str] = []
    for fact in dict.fromkeys(missing_facts):
        if fact.startswith("Runtime probe evidence"):
            queries.append(
                "Run `save-the-token doctor` against the configured MCP server."
            )
        elif fact.startswith("Tool budget evidence"):
            queries.append(
                "Run `save-the-token tools` after a successful runtime probe."
            )
        elif "config" in fact.lower():
            queries.append(
                "Fix or add a supported MCP config file, then rerun `save-the-token scan`."
            )
        elif "instruction" in fact.lower():
            queries.append(
                "Increase `--context-budget` or add a narrower instruction routing task."
            )
    return list(dict.fromkeys(queries))


def _probe_summary(probe: ProbeResult) -> str:
    if probe.ok:
        return f"initialized={probe.initialized}, tools={len(probe.tools)}."
    return f"error={probe.error or 'unknown error'}."


class _EvidenceBuilder:
    def __init__(self) -> None:
        self._items: list[Evidence] = []

    @property
    def items(self) -> tuple[Evidence, ...]:
        return tuple(self._items)

    def add(
        self,
        corpus: str,
        source: str,
        subject: str,
        summary: str,
        fingerprint: EvidenceFingerprint | None = None,
    ) -> str:
        evidence_id = f"E{len(self._items) + 1}"
        self._items.append(
            Evidence(
                id=evidence_id,
                corpus=corpus,
                source=source,
                subject=subject,
                summary=summary,
                fingerprint=fingerprint,
            )
        )
        return evidence_id


def _cache_summary(base: str, status: EvidenceCacheStatus | None) -> str:
    if status is None:
        return base
    if status.cache_hit:
        return f"{base} Evidence cache hit for unchanged source."
    return f"{base} Evidence cache miss; current fingerprint is reported."


def _tool_fingerprint(
    evidence_cache: tuple[EvidenceCacheStatus, ...],
    source_path,
    server_id: str,
) -> EvidenceFingerprint | None:
    prefix = f"{source_path.resolve()}#{server_id}/tools-list"
    for status in evidence_cache:
        if status.fingerprint.kind == "tools" and status.fingerprint.source == prefix:
            return status.fingerprint
    return None
