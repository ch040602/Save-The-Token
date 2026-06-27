from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ConfigSource:
    path: Path
    client: str
    scope: str


@dataclass(frozen=True)
class McpServerConfig:
    source: ConfigSource
    server_id: str
    command: str | None = None
    args: tuple[str, ...] = ()
    url: str | None = None
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    enabled_tools: tuple[str, ...] = ()
    disabled_tools: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfigFinding:
    severity: str
    code: str
    message: str
    source: str
    server_id: str | None = None


@dataclass(frozen=True)
class ScanResult:
    sources: tuple[ConfigSource, ...]
    servers: tuple[McpServerConfig, ...]
    findings: tuple[ConfigFinding, ...]


@dataclass(frozen=True)
class ToolSchema:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProbeResult:
    server: McpServerConfig
    ok: bool
    initialized: bool = False
    tools: tuple[ToolSchema, ...] = ()
    error: str | None = None
    stderr: str = ""


@dataclass(frozen=True)
class ToolBudgetItem:
    name: str
    schema_chars: int
    estimated_tokens: int
    relevance_score: int = 0
    matched_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolBudgetReport:
    server: McpServerConfig
    total_tools: int
    total_schema_chars: int
    estimated_tokens: int
    budget_tokens: int
    over_budget: bool
    items: tuple[ToolBudgetItem, ...]
    recommended_enabled_tools: tuple[str, ...]
    codex_toml_snippet: str
    client_snippet_format: str
    client_snippet: str


@dataclass(frozen=True)
class ToolSchemaDigestItem:
    name: str
    description: str
    required_inputs: tuple[str, ...]
    risk_markers: tuple[str, ...]
    full_schema_ref: str
    full_schema_tokens: int
    digest_tokens: int
    saved_tokens: int
    missing_details: tuple[str, ...]
    relevance_score: int = 0
    matched_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolSchemaDigestReport:
    server: McpServerConfig
    total_tools: int
    total_full_schema_tokens: int
    total_digest_tokens: int
    saved_tokens: int
    compression_ratio: float
    items: tuple[ToolSchemaDigestItem, ...]
    method: str = "deterministic-schema-digest"
    missing_facts: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceFingerprint:
    source: str
    kind: str
    size_bytes: int
    estimated_tokens: int
    sha256: str
    mtime_ns: int | None = None

    @property
    def cache_key(self) -> str:
        return f"{self.kind}:{self.source}:{self.sha256}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "kind": self.kind,
            "size_bytes": self.size_bytes,
            "estimated_tokens": self.estimated_tokens,
            "sha256": self.sha256,
            "mtime_ns": self.mtime_ns,
            "cache_key": self.cache_key,
        }


@dataclass(frozen=True)
class EvidenceCacheStatus:
    fingerprint: EvidenceFingerprint
    cache_hit: bool
    cached_summary: str | None = None
    cached_estimated_tokens: int | None = None


@dataclass(frozen=True)
class ContextBudgetItem:
    source: str
    kind: str
    size_bytes: int
    estimated_tokens: int
    selected: bool
    reason: str
    priority: int


@dataclass(frozen=True)
class ContextBudgetReport:
    budget_tokens: int
    total_estimated_tokens: int
    selected_tokens: int
    skipped_tokens: int
    selected: tuple[ContextBudgetItem, ...]
    skipped: tuple[ContextBudgetItem, ...]
    missing_facts: tuple[str, ...]
    preserves_orchestrator_baseline: bool = True


@dataclass(frozen=True)
class InstructionSection:
    source: str
    heading_path: str
    byte_start: int
    byte_end: int
    estimated_tokens: int
    matched_terms: tuple[str, ...]
    selected: bool
    reason: str
    snippet: str = ""
    source_kind: str = "orchestrator-instruction"
    scope_path: str = "."
    scope_depth: int = 0


