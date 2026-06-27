# Agentic RAG Diagnostic Design

Save-The-Token applies an Agentic RAG diagnostic loop to MCP configuration and tool budget problems.

## Evidence Corpora

- `client-config`: Codex `config.toml`, Claude Code `.mcp.json` and `~/.claude.json`, Claude Desktop `claude_desktop_config.json`, VS Code `mcp.json`, Cursor `mcp.json`.
- `runtime`: stdio process startup, Streamable HTTP POST, `initialize`, stderr, HTTP status, exit code.
- `tools`: `tools/list` response, tool names, descriptions, `inputSchema`, `outputSchema`.
- `tool-schema-digest`: compact tool schema summaries with required inputs, risk markers, full schema refs, savings, and omitted-detail notes.
- `policy`: existing `enabled_tools`, `disabled_tools`, HTTP headers, timeout, redaction, and approval settings.
- `client-docs`: MCP specification and client configuration references.
- `evidence-cache`: fingerprints, token estimates, and optional cached summaries for unchanged config, instruction, and tool evidence.
- `context-budget`: selected and skipped config/instruction evidence measured by bytes and estimated tokens.
- `instruction-route`: Markdown sections selected or skipped from root-level and opt-in nested instruction files with task-query and scope lineage.
- `prompt-compression`: deterministic extractive compression records for selected instruction evidence.
- `evidence-order`: compressed evidence ordered by safety/task priority, citation availability, recency, and stable tie-breakers.
- `active-retrieval`: bounded missing-fact follow-up trace with target corpus, query, existing evidence ids, stop reason, and final status.
- `token-evaluation`: deterministic comparison of full, selected, compressed, and reordered instruction-evidence variants.
- `benchmark-report`: strict aggregate JSON/Markdown report over local repo-task cases.
- `orchestration-advice`: recommend-only guidance for main-agent work, progressive skill loading, and explicit subagent requests.

## Loop

1. Plan the required facts for the requested diagnosis.
2. Route each fact to the smallest useful corpus.
3. Retrieve deterministic evidence through parsers and MCP probes.
4. Draft a diagnosis from evidence only.
5. Check sufficiency before emitting a final recommendation.
6. If evidence is insufficient, request targeted follow-up checks.
7. Emit grounded JSON/Markdown reports and config snippets.

## MVP Mapping

- `scan` covers `client-config`, including Claude Code project/user/local MCP configs and Claude Desktop MCP configs.
- `doctor` covers `runtime` and basic `tools` for stdio and Streamable HTTP servers.
- `tools` covers budget analysis over `tools`.
- `tools --task` routes a task query over tool names, descriptions, and schemas before budget trimming.
- `tools --schema-digest` emits compact schema digests without changing task-aware routing.
- `report` performs the sufficient-context judgment over config, runtime, and budget evidence.
- `scan --cache` and `report --cache` mark evidence cache hits and misses without treating a hit as fresh runtime evidence.
- `report --context-budget` plans a secondary context budget for config and instruction evidence while preserving Codex's own instruction chain.
- `report --route-instructions --task "..."` routes instruction sections and reports selected/skipped lineage. Add `--include-nested-instructions` to opt in to bounded nested `AGENTS.md` / `CLAUDE.md` discovery. Add `--include-guidance` to opt in to developer guidance sources.
- `report --compress-instructions --task "..."` compresses routed instruction snippets and reports token savings.
- `report --order-evidence --task "..."` routes, compresses, and orders instruction evidence with a lead digest.
- `report --active-retrieval N --task "..."` plans bounded follow-up retrieval steps from missing facts without changing insufficient status.
- `report --schema-digest` includes tool schema digest evidence in the sufficiency report.
- `report --orchestration-advice` emits recommend-only orchestration guidance without spawning subagents.
- `eval --task "..."` compares token-reduction variants and reports recall/sufficiency regressions. Add `--include-nested-instructions` when nested instruction files should be part of the evaluation corpus.
- `benchmark --repos-dir ...` aggregates strict evaluation across local repo checkouts and reports coverage, savings, regressions, and caveats. Root-only and nested-instruction runs are distinct coverage modes.
- `slim` emits source-client-specific snippets from sufficient tool evidence.

## Report Contract

`report` returns structured JSON:

- `status`: `sufficient`, `insufficient`, or `unanswerable`.
- `claims`: grounded statements, each with `evidence_ids`.
- `missing_facts`: facts needed before a reliable recommendation can be made.
- `feedback_queries`: targeted next commands or checks.
- `evidence`: compact evidence records with corpus, source, subject, and summary.
- `evidence_cache`: fingerprint records with `cache_hit`, optional cached summary, and current token estimate.
- `context_budget`: selected/skipped config and instruction evidence with byte estimates, token estimates, and reasons when `--context-budget` is used.
- `instruction_routes`: selected/skipped Markdown instruction sections, snippets, matched terms, `source_kind`, `scope_path`, `scope_depth`, and lineage when `--route-instructions` is used.
- `prompt_compression`: original tokens, compressed tokens, compression ratio, citation ids, preserved terms, and compressed text when `--compress-instructions` is used.
- `evidence_order`: ordered compressed evidence, lead digest, ordering rationale, placement, priority scores, and missing facts when `--order-evidence` is used.
- `active_retrieval`: bounded follow-up trace with original task, missing fact, follow-up query, target corpus, retrieved evidence ids, stop reason, and final status when `--active-retrieval N` is used.
- `tool_schema_digests`: per-server schema digest reports with required inputs, risk markers, full schema refs, token savings, and omitted details when `--schema-digest` is used.
- `orchestration_advice`: main-agent, skill progressive-disclosure, and explicit subagent request recommendations when `--orchestration-advice` is used.

`eval` returns structured JSON:

- `task_query`: task used for routing and recall checks.
- `required_terms`: lexical task terms that should survive token reduction.
- `variants`: `full_context`, `selected_context`, `compressed_context`, and `reordered_context` metrics.
- `regressions`: token-reduction variants that dropped required terms or introduced missing facts.

`benchmark` returns structured JSON:

- `benchmark_options`: repo directory, task queries, fallback instructions, guidance flag, and optional commit manifest.
- `summary`: total cases, full-context eligible cases, successful reduced cases, success rates, weighted/median saving, and success split by selected versus compressed/reordered variants.
- `rows`: per repo-task metrics including commit, source kinds, token estimates, sufficiency statuses, missing fact counts, regressions, and best sufficient reduction.
- `caveats`: explicit constraints that prevent overclaiming savings from insufficient context.

## Task-Aware Tool Routing

`--task` is the portable MVP version of query planning and routing:

- Planner input: the user task query.
- Corpus: tool name, description, `inputSchema`, and `outputSchema`.
- Retrieval signal: deterministic lexical term overlap with a small stop-word filter.
- Synthesis: recommend matching tools within the token budget and expose `relevance_score` plus `matched_terms`.
- Fallback: if no tool matches the task query, use the existing budget-only recommendation.

## Tool Schema Digest

Tool schema digest mode reduces `tools/list` schema context without removing the full schema path:

- It summarizes each tool as name, shortened description, required input keys, risk markers, and `full_schema_ref`.
- It reports full-schema tokens, digest tokens, saved tokens, and compression ratio.
- It records omitted details such as full `inputSchema`, `outputSchema`, optional inputs, and raw payload data.
- It preserves task-aware routing evidence by carrying `relevance_score` and `matched_terms` from the budget planner.
- It does not automatically invoke tools or discard full schemas; selected tools still point back to their full schema reference.

## Streamable HTTP Runtime Evidence

HTTP probing follows the MCP 2025-11-25 Streamable HTTP transport:

- Send JSON-RPC requests with `Accept: application/json, text/event-stream`.
- Preserve `MCP-Session-Id` returned by `initialize` on subsequent requests.
- Send `MCP-Protocol-Version: 2025-11-25`.
- Parse both `application/json` and `text/event-stream` responses for `tools/list`.
- Forward configured custom headers after filtering unsafe names and values.

## Secret-Safe Evidence

Save-The-Token separates operational evidence from secret values:

- HTTP probes can use configured headers such as `Authorization`.
- `scan` output redacts secret-like values in `env`, `headers`, and nested `raw` config.
- Header names or values containing newline characters are linted.
- MCP-managed headers such as `Accept`, `Content-Type`, `MCP-Protocol-Version`, and `MCP-Session-Id` are controlled by the probe, not by user config.

## Client-Specific Synthesis

Tool recommendations are synthesized in the config dialect of the discovered source:

- Codex sources get TOML snippets under `[mcp_servers.<id>]` with `enabled_tools`.
- VS Code and Cursor `mcp.json` sources get JSON merge snippets under `mcpServers.<id>.enabledTools`.
- Claude Code and Claude Desktop sources currently get a deferred snippet notice because the official Claude MCP config docs do not document an enabled-tool allowlist field.
- The legacy `codex_toml_snippet` remains in JSON output for backward compatibility.

## Evidence Fingerprint Cache

Cache-aware reports reduce repeated context work without storing raw evidence:

- Config and instruction files are fingerprinted by absolute path, byte size, mtime, SHA-256, and estimated tokens.
- `tools/list` evidence is fingerprinted from a stable JSON serialization of tool names, descriptions, schemas, and raw payloads.
- Cache entries are path-scoped, so identical content in a different file does not silently reuse a summary.
- Cache misses are reported explicitly and do not change sufficiency status by themselves.

