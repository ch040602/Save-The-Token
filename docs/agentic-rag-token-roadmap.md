# Agentic RAG Token Roadmap

This roadmap records remaining work after TODO-009. It focuses on reducing token cost without fighting Codex's own orchestrator, instruction discovery, skill loading, or explicit subagent orchestration.

## Source Basis

- Codex `AGENTS.md` discovery reads global guidance, then project guidance from repo root to current directory. It includes at most one instruction file per directory and stops when `project_doc_max_bytes` is reached.
- Codex supports `project_doc_fallback_filenames` and `project_doc_max_bytes` in config for instruction discovery.
- Codex skills already use progressive disclosure: the initial skills list is compact, and full `SKILL.md` is loaded only when selected.
- Codex subagents are orchestrated by Codex and are spawned only when explicitly requested; subagent workflows cost more tokens than comparable single-agent runs.

Primary references:

- https://developers.openai.com/codex/guides/agents-md
- https://developers.openai.com/codex/skills
- https://developers.openai.com/codex/subagents
- https://developers.openai.com/codex/concepts/customization
- https://code.claude.com/docs/en/mcp
- https://code.claude.com/docs/en/settings
- https://modelcontextprotocol.io/docs/develop/connect-local-servers
- https://arxiv.org/abs/2310.05736
- https://arxiv.org/html/2310.06839v2
- https://arxiv.org/abs/2307.03172
- https://arxiv.org/abs/2305.06983

## Agentic RAG Corpus Catalog

Save-The-Token should treat these as separate evidence corpora instead of flattening them into one prompt:

- `client-config`: Codex `config.toml`, VS Code `mcp.json`, Cursor `mcp.json`, Claude Code `.mcp.json`, Claude Code `~/.claude.json`, and Claude Desktop `claude_desktop_config.json`.
- `runtime`: stdio and Streamable HTTP probe results.
- `tools`: `tools/list` schemas, names, descriptions, task relevance, and selected allowlists.
- `instructions`: `AGENTS.md`, `AGENTS.override.md`, and configured fallback instruction files.
- `skills`: skill metadata first, full `SKILL.md` only when routed or explicitly invoked.
- `orchestration`: main-agent vs explicit subagent routing decisions, including token/cost notes.
- `policy`: approval policy, sandbox policy, redaction rules, and secret handling.

## Registered TODOs

- `TODO-010`: source-grounded Claude config discovery. Completed: `scan` discovers Claude Code project `.mcp.json`, Claude Code user/local `~/.claude.json`, and Claude Desktop `claude_desktop_config.json`; Claude enabled-tool snippet generation is explicitly deferred.
- `TODO-011`: context budget planner for instruction and config corpora. Completed: `report --context-budget` measures config and instruction candidates, emits selected/skipped evidence, and preserves Codex's orchestrator baseline.
- `TODO-012`: selective `AGENTS.md` evidence routing. Completed: `report --route-instructions --task ...` parses instruction Markdown sections, selects task-relevant plus baseline safety/security sections, redacts selected snippets, and records route lineage.
- `TODO-013`: orchestrator-aware subagent and skill loading recommendations. Completed: `report --orchestration-advice` emits recommend-only main-agent, progressive skill loading, and explicit subagent request guidance with token/cost warnings and `auto_spawn=false`.
- `TODO-014`: extractive prompt compression planner. Completed: `report --compress-instructions` compresses routed instruction sections with deterministic extractive rules and reports token savings, citation ids, and preserved facts.
- `TODO-015`: evidence ordering to reduce lost-in-the-middle risk. Completed: `report --order-evidence` orders compressed evidence by safety/task priority, citation availability, recency, and stable tie-breakers, then emits a lead digest.
- `TODO-016`: active follow-up retrieval loop. Completed: `report --active-retrieval N` plans bounded missing-fact follow-up steps with target corpus, query, existing evidence ids, stop reason, and final status while preserving insufficient drafts.
- `TODO-017`: evidence fingerprint cache. Completed: `scan --cache` and `report --cache` now expose path-scoped SHA-256 fingerprints, token estimates, and cache hit/miss status for config, instruction, and tool evidence.
- `TODO-018`: tool schema digest mode. Completed: `tools --schema-digest` and `report --schema-digest` emit compact schema digests with required inputs, risk markers, full schema refs, token savings, omitted details, and preserved routing terms.
- `TODO-019`: token-budget evaluation harness. Completed: `eval --task ...` compares full, selected, compressed, and reordered instruction-evidence variants with token estimates, required-term recall, missing fact count, sufficiency status, and regression flags.
- `TODO-021`: nested instruction discovery. Completed: `--include-nested-instructions` enables bounded nested `AGENTS.md` / `CLAUDE.md` discovery for `report`, `eval`, and `benchmark`, preserving scope lineage and separating root-only from nested benchmark caveats.

