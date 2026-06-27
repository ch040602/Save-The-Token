# Save-The-Token

Save-The-Token is a local-first MCP tool budget doctor for Codex, Claude Code, Cursor, and VS Code.

It starts with a narrow MVP:

- discover Codex MCP configuration files
- discover Claude Code `.mcp.json`, `~/.claude.json`, and Claude Desktop config files
- discover VS Code and Cursor `mcp.json` files
- lint MCP server entries
- run stdio and Streamable HTTP MCP health probes
- pass configured HTTP auth headers while redacting secrets from output
- measure `tools/list` schema surface
- emit compact tool schema digests with required inputs, risk markers, and token savings
- emit grounded sufficiency reports with evidence ids
- fingerprint config, instruction, and tool evidence for cache-aware reruns
- plan a secondary context budget for config and instruction evidence without replacing Codex's instruction chain
- route root-level instruction sections by task query while redacting secret-like lines
- order compressed instruction evidence into a lead digest to reduce lost-in-the-middle risk
- plan bounded follow-up retrieval steps from missing facts without treating insufficient drafts as final
- evaluate token-reduction variants for required evidence recall and sufficiency regressions
- generate strict benchmark JSON/Markdown reports that count savings only when context remains sufficient
- recommend main-agent, progressive skill loading, and explicit subagent request paths without spawning subagents
- prioritize relevant tools for a user task query
- generate client-specific `enabled_tools` or `enabledTools` recommendations

The design follows an Agentic RAG-style diagnostic loop: plan required facts, retrieve only the needed config/runtime/tool evidence, judge whether the context is sufficient, then emit a grounded report or targeted next checks.

## Release Positioning

Safe current claim: Save-The-Token is a local-first token budget and MCP diagnostic CLI for agent coding environments. Its strict benchmark counts savings only when both the full context and the reduced context remain sufficient.

Current benchmark scope is narrow. On the current 10-repo, 20-case local benchmark, Save-The-Token finds safe reductions in 5/20 repo-task cases. Successful cases reduce instruction context by about 69% weighted average. Repos or tasks with insufficient full context are reported as coverage gaps, not token savings.

Do not describe the current release as "70% token savings across major repositories." That overstates the measured result.

## Quick Start

Install the CLI from a source checkout:

```powershell
python -m pip install .
```

Or install from a built wheel:

```powershell
python -m pip install dist\save_the_token-0.1.0-py3-none-any.whl
```

For development and release-gate tooling:

```powershell
python -m pip install -e ".[dev]"
```

Run read-only discovery first:

```powershell
save-the-token scan --root .
```

When running directly from a source checkout without installing, set `PYTHONPATH=src`:

```powershell
$env:PYTHONPATH = "src"
python -m save_the_token.cli scan --root .
```

Runtime commands are not all equivalent:

- `scan` is read-only config discovery and linting. It does not start MCP servers.
- `eval` and `benchmark` evaluate local instruction files. They do not start MCP servers.
- `doctor`, `tools`, `report`, and `slim` may start configured stdio MCP server commands, call configured Streamable HTTP MCP URLs, and forward configured HTTP headers.

```powershell
save-the-token doctor --root .
save-the-token tools --root . --budget 8000
save-the-token tools --root . --budget 8000 --task "review GitHub issues"
save-the-token tools --root . --budget 8000 --task "review GitHub issues" --schema-digest
save-the-token report --root . --budget 8000
save-the-token report --root . --budget 8000 --context-budget 2000
save-the-token report --root . --budget 8000 --task "fix tests" --route-instructions
save-the-token report --root . --budget 8000 --task "fix tests" --route-instructions --include-nested-instructions
save-the-token report --root . --budget 8000 --task "fix tests" --route-instructions --include-guidance
save-the-token report --root . --budget 8000 --task "fix tests" --compress-instructions
save-the-token report --root . --budget 8000 --task "fix tests" --order-evidence
save-the-token report --root . --budget 8000 --task "fix tests" --active-retrieval 2
save-the-token report --root . --budget 8000 --task "fix tests" --schema-digest
save-the-token report --root . --budget 8000 --task "security review" --orchestration-advice
save-the-token report --root . --budget 8000 --cache .save-the-token-cache.json
save-the-token eval --root . --task "fix tests"
save-the-token eval --root . --task "fix tests" --include-nested-instructions
save-the-token eval --root . --task "fix tests" --include-guidance
save-the-token benchmark --repos-dir .bench/repos --repo-commits .bench/repo-commits.json --fallback-instruction CLAUDE.md --include-nested-instructions --json-out .bench/report.json --markdown-out .bench/report.md
save-the-token slim --root . --budget 8000
```

