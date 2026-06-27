from __future__ import annotations

import re

from .models import OrchestrationAdviceReport, OrchestrationRecommendation, ScanResult


def plan_orchestration_advice(
    task_query: str,
    scan: ScanResult,
) -> OrchestrationAdviceReport:
    terms = _tokenize(task_query)
    recommendations: list[OrchestrationRecommendation] = [
        OrchestrationRecommendation(
            category="main-agent",
            recommendation="Use the main agent for local, single-module edits, command execution, and final integration decisions.",
            rationale=_main_agent_rationale(scan, terms),
            token_cost_warning="Lowest orchestration overhead; still requires targeted file reads and validation.",
        )
    ]
    recommendations.extend(_skill_recommendations(terms))
    recommendations.extend(_subagent_recommendations(terms))
    if not any(
        item.category == "skill-progressive-disclosure" for item in recommendations
    ):
        recommendations.append(
            OrchestrationRecommendation(
                category="skill-progressive-disclosure",
                recommendation="Load full skill instructions only after the task clearly matches skill metadata or the user explicitly names the skill.",
                rationale="Progressive disclosure preserves context by keeping skill metadata compact until needed.",
                token_cost_warning="Loading full skill files spends extra context; avoid speculative skill loading.",
            )
        )
    return OrchestrationAdviceReport(
        task_query=task_query,
        recommendations=tuple(recommendations),
    )


def _skill_recommendations(
    terms: frozenset[str],
) -> tuple[OrchestrationRecommendation, ...]:
    mapping = (
        (
            {"security", "secret", "secrets", "auth", "token"},
            "security-and-hardening",
            "security-sensitive implementation or review",
        ),
        (
            {"review", "audit", "quality"},
            "code-review-and-quality",
            "critical review before merge",
        ),
        (
            {"performance", "latency", "speed", "optimize"},
            "performance-optimization",
            "performance-sensitive investigation",
        ),
        (
            {"debug", "bug", "failure", "error"},
            "systematic-debugging",
            "root-cause debugging",
        ),
        (
            {"token", "context", "compression", "budget"},
            "codex-token-thrift",
            "token and context budget reduction",
        ),
    )
    results = []
    for trigger_terms, skill_name, rationale in mapping:
        if terms & trigger_terms:
            results.append(
                OrchestrationRecommendation(
                    category="skill-progressive-disclosure",
                    recommendation=f"Consider loading `${skill_name}` only if the next step needs its full workflow.",
                    rationale=rationale,
                    token_cost_warning="Skill loading consumes context; metadata-level routing should happen first.",
                )
            )
    return tuple(results)


def _subagent_recommendations(
    terms: frozenset[str],
) -> tuple[OrchestrationRecommendation, ...]:
    results = []
    broad = bool(
        terms
        & {
            "whole",
            "codebase",
            "repository",
            "repo",
            "broad",
            "migration",
            "cross",
            "audit",
        }
    )
    if broad:
        results.append(
            _subagent(
                "explorer",
                "Ask Codex to spawn an explorer subagent when independent broad codebase discovery is worth the extra context.",
                "The task appears broad or cross-cutting.",
            )
        )
    if terms & {"review", "audit", "quality"}:
        results.append(
            _subagent(
                "review",
                "Ask Codex to spawn a review subagent for independent blocker/high-risk critique after implementation.",
                "The task asks for review or quality assessment.",
            )
        )
    if terms & {"security", "secret", "secrets", "auth", "token", "permission"}:
        results.append(
            _subagent(
                "security",
                "Ask Codex to spawn a security subagent for independent security critique when secrets, auth, or permissions are in scope.",
                "The task includes security-sensitive terms.",
            )
        )
    return tuple(results)


def _subagent(
    role: str, recommendation: str, rationale: str
) -> OrchestrationRecommendation:
    return OrchestrationRecommendation(
        category="explicit-subagent-request",
        recommendation=f"{role}: {recommendation}",
        rationale=rationale,
        token_cost_warning="Subagents consume additional tokens because each performs separate model and tool work; request them explicitly only when independent review is worth the cost.",
        auto_spawn=False,
    )


def _main_agent_rationale(scan: ScanResult, terms: frozenset[str]) -> str:
    if not scan.servers:
        return "No MCP server entries are available, so the main agent should first resolve local config evidence."
    if terms & {"small", "local", "single", "fix"}:
        return "The task appears local enough for main-agent execution and validation."
    return "The main agent should keep final decision authority and coordinate any optional skills or subagent requests."


def _tokenize(text: str) -> frozenset[str]:
    terms = re.findall(r"[a-z0-9]+", text.lower().replace("_", " "))
    stop_words = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}
    return frozenset(term for term in terms if len(term) > 1 and term not in stop_words)
