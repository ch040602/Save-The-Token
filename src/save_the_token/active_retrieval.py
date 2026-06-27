from __future__ import annotations

from .models import ActiveRetrievalReport, ActiveRetrievalStep, DiagnosticReport


def plan_active_retrieval(
    report: DiagnosticReport,
    original_task: str,
    max_iterations: int,
) -> ActiveRetrievalReport:
    bounded_iterations = max(0, max_iterations)
    if report.status == "sufficient":
        return ActiveRetrievalReport(
            original_task=original_task,
            max_iterations=bounded_iterations,
            steps=(),
            stop_reason="sufficient",
            final_status="sufficient",
        )
    if report.status == "unanswerable":
        return ActiveRetrievalReport(
            original_task=original_task,
            max_iterations=bounded_iterations,
            steps=(),
            stop_reason="unanswerable",
            final_status="unanswerable",
        )
    if bounded_iterations == 0:
        return ActiveRetrievalReport(
            original_task=original_task,
            max_iterations=bounded_iterations,
            steps=(),
            stop_reason="iteration_budget_exhausted",
            final_status=report.status,
        )

    missing_facts = tuple(dict.fromkeys(report.missing_facts))
    steps = tuple(
        ActiveRetrievalStep(
            iteration=index + 1,
            original_task=original_task,
            missing_fact=fact,
            follow_up_query=_follow_up_query(fact),
            target_corpus=_target_corpus(fact),
            retrieved_evidence_ids=_retrieved_evidence_ids(
                report, _target_corpus(fact)
            ),
            status_after_iteration=report.status,
        )
        for index, fact in enumerate(missing_facts[:bounded_iterations])
    )
    return ActiveRetrievalReport(
        original_task=original_task,
        max_iterations=bounded_iterations,
        steps=steps,
        stop_reason=(
            "iteration_budget_exhausted"
            if report.status != "sufficient" and len(steps) >= bounded_iterations
            else "awaiting_external_evidence"
        ),
        final_status=report.status,
    )


def _target_corpus(missing_fact: str) -> str:
    normalized = missing_fact.lower()
    if "runtime probe" in normalized:
        return "runtime"
    if "tool budget" in normalized or "tools/list" in normalized:
        return "tools"
    if "instruction" in normalized:
        return "instructions"
    if "compression" in normalized or "compressed" in normalized:
        return "prompt-compression"
    if "ordering" in normalized or "evidence order" in normalized:
        return "evidence-order"
    if "config" in normalized or "mcp server entry" in normalized:
        return "client-config"
    return "diagnostic"


def _follow_up_query(missing_fact: str) -> str:
    corpus = _target_corpus(missing_fact)
    if corpus == "runtime":
        return "Run `save-the-token doctor` against the configured MCP server."
    if corpus == "tools":
        return "Run `save-the-token tools` after a successful runtime probe."
    if corpus == "instructions":
        return 'Run `save-the-token report --route-instructions --task "..."` with a narrower task or fallback instruction file.'
    if corpus == "prompt-compression":
        return 'Run `save-the-token report --compress-instructions --task "..."` after instruction routing selects sections.'
    if corpus == "evidence-order":
        return 'Run `save-the-token report --order-evidence --task "..."` after compression yields evidence.'
    if corpus == "client-config":
        return (
            "Fix or add a supported MCP config file, then rerun `save-the-token scan`."
        )
    return f"Retrieve targeted evidence for missing fact: {missing_fact}"


def _retrieved_evidence_ids(
    report: DiagnosticReport, target_corpus: str
) -> tuple[str, ...]:
    prefixes = _corpus_prefixes(target_corpus)
    return tuple(
        evidence.id
        for evidence in report.evidence
        if any(
            evidence.corpus == prefix or evidence.corpus.startswith(f"{prefix}:")
            for prefix in prefixes
        )
    )


def _corpus_prefixes(target_corpus: str) -> tuple[str, ...]:
    if target_corpus == "runtime":
        return ("runtime-probe",)
    if target_corpus == "tools":
        return ("tool-budget", "tools")
    if target_corpus == "instructions":
        return (
            "instruction-route",
            "context-budget:instruction",
            "context-budget:instructions",
        )
    if target_corpus == "client-config":
        return ("client-config",)
    return (target_corpus,)