@dataclass(frozen=True)
class InstructionRouteLineage:
    original_task: str
    source: str
    heading_path: str
    selected: bool
    reason: str
    matched_terms: tuple[str, ...]
    source_kind: str = "orchestrator-instruction"
    scope_path: str = "."
    scope_depth: int = 0


@dataclass(frozen=True)
class InstructionRouteReport:
    original_task: str
    selected_sections: tuple[InstructionSection, ...]
    skipped_sections: tuple[InstructionSection, ...]
    lineage: tuple[InstructionRouteLineage, ...]
    missing_facts: tuple[str, ...]
    preserves_orchestrator_baseline: bool = True


@dataclass(frozen=True)
class CompressionItem:
    citation_id: str
    source: str
    heading_path: str
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    required_facts_preserved: bool
    preserved_terms: tuple[str, ...]
    compressed_text: str


@dataclass(frozen=True)
class PromptCompressionReport:
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    items: tuple[CompressionItem, ...]
    missing_facts: tuple[str, ...]
    method: str = "deterministic-extractive"
    dependency_policy: str = "no model dependency"


@dataclass(frozen=True)
class EvidenceOrderItem:
    rank: int
    placement: str
    citation_id: str
    source: str
    heading_path: str
    priority_score: int
    recency_ns: int
    rationale: str
    compressed_tokens: int
    compressed_text: str


@dataclass(frozen=True)
class EvidenceOrderReport:
    ordered_items: tuple[EvidenceOrderItem, ...]
    lead_digest: str
    ordering_rationale: str
    missing_facts: tuple[str, ...]


@dataclass(frozen=True)
class ActiveRetrievalStep:
    iteration: int
    original_task: str
    missing_fact: str
    follow_up_query: str
    target_corpus: str
    retrieved_evidence_ids: tuple[str, ...]
    status_after_iteration: str


@dataclass(frozen=True)
class ActiveRetrievalReport:
    original_task: str
    max_iterations: int
    steps: tuple[ActiveRetrievalStep, ...]
    stop_reason: str
    final_status: str
    preserves_insufficient_draft: bool = True


@dataclass(frozen=True)
class TokenEvaluationVariant:
    name: str
    estimated_tokens: int
    selected_evidence_recall: float
    missing_fact_count: int
    sufficiency_status: str
    preserved_terms: tuple[str, ...]
    missing_terms: tuple[str, ...]


@dataclass(frozen=True)
class TokenEvaluationReport:
    task_query: str
    required_terms: tuple[str, ...]
    variants: tuple[TokenEvaluationVariant, ...]
    regressions: tuple[str, ...]
    method: str = "deterministic-token-budget-eval"


@dataclass(frozen=True)
class OrchestrationRecommendation:
    category: str
    recommendation: str
    rationale: str
    token_cost_warning: str
    auto_spawn: bool = False


@dataclass(frozen=True)
class OrchestrationAdviceReport:
    task_query: str
    recommendations: tuple[OrchestrationRecommendation, ...]
    preserves_codex_orchestrator: bool = True
    policy: str = (
        "recommend-only; does not spawn subagents or load skills automatically"
    )


@dataclass(frozen=True)
class Evidence:
    id: str
    corpus: str
    source: str
    subject: str
    summary: str
    fingerprint: EvidenceFingerprint | None = None


@dataclass(frozen=True)
class DiagnosticClaim:
    text: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class DiagnosticReport:
    status: str
    claims: tuple[DiagnosticClaim, ...]
    missing_facts: tuple[str, ...]
    feedback_queries: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    evidence_cache: tuple[EvidenceCacheStatus, ...] = ()
    context_budget: ContextBudgetReport | None = None
    instruction_routes: InstructionRouteReport | None = None
    prompt_compression: PromptCompressionReport | None = None
    evidence_order: EvidenceOrderReport | None = None
    active_retrieval: ActiveRetrievalReport | None = None
    tool_schema_digests: tuple[ToolSchemaDigestReport, ...] = ()
    orchestration_advice: OrchestrationAdviceReport | None = None