## Context Budget Planner

The context budget planner is intentionally additive:

- It measures config sources and root-level instruction files before reading their contents.
- It emits selected and skipped evidence records with byte and token estimates.
- It can include fallback instruction filenames through `--fallback-instruction`.
- It marks missing or skipped instruction evidence as a sufficiency gap only when context budgeting is explicitly requested.
- It does not suppress, mutate, or replace Codex's orchestrator-loaded `AGENTS.md` behavior.

## Instruction Routing

Instruction routing is the first section-level token reduction layer:

- It parses root-level `AGENTS.override.md`, `AGENTS.md`, and `--fallback-instruction` files by Markdown headings.
- With `--include-nested-instructions`, it performs bounded traversal for nested `AGENTS.override.md`, `AGENTS.md`, `CLAUDE.md`, and fallback instruction filenames.
- With `--include-guidance`, it also parses exact root-level developer guidance paths: `CONTRIBUTING.md` and `.github/copilot-instructions.md`.
- It selects sections matching the task query and always preserves narrow baseline sections such as safety, security, secrets, permissions, approvals, and sandboxing.
- It records lineage from original task to source file, source kind, scope path, scope depth, heading, selected/skipped status, reason, and matched terms.
- Selected snippets are bounded and secret-like lines are replaced with `<redacted>`.
- Guidance sources are never included by default, preserving the orchestrator baseline and avoiding broad doc loading unless explicitly requested.
- It reports evidence only; it does not unload or replace instructions already handled by Codex.

## Extractive Compression

Prompt compression is deterministic by default:

- It compresses selected instruction sections after routing.
- It preserves citation ids derived from source path, byte span, and heading.
- It keeps headings, warning/requirement lines, command lines, bullets, and task-matched lines.
- It reports original token estimate, compressed token estimate, compression ratio, and whether matched required facts were preserved.
- LLMLingua-style budget-aware compression is treated as inspiration; no model dependency is added by default.

## Evidence Ordering

Evidence ordering reduces the risk that important routed evidence is buried in the middle of a long context:

- It consumes compressed instruction evidence rather than raw instruction files.
- It prioritizes safety/security/permission sections, task-matched facts, warnings, commands, and citation-backed evidence.
- It uses source file mtime as a recency signal after priority and citation need.
- It applies stable source, heading, and citation tie-breakers for reproducible output.
- It emits a lead digest from the highest-ranked items and keeps the full ordered list with rationale.

## Active Retrieval

Active retrieval starts from the Sufficient Context check rather than broad fanout:

- It inspects the draft report's `missing_facts`.
- It maps each missing fact to the smallest target corpus such as `runtime`, `tools`, `instructions`, or `client-config`.
- It emits a concrete follow-up query and any already-present evidence ids for that corpus.
- It enforces `--active-retrieval N` as the iteration budget.
- It preserves the draft status, so an `insufficient` report remains insufficient until new evidence is actually retrieved and the report is rebuilt.

## Token Evaluation

The evaluation harness is a local regression guard:

- It builds full, selected, compressed, and reordered instruction-evidence variants from the same task query.
- It reports estimated tokens, selected evidence recall, missing fact count, preserved terms, missing terms, and sufficiency status.
- It flags regressions when a reduced variant drops required task terms that exist in full context.
- It does not judge semantic answer quality or execute MCP servers.

## Benchmark Report

The benchmark report is a reproducibility layer over token evaluation:

- It scans local repo directories only; it does not clone or fetch repositories.
- It can read a repo/commit JSON manifest so benchmark rows are tied to exact revisions.
- It can write JSON and Markdown reports from the same run.
- It counts savings only when `full_context` is sufficient and the reduced variant is also sufficient.
- It treats insufficient full context as a coverage gap, not as a token-saving result.

## Orchestration Advice

Orchestration advice is deliberately recommend-only:

- It keeps the main agent as final decision-maker.
- It suggests progressive skill loading only when task terms match a skill's domain.
- It suggests asking Codex for explorer, review, or security subagents only for broad, review-heavy, or security-sensitive work.
- It includes token/cost warnings for subagents because each subagent performs separate model and tool work.
- It sets `auto_spawn=false` and does not override Codex's own orchestrator.

## Token Roadmap

Further Agentic RAG work is tracked in `docs/agentic-rag-token-roadmap.md`:

- Claude config discovery.
- Active retrieval.
- Token-budget evaluation.

## Research Basis

- RAG provides the retrieve-then-ground baseline.
- Sufficient Context motivates not making a diagnosis without enough evidence.
- FRAMES motivates evaluating fact coverage, fetch coverage, reasoning correctness, and citation/provenance.
- Google Cross Corpus Retrieval motivates corpus descriptions and targeted routing instead of searching every source blindly.