## Token Reduction Strategy

The goal is to reduce unnecessary context while preserving the information the orchestrator already loads and relies on.

1. Preserve the orchestrator baseline.
   - Do not replace Codex's instruction chain.
   - Treat already-loaded `AGENTS.md` content as baseline policy.
   - Save-The-Token should inspect and report instruction cost, not silently suppress orchestrator guidance.

2. Add a secondary retrieval layer for large instruction files.
   - Measure candidate instruction files by bytes and estimated tokens before deep reads.
   - Split files by Markdown headings.
   - Route the task query to relevant sections.
   - Report selected and skipped sections with reasons.

3. Use progressive disclosure for local assets.
   - Skill metadata is enough until a task matches the skill.
   - Full skill references should be read only after a route decision.
   - Large docs should be summarized into a compact evidence record before synthesis.

4. Emit a context budget report.
   - Total bytes and estimated tokens per corpus.
   - Selected evidence IDs.
   - Skipped evidence IDs.
   - Missing facts if the budget cut makes the answer insufficient.

Implemented slice:

- `src/save_the_token/context_budget.py` plans a secondary context budget over discovered config sources and root-level instruction files.
- `report --context-budget` includes `context_budget` in diagnostic JSON.
- Repeated `--fallback-instruction NAME` includes additional root-level instruction candidates.
- The planner does not read raw instruction content; section-level routing remains TODO-012.

5. Prefer reviewable snippets over mutation.
   - Generate config snippets first.
   - Defer automatic patching unless a later TODO adds dry-run diffs, backups, and explicit user approval.

6. Compress only after routing.
   - First select relevant corpora and sections.
   - Then compress selected evidence.
   - Keep citation IDs and required facts intact.
   - Use deterministic extractive compression by default; model-based compression can remain optional.

7. Reorder evidence deliberately.
   - Long contexts can underuse evidence in the middle.
   - Place high-priority instructions and critical evidence near the front or in a lead digest.
   - Keep supporting details after the digest with citation IDs.

Implemented slice:

- `src/save_the_token/evidence_ordering.py` orders compressed instruction evidence after routing and compression.
- `report --order-evidence` includes `evidence_order` in diagnostic JSON and internally routes/compresses instructions when needed.
- The ordering is deterministic, dependency-free, and records priority score, recency, placement, rationale, and lead digest.

8. Retrieve again only when missing facts justify it.
   - Do not fan out blindly.
   - Generate follow-up queries from the sufficiency check.
   - Stop when sufficient, unanswerable, or the iteration budget is exhausted.

Implemented slice:

- `src/save_the_token/active_retrieval.py` maps report missing facts to targeted follow-up retrieval steps.
- `report --active-retrieval N` emits `active_retrieval` with original task, iteration budget, trace steps, stop reason, and final status.
- The planner never upgrades an insufficient draft; new external evidence must be gathered and the report rebuilt before sufficiency can change.

9. Cache evidence fingerprints.
   - Hash instruction/config/schema evidence.
   - Reuse token estimates and summaries for unchanged evidence.
   - Mark cache hits and misses in reports.

10. Digest large tool schemas.
   - Keep name, description, required inputs, and risk markers.
   - Preserve a full schema reference for selected or inspected tools.
   - Report token savings and omitted details.

Implemented slice:

- `src/save_the_token/schema_digest.py` produces deterministic tool schema digest reports.
- `tools --schema-digest` emits compact digest payloads alongside unchanged budget recommendations.
- `report --schema-digest` adds digest evidence and `tool_schema_digests` to diagnostic JSON.

11. Evaluate token cuts.
   - Compare full, selected, compressed, and reordered packs.
   - Track missing facts and sufficiency status, not only token count.

Implemented slice:

- `src/save_the_token/evaluation.py` evaluates instruction evidence variants built from routing, compression, and ordering.
- `eval --task "..."` emits token estimates, selected evidence recall, missing fact count, sufficiency status, preserved/missing terms, and regressions.
- Regression tests catch reduced variants that drop required task terms present in full context.

