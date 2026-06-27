---
name: save-the-token-mcp-doctor
description: Diagnose MCP config, stdio/Streamable HTTP health, tools/list schema surface, and client-specific enabled tool slimming with the local Save-The-Token CLI.
---

# Save-The-Token MCP Doctor

Use this skill when the user asks to debug MCP setup, reduce MCP tool/schema token cost, inspect `tools/list`, or generate client-specific enabled tool recommendations.

Save-The-Token discovers Codex, Claude Code, Claude Desktop, VS Code, and Cursor MCP configs. It forwards configured HTTP headers for URL-based MCP servers, but `scan` redacts secret-like values in output. `tools` and `report` can emit compact schema digests. `eval` can regression-test token-reduction variants over local instruction evidence. `benchmark` can aggregate strict sufficient-only token savings across local repo checkouts. `scan` and `report` can also read an optional evidence summary cache and report fingerprint hit/miss status. `report` can also plan a secondary config/instruction context budget, route instruction sections, opt in to developer guidance routing, compress selected instruction evidence, order compressed evidence, plan bounded follow-up retrieval, and emit recommend-only orchestration advice without replacing Codex's instruction chain.

## Install Modes

Use this skill with one of these CLI setups:

- Installed package or wheel: run `save-the-token ...`.
- Source checkout: set `PYTHONPATH=src` from the repository root and run `python -m save_the_token.cli ...`.
- Agent Skill bundle: load this directory from `skills/save-the-token-mcp-doctor`; the bundle guides the CLI and is distributed separately from the Python wheel.

Do not present the current benchmark as broad 70% savings across major repositories. The current strict benchmark supports the narrower claim that safe reductions were found in 5/20 repo-task cases, with about 69% weighted savings only among successful sufficient cases.

## Workflow

1. Run read-only discovery first:

   ```powershell
   save-the-token scan --root .
   ```

   Add `--cache .save-the-token-cache.json` when a prior evidence-summary cache exists and cache hit/miss visibility is useful.

   When running from a source checkout instead of an installed wheel, set `PYTHONPATH=src` and use `python -m save_the_token.cli ...`.

2. If config discovery is valid and the user wants runtime evidence, explain that this may start configured stdio MCP commands or call configured MCP URLs, then run:

   ```powershell
   save-the-token doctor --root . --timeout 5
   ```

3. For tool budget analysis, explain that collecting `tools/list` may start configured stdio MCP commands or call configured MCP URLs, then run:

   ```powershell
   save-the-token tools --root . --budget 8000
   ```

   Add `--task "..."` when the user has a concrete workflow and wants task-aware tool selection:

   ```powershell
   save-the-token tools --root . --budget 8000 --task "triage GitHub issues"
   ```

   Add `--schema-digest` to include compact schema summaries, token savings, risk markers, and full schema refs without changing recommendations.

4. For a compact client-specific snippet, explain that snippet generation may collect runtime tool evidence, then run:

   ```powershell
   save-the-token slim --root . --budget 8000 --task "triage GitHub issues"
   ```

5. When the user needs a grounded final diagnostic, explain that reports may collect runtime tool evidence, then run:

   ```powershell
   save-the-token report --root . --budget 8000 --task "triage GitHub issues"
   ```

   Add `--cache .save-the-token-cache.json` to include path-scoped fingerprints and cache hit/miss records for config, instruction, and tool evidence.

   Add `--context-budget 2000` to include selected/skipped config and instruction evidence. Add repeated `--fallback-instruction NAME` when the project uses root-level instruction filenames beyond `AGENTS.override.md` and `AGENTS.md`.

   Add `--route-instructions --task "..."` to include selected/skipped Markdown instruction sections, route lineage, source kind, and redacted snippets. Add `--include-guidance` only when the user wants `CONTRIBUTING.md` and `.github/copilot-instructions.md` considered as developer guidance.

   Add `--include-nested-instructions` only when the user wants bounded nested `AGENTS.md` / `CLAUDE.md` discovery. Treat root-only and nested benchmark results as separate coverage modes.

   Add `--compress-instructions --task "..."` to include deterministic extractive compression, original/compressed token estimates, compression ratio, and preserved citation ids.

   Add `--order-evidence --task "..."` to include the compressed evidence order, lead digest, priority scores, placement, and ordering rationale.

   Add `--active-retrieval N --task "..."` to include a bounded missing-fact follow-up trace with target corpus, query, stop reason, and final sufficiency status.

   Add `--schema-digest` to include per-server tool schema digest evidence in the report.

   Add `--orchestration-advice --task "..."` to include recommend-only main-agent, skill loading, and explicit subagent request guidance. It does not spawn subagents.

6. To regression-test token reduction over local instruction evidence, run:

   ```powershell
   save-the-token eval --root . --task "triage GitHub issues"
   ```

   Add repeated `--fallback-instruction NAME` when the project uses additional root-level instruction files. Add `--include-nested-instructions` only when evaluating nested instruction files. Add `--include-guidance` only when evaluating developer guidance files such as `CONTRIBUTING.md`.

7. To aggregate a reproducible local repo benchmark, run:

   ```powershell
   save-the-token benchmark --repos-dir .bench/repos --repo-commits .bench/repo-commits.json --fallback-instruction CLAUDE.md --json-out .bench/report.json --markdown-out .bench/report.md
   ```

   Treat savings as valid only where both full and reduced contexts are sufficient; the report caveats state this explicitly.

   Add `--include-nested-instructions` for a separate bounded nested-instruction benchmark run. Do not mix its result with a root-only benchmark claim.

## Rules

- Treat `scan` as safe and read-only.
- Treat `eval` and `benchmark` as local instruction-evidence commands; they do not start MCP servers.
- Do not synthesize Claude enabled-tool allowlist snippets; Save-The-Token marks that strategy deferred until official Claude docs expose a supported field.
- Explain before running `doctor`, `tools`, `report`, or `slim` because they start configured MCP server commands or call configured MCP URLs with configured headers.
- State that configured headers may be forwarded to configured MCP URLs, while secret-like header/env/raw config values are redacted from public output.
- Do not claim a root cause unless config, runtime, or tool evidence is sufficient.
- If evidence is insufficient, state the exact missing fact and the next command needed.