## Distribution

Save-The-Token has two release artifacts:

- PyPI wheel / source distribution: ships the `save-the-token` CLI package.
- Agent Skill bundle: ships from the repository at `skills/save-the-token-mcp-doctor` and is not imported as Python package code.

The wheel is intentionally CLI-focused. The source distribution includes `docs/` and `skills/` via `MANIFEST.in` so release archives keep the Agent Skill and design documents available for review. Public release metadata points to the package page, repository, README documentation, and issue tracker.

Agent Skill distribution is separate from the wheel. Use the repository bundle at `skills/save-the-token-mcp-doctor` with a locally installed `save-the-token` CLI, or use a source checkout with `PYTHONPATH=src`. The skill is an orchestration guide for the CLI; it does not package Python code into the wheel.

## Commands

- `scan`: read-only config discovery and linting. Does not start MCP servers.
- `doctor`: probes enabled stdio or Streamable HTTP MCP servers and checks `initialize` plus `tools/list`.
- `tools`: reports tool count, estimated schema tokens, relevance scores, matched task terms, and client-specific allowlist snippets.
- `report`: emits `sufficient`, `insufficient`, or `unanswerable` with claims, missing facts, feedback queries, and evidence ids.
- `eval`: compares full, selected, compressed, and reordered instruction-evidence variants for token estimates, required-term recall, missing facts, and sufficiency regressions.
- `benchmark`: runs `eval` across local repo directories and emits strict JSON/Markdown reports with repo commits, task queries, coverage, savings, regressions, and caveats.
- `slim`: prints compact source-client-specific snippets, using Codex TOML for Codex config and JSON `enabledTools` snippets for VS Code/Cursor `mcp.json`.

`tools`, `report`, and `slim` accept `--task "..."`. When present, Save-The-Token routes the task query over tool names, descriptions, and schemas, then recommends matching tools before falling back to budget-only selection.

`tools` and `report` accept `--schema-digest`. This emits compact tool schema digests with name, shortened description, required inputs, auth/destructive/network/filesystem risk markers, full schema references, token savings, and omitted-detail notes. Digest mode does not change task-aware tool selection.

`scan` and `report` accept `--cache path.json`. The cache is read-only and uses `entries` with `source`, `kind`, `sha256`, `estimated_tokens`, and optional `summary` fields. Output includes `evidence_cache` hit/miss records; misses remain visible so stale cache entries do not hide changed evidence.

`report` accepts `--context-budget N` and optional repeated `--fallback-instruction NAME`. This measures config and root-level instruction files by bytes and estimated tokens, emits selected/skipped evidence with reasons, and preserves Codex's orchestrator-loaded instruction baseline instead of changing it.

`report` accepts `--route-instructions` with `--task "..."`. This splits root-level `AGENTS.override.md`, `AGENTS.md`, and fallback instruction files into Markdown sections, selects task-matching sections plus baseline safety/security sections, emits route lineage, and redacts secret-like lines in selected snippets. Add `--include-nested-instructions` to opt in to bounded nested `AGENTS.md` / `CLAUDE.md` discovery with scope lineage. Add `--include-guidance` to opt in to developer guidance files such as `CONTRIBUTING.md` and `.github/copilot-instructions.md`; these are reported with `source_kind="developer-guidance"` and are not loaded by default.

`report` accepts `--compress-instructions`. This routes instruction sections when needed, then keeps headings, warnings, commands, and task-matched lines while reporting original tokens, compressed tokens, compression ratio, and preserved citation ids.

`report` accepts `--order-evidence`. This routes and compresses instruction evidence when needed, then orders compressed items by safety/task priority, citation availability, recency, and stable tie-breakers. Output includes an `evidence_order` lead digest, ordered items, and rationale.