## Selective AGENTS.md Routing

Selective routing should be additive to Codex behavior:

- Codex may already have loaded `AGENTS.md`; Save-The-Token should not assume it can unload it.
- Save-The-Token can scan instruction files as evidence and identify which sections are relevant to a task.
- The diagnostic report should say:
  - which instruction files exist,
  - which sections are relevant,
  - which sections were skipped,
  - whether skipped content creates insufficiency.

Proposed selection algorithm:

1. Discover instruction candidates:
   - `AGENTS.override.md`
   - `AGENTS.md`
   - configured fallback names such as `TEAM_GUIDE.md` or `.agents.md`
2. Build section records:
   - file path,
   - heading path,
   - byte span,
   - estimated tokens,
   - lexical task terms.
3. Route:
   - Always include root-level safety/permissions sections.
   - Include sections matching task terms.
   - Include nearest-directory overrides before parent sections.
4. Judge sufficiency:
   - If a task touches tests but no test instructions were selected, mark `insufficient`.
   - If selected sections exceed budget, emit follow-up queries or ask for a narrower task.

Implemented slice:

- `src/save_the_token/instruction_routing.py` parses instruction files by Markdown heading.
- `report --route-instructions --task "..."` emits `instruction_routes`.
- Route lineage records original task, source file, source kind, scope path, scope depth, heading path, selection status, reason, and matched terms.
- Selected snippets are length-bounded and secret-like lines are redacted.
- The route is additive to Codex's orchestrator-loaded baseline.
- `--include-nested-instructions` adds bounded nested `AGENTS.override.md`, `AGENTS.md`, `CLAUDE.md`, and fallback instruction filename traversal.

## Orchestrator-Aware Policy

Save-The-Token should not try to out-orchestrate Codex. It should provide evidence that helps Codex decide.

- Main agent default:
  - local code edits,
  - small diagnostics,
  - single-module changes,
  - docs-only updates.
- Skill progressive disclosure:
  - load full skill instructions only when the task matches its metadata or the user explicitly invokes it.
- Explicit subagent suggestion:
  - broad codebase exploration,
  - independent security/review/performance critique,
  - parallel investigation across unrelated corpora.
- Warning:
  - subagents consume more tokens because each performs its own model and tool work.
  - recommendations should say "suggest asking Codex to spawn..." rather than spawning automatically.

Implemented slice:

- `src/save_the_token/orchestration.py` emits deterministic recommend-only orchestration advice from task terms and scan evidence.
- `report --orchestration-advice` includes `orchestration_advice` in diagnostic JSON and grounds the advice as evidence.
- Recommendations distinguish main-agent work, progressive skill loading, and explicit subagent requests.
- Subagent recommendations include token/cost warnings and `auto_spawn=false`.

## Additional Agentic RAG Methods

### Extractive Compression

LLMLingua and LongLLMLingua motivate budget-controlled, question-aware compression. Save-The-Token should not add a model dependency by default. Instead, TODO-014 should start with deterministic extractive compression:

- preserve headings, commands, warnings, and cited evidence;
- drop repeated examples and low-match prose;
- report compression ratio;
- mark insufficiency if required facts are lost.

Implemented slice:

- `src/save_the_token/prompt_compression.py` compresses selected instruction route sections.
- Compression preserves citation ids built from source path, byte span, and heading.
- `report --compress-instructions` emits `prompt_compression`.
- The method remains deterministic and dependency-free; LLMLingua-style compression remains source inspiration rather than a runtime dependency.

### Evidence Ordering

Lost-in-the-middle research motivates not just reducing context, but ordering it. TODO-015 now produces prompt packs with:

- a lead digest containing the highest-value evidence;
- boundary placement for safety and task-critical facts;
- stable tie-breaking to keep outputs reproducible.

Implemented slice:

- Safety/security/permission headings receive the highest deterministic priority.
- Task-matched compressed sections, warnings, commands, and citation-backed evidence are promoted before generic prose.
- Recency and stable source/heading/citation tie-breakers keep ordering reproducible.

### Active Retrieval

FLARE-style active retrieval motivates retrieving again only when generation reveals a missing fact. For Save-The-Token, TODO-016 uses the existing sufficiency check:

- missing fact -> follow-up query -> targeted corpus route -> new evidence -> re-check;
- max iteration budget;
- no final recommendation from an insufficient draft.

Implemented slice:

- Missing facts are routed to deterministic target corpora: `client-config`, `runtime`, `tools`, `instructions`, `prompt-compression`, `evidence-order`, or `diagnostic`.
- The trace records original task, missing fact, follow-up query, retrieved evidence ids already present in the draft, and status after each planned step.
- Stop reasons currently include `sufficient`, `unanswerable`, `iteration_budget_exhausted`, and `awaiting_external_evidence`.

### Evidence Cache

Many token costs come from repeatedly reading unchanged config, instruction, and schema corpora. TODO-017 should add fingerprinted evidence records:

- path, size, mtime, and content hash;
- cached summary and token estimate;
- invalidation when fingerprints change.

Implemented slice:

- `src/save_the_token/evidence_cache.py` fingerprints files, text, and `tools/list` schemas.
- Cache lookup is deterministic on `kind`, source path, and SHA-256.
- `scan --cache` reports client-config and root instruction cache status.
- `report --cache` also reports tool evidence cache status after runtime probing.

### Tool Schema Digest

Large MCP tool schemas can dominate token budget. TODO-018 now creates a digest mode:

- name;
- description;
- required input keys;
- auth/destructive/network risk markers;
- full schema pointer for selected tools.

Implemented slice:

- Digest items include `full_schema_tokens`, `digest_tokens`, `saved_tokens`, `missing_details`, `relevance_score`, and `matched_terms`.
- Risk markers are deterministic keyword signals for destructive/write/auth/network/filesystem cues.
- Full schema refs are stable strings of the form `<config>#<server>/tools/<tool>/schema`.

### Evaluation Harness

Token reduction needs regression checks. TODO-019 should create fixtures for:

- full-context baseline;
- selected-context pack;
- compressed-context pack;
- reordered-context pack;
- selected evidence recall and sufficiency status.

Implemented slice:

- The harness compares `full_context`, `selected_context`, `compressed_context`, and `reordered_context`.
- Metrics include `estimated_tokens`, `selected_evidence_recall`, `missing_fact_count`, `sufficiency_status`, `preserved_terms`, and `missing_terms`.
- The CLI exits non-zero when regressions are detected.

## Next Implementation Slice

Major-repo benchmarking found that efficiency claims should be more conservative before release. The next hardening items are:

- TODO-020: propagate compression missing facts into reordered evaluation sufficiency. Implemented.
- TODO-021: discover nested `AGENTS.md` and `CLAUDE.md` files so large repos are not judged only by root instruction coverage. Implemented: `report`, `eval`, and `benchmark` accept `--include-nested-instructions`; benchmark caveats distinguish root-only and nested-instruction coverage modes.
- TODO-022: optionally route high-demand developer guidance sources such as `CONTRIBUTING.md` and `.github/copilot-instructions.md` without changing the default orchestrator-safe baseline. Implemented: `--include-guidance` on `report` and `eval` includes exact guidance paths with `source_kind="developer-guidance"`.
- TODO-023: add a reproducible benchmark report command that records repo commits, task queries, coverage, regressions, and caveats. Implemented: `benchmark --repos-dir ...` writes strict sufficient-only JSON and Markdown reports.

Post-TODO-022 benchmark:

- `--include-guidance` increased cases with instruction/guidance tokens from 12/20 to 14/20 across the sampled repo-task set.
- Sufficient-reduction success remained 5/20, so this is a coverage plumbing improvement rather than a proven efficiency gain.
- Benchmark reports now make this caveat visible by default.

Still deferred:

- Claude enabled-tool allowlist snippet synthesis remains deferred until an official Claude config field is documented.
- Semantic answer-quality grading remains deferred; `eval` currently guards required evidence retention only.

## Claude Config Discovery

Official source basis:

- Claude Code MCP scopes: project servers are stored in `.mcp.json`; user and local scopes are stored in `~/.claude.json`, with local servers under the current project entry.
- Claude Code settings docs also list MCP server locations as `~/.claude.json`, `.mcp.json`, and per-project `~/.claude.json`.
- Claude Desktop MCP docs locate `claude_desktop_config.json` at `~/Library/Application Support/Claude/` on macOS and `%APPDATA%\Claude\` on Windows.

Implemented slice:

- `src/save_the_token/config.py` discovers those files read-only.
- `.claude.json` extraction preserves `user` and `local` scopes on per-server source metadata.
- Claude Desktop config reuses the standard `mcpServers` JSON parser.
- Claude enabled-tool snippets are returned as `client_snippet_format="deferred"` instead of inventing unsupported config.
