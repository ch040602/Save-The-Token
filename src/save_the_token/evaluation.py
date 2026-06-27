from __future__ import annotations

import re
from pathlib import Path

from .evidence_ordering import order_prompt_evidence
from .instruction_routing import route_instruction_sections
from .models import (
    EvidenceOrderReport,
    InstructionRouteReport,
    PromptCompressionReport,
    TokenEvaluationReport,
    TokenEvaluationVariant,
)
from .prompt_compression import compress_instruction_routes


def evaluate_token_budget(
    root: Path,
    task_query: str,
    fallback_instruction_names: tuple[str, ...] = (),
    include_guidance_sources: bool = False,
    include_nested_instructions: bool = False,
) -> TokenEvaluationReport:
    routes = route_instruction_sections(
        root,
        task_query=task_query,
        fallback_instruction_names=fallback_instruction_names,
        include_guidance_sources=include_guidance_sources,
        include_nested_instructions=include_nested_instructions,
    )
    compression = compress_instruction_routes(routes)
    ordering = order_prompt_evidence(compression)
    required_terms = tuple(sorted(_tokenize(task_query)))
    variants = (
        _full_context_variant(routes, required_terms),
        _selected_context_variant(routes, required_terms),
        _compressed_context_variant(compression, required_terms),
        _reordered_context_variant(ordering, compression, required_terms),
    )
    return TokenEvaluationReport(
        task_query=task_query,
        required_terms=required_terms,
        variants=variants,
        regressions=_regressions(variants, required_terms),
    )


def _full_context_variant(
    routes: InstructionRouteReport,
    required_terms: tuple[str, ...],
) -> TokenEvaluationVariant:
    sections = routes.selected_sections + routes.skipped_sections
    text = "\n".join(
        _section_text(section.source, section.byte_start, section.byte_end)
        for section in sections
    )
    return _variant(
        name="full_context",
        estimated_tokens=sum(section.estimated_tokens for section in sections),
        text=text,
        required_terms=required_terms,
        missing_fact_count=0 if sections else 1,
    )


def _selected_context_variant(
    routes: InstructionRouteReport,
    required_terms: tuple[str, ...],
) -> TokenEvaluationVariant:
    text = "\n".join(
        _section_text(section.source, section.byte_start, section.byte_end)
        for section in routes.selected_sections
    )
    return _variant(
        name="selected_context",
        estimated_tokens=sum(
            section.estimated_tokens for section in routes.selected_sections
        ),
        text=text,
        required_terms=required_terms,
        missing_fact_count=len(routes.missing_facts),
    )


def _compressed_context_variant(
    compression: PromptCompressionReport,
    required_terms: tuple[str, ...],
) -> TokenEvaluationVariant:
    text = "\n".join(item.compressed_text for item in compression.items)
    return _variant(
        name="compressed_context",
        estimated_tokens=compression.compressed_tokens,
        text=text,
        required_terms=required_terms,
        missing_fact_count=len(compression.missing_facts),
    )


def _reordered_context_variant(
    ordering: EvidenceOrderReport,
    compression: PromptCompressionReport,
    required_terms: tuple[str, ...],
) -> TokenEvaluationVariant:
    text = "\n".join(
        (ordering.lead_digest,)
        + tuple(item.compressed_text for item in ordering.ordered_items)
    )
    return _variant(
        name="reordered_context",
        estimated_tokens=compression.compressed_tokens
        + _estimate_tokens(len(ordering.lead_digest)),
        text=text,
        required_terms=required_terms,
        missing_fact_count=len(
            tuple(dict.fromkeys(compression.missing_facts + ordering.missing_facts))
        ),
    )


def _variant(
    name: str,
    estimated_tokens: int,
    text: str,
    required_terms: tuple[str, ...],
    missing_fact_count: int,
) -> TokenEvaluationVariant:
    text_terms = _tokenize(text)
    preserved = tuple(term for term in required_terms if term in text_terms)
    missing = tuple(term for term in required_terms if term not in text_terms)
    recall = (
        1.0 if not required_terms else round(len(preserved) / len(required_terms), 4)
    )
    return TokenEvaluationVariant(
        name=name,
        estimated_tokens=estimated_tokens,
        selected_evidence_recall=recall,
        missing_fact_count=missing_fact_count,
        sufficiency_status="sufficient"
        if recall == 1.0 and missing_fact_count == 0
        else "insufficient",
        preserved_terms=preserved,
        missing_terms=missing,
    )


def _regressions(
    variants: tuple[TokenEvaluationVariant, ...],
    required_terms: tuple[str, ...],
) -> tuple[str, ...]:
    if not variants or not required_terms:
        return ()
    full = variants[0]
    if full.selected_evidence_recall < 1.0:
        return ()
    regressions = []
    for variant in variants[1:]:
        if variant.selected_evidence_recall < 1.0:
            regressions.append(
                f"{variant.name} dropped required task terms: {list(variant.missing_terms)}"
            )
        if (
            variant.missing_fact_count > full.missing_fact_count
            and variant.sufficiency_status != "sufficient"
        ):
            regressions.append(
                f"{variant.name} introduced {variant.missing_fact_count} missing fact(s)."
            )
    return tuple(dict.fromkeys(regressions))


def _section_text(source: str, byte_start: int, byte_end: int) -> str:
    path = Path(source)
    if not path.exists():
        return ""
    return path.read_bytes()[byte_start:byte_end].decode("utf-8", errors="replace")


def _tokenize(text: str) -> frozenset[str]:
    stop_words = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}
    terms = re.findall(r"[a-z0-9]+", text.lower().replace("_", " "))
    return frozenset(term for term in terms if len(term) > 1 and term not in stop_words)


def _estimate_tokens(chars: int) -> int:
    return max(1, (chars + 3) // 4)