`report` accepts `--active-retrieval N`. This plans up to `N` targeted follow-up retrieval steps from the report's missing facts, records the target corpus, query, retrieved evidence ids already present in the draft, stop reason, and final sufficiency status. It does not turn an `insufficient` draft into a final recommendation.

`report` accepts `--orchestration-advice`. This emits recommend-only guidance that distinguishes main-agent work, progressive skill loading, and explicit subagent requests. It never spawns subagents or overrides Codex's orchestrator.

`eval` accepts `--task "..."`, optional repeated `--fallback-instruction NAME`, optional `--include-nested-instructions`, and optional `--include-guidance`. It does not start MCP servers; it evaluates local instruction evidence only and exits non-zero if a token-reduction variant drops required task terms.

`benchmark` accepts `--repos-dir`, repeated `--task`, optional `--repo-commits`, repeated `--fallback-instruction`, optional `--include-nested-instructions`, optional `--include-guidance`, `--json-out`, and `--markdown-out`. Savings are counted only when `full_context` and the reduced variant are both `sufficient`; insufficient full context is reported as a coverage gap rather than a saving. Root-only and nested-instruction benchmark runs should be compared separately because their coverage assumptions differ.

## Safety Boundaries

- `scan` reads client config files and emits lint findings. It does not start MCP servers or call MCP URLs.
- `eval` and `benchmark` operate on local instruction files and benchmark fixture directories. They do not start MCP servers.
- `doctor`, `tools`, `report`, and `slim` collect runtime or tool evidence. Depending on discovered config, they may start configured stdio MCP commands or call configured Streamable HTTP MCP URLs.
- URL-based MCP probes forward configured headers after filtering MCP-managed headers and unsafe newline values. Secret-like header, env, and raw config values are redacted from public JSON output.
- Save-The-Token reads configured header values as written; it does not expand environment variable placeholders such as `${TOKEN}`.

For protected HTTP MCP servers, put headers in the server config:

```json
{
  "mcpServers": {
    "remote": {
      "url": "https://example.com/mcp",
      "headers": {
        "Authorization": "Bearer ${TOKEN}"
      }
    }
  }
}
```

Save-The-Token forwards the configured header value as read from the client config; it does not expand environment variable placeholders.
`scan` redacts secret-like `env`, `headers`, and `raw` values in JSON output.

## Current Limitations

- HTTP probing supports basic Streamable HTTP JSON and SSE responses for `initialize` and `tools/list`.
- Custom headers with unsafe newline characters are linted and ignored by the HTTP probe.
- Task-aware tool selection is lexical and deterministic; semantic embeddings or LLM reranking are intentionally out of scope for the MVP.
- Claude config discovery is supported for Claude Code and Claude Desktop.
- Instruction discovery covers root-level `AGENTS.override.md`, `AGENTS.md`, and configured fallback instruction filenames by default. Nested directory-level `AGENTS.md` / `CLAUDE.md` files are opt-in through `--include-nested-instructions` and use bounded traversal.
- Instruction routing, compression, and evidence ordering are deterministic and lexical; semantic embeddings and model-based compression are out of scope for the MVP.
- Developer guidance routing is opt-in because `CONTRIBUTING.md` and similar files can be broad, repo-specific, and outside the orchestrator instruction chain.
- Active retrieval is a deterministic follow-up planner for missing facts; it does not automatically rerun external commands or call remote MCP URLs beyond the normal report probe path.
- Schema digest risk markers are deterministic keyword signals, not a security classifier.
- Evaluation recall is lexical over task terms; it is a regression guard for required evidence, not a semantic correctness benchmark.
- Benchmark reports are local and deterministic. They do not clone repos, judge semantic answer quality, or count savings from insufficient reduced variants.
- Orchestration advice is recommend-only and does not load skills or spawn subagents.
- Evidence cache writing is manual for now; Save-The-Token reads cache entries and reports hit/miss status.
- JSON snippets are merge suggestions, not automatic file edits.
- Claude MCP config discovery is supported, but Claude-specific enabled-tool allowlist snippets are deferred because the official Claude MCP config docs do not document an `enabledTools` field.
- Automatic patching is planned after the current snippet flow stabilizes.

## Development

```powershell
python -m unittest discover -s tests -v
python -m ruff check .\src .\tests
mypy .\src\save_the_token
python -m pip wheel . -w dist --no-deps
```
