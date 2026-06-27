# Release Readiness Audit

Audit date: 2026-06-26

## Verdict

Save-The-Token is release-ready for a CLI-focused public pre-release. Stable release claims should remain conservative until a fresh benchmark is run after the public repository push.

Packaging metadata, release files, public project URLs, CI, static typing, formatting, install smoke, and release-facing safety/claim documentation are now addressed. The current safe positioning is CLI public pre-release, with narrow benchmark claims and explicit runtime safety boundaries.

## Gate Recheck

Recheck date: 2026-06-26

Verdict remains: not release-ready.

Current release gate status:

- Unit tests: pass, 65 tests.
- Ruff: pass with `python -m ruff check .\src .\tests`.
- Wheel build: pass with `python -m pip wheel . -w .release-audit-dist --no-deps`.
- Benchmark smoke: pass, current strict report shows 20 cases, 5 eligible full-sufficient cases, 5 successful reductions, and 69.3% weighted saving on successful cases.
- Mypy: fail, 6 errors in 4 files.
- Root release files: `LICENSE`, `LICENSE.md`, `CHANGELOG.md`, and `.gitignore` are absent.
- CI: `.github/workflows` is absent.

Release decision: do not publish as a stable public release. A private preview or pre-release is acceptable only if it clearly states the current blockers and benchmark limits.

## Gate Recheck 2

Recheck date: 2026-06-26

Verdict remains unchanged: not stable-release-ready.

Latest gate evidence:

- Unit tests: pass, 65 tests.
- Ruff: pass.
- Wheel build: pass.
- Benchmark smoke: pass, 20 total cases, 5 eligible full-sufficient cases, 5 successful reductions, 69.3% weighted saving on successful cases.
- Mypy: fail, same 6 errors in 4 files.
- Release files: `LICENSE`, `LICENSE.md`, `CHANGELOG.md`, and `.gitignore` still absent.
- CI: `.github/workflows` still absent.

Release decision remains:

- Stable public release: blocked.
- Private preview / pre-release: acceptable only with explicit blocker disclosure.
- Marketing claim: limited to successful benchmark cases; do not claim broad 70% savings across major repositories.

## Distribution Gap Matrix

Additional audit date: 2026-06-26

Install smoke:

- Built wheel installs into an isolated venv with `pip install --no-index --find-links .\.release-audit-dist Save-The-Token`.
- Installed `save-the-token --help` runs and exposes `scan`, `doctor`, `tools`, `slim`, `report`, `eval`, and `benchmark`.

Wheel metadata gaps:

- `Description-Content-Type` is absent, so README long description is not bound into package metadata.
- `Classifier` fields are absent.
- `Project-URL` fields are absent.
- License is declared as `MIT`, but no root license file is packaged.
- Wheel contains only 23 files: the `save_the_token` package and dist-info metadata.
- Wheel does not contain `docs/`.
- Wheel does not contain `skills/save-the-token-mcp-doctor`.

Tooling gaps:

- `python -m ruff check .\src .\tests` passes.
- `python -m ruff format --check .\src .\tests` fails: 30 files would be reformatted.
- `build` and `twine` are not installed, so source distribution and package metadata validation are not available.

Release impact:

- CLI wheel is installable enough for a private preview.
- PyPI-style public release remains blocked until metadata, license files, formatting policy, sdist/twine validation, and distribution shape are addressed.
- Agent Skill release remains blocked until the skill directory has an explicit distribution or install path separate from the wheel.

## Gate Recheck 3

Recheck date: 2026-06-26

Verdict remains unchanged: not stable-release-ready.

Fresh gate evidence:

- Unit tests: pass, 65 tests.
- `python -m ruff check .\src .\tests`: pass.
- `python -m py_compile` over `src/save_the_token/*.py`: pass.
- Wheel build: pass, produced `save_the_token-0.1.0-py3-none-any.whl`.
- Isolated wheel install: pass.
- Installed `save-the-token --help`: pass.
- Benchmark with explicit `PYTHONPATH=src`: pass, 20 total cases, 5 eligible full-sufficient cases, 5 successful reductions, 69.3% weighted saving on successful cases.
- `mypy .\src\save_the_token`: fail, 6 errors in 4 files.
- `python -m ruff format --check .\src .\tests`: fail, 30 files would be reformatted.
- Root release files: `LICENSE`, `LICENSE.md`, `CHANGELOG.md`, and `.gitignore` remain absent.
- CI: `.github/workflows` remains absent.
- Package validation tooling: `build` and `twine` are not installed.
- Wheel metadata remains too sparse: no long-description content type, no classifiers, no project URLs, no packaged docs, no packaged Agent Skill, and no emitted license metadata in the inspected wheel.
- Release gate reproducibility issue found: the prior local benchmark command failed without package installation or `PYTHONPATH`; RDD command registry now uses explicit `PYTHONPATH=src` for local benchmark execution.

Release decision remains:

- Stable public release: blocked.
- Private preview / pre-release: technically possible for the CLI only, but should disclose all blockers.
- Agent Skill release: blocked until the skill distribution path is explicit.
- Marketing claim: keep to strict successful-case benchmark wording only.

## Distribution Plan

Plan date: 2026-06-27

Release shape:

- PyPI wheel: ships the installable `Save-The-Token` CLI package and console script only.
- Source distribution: includes `README.md`, `LICENSE`, `CHANGELOG.md`, `docs/`, and `skills/` through `MANIFEST.in`.
- Agent Skill bundle: distributed from the repository path `skills/save-the-token-mcp-doctor`, not as Python importable package code.

Metadata status after TODO-025:

- README long description is configured through `readme = "README.md"`.
- MIT license file is configured through `license-files = ["LICENSE"]`.
- Classifiers, keywords, and optional `dev` dependencies are configured.
- `CHANGELOG.md` and `.gitignore` exist.
- Historical note: before the public repository bootstrap, project URL metadata only contained the package URL. Current metadata now includes Package, Repository, Documentation, and Issues URLs.

Release impact:

- Packaging metadata is now sufficient for a CLI private preview and closer to a PyPI pre-release.
- Stable release remains blocked by TODO-028 and the missing public repository/project URLs.
- Agent Skill release is no longer ambiguous in shape, but still needs install documentation and safety wording from TODO-028.

## Packaging Recheck

Recheck date: 2026-06-27

TODO-025 status: completed.

Passing checks:

- `pyproject.toml` parses and includes README metadata, license files, classifiers, keywords, package URL, and optional `dev` dependencies.
- `python -m pip wheel . -w .release-audit-dist --no-deps`: pass.
- Wheel metadata includes `Description-Content-Type: text/markdown`, `License-Expression: MIT`, `License-File: LICENSE`, classifiers, keywords, and `Project-URL: Package, https://pypi.org/project/Save-The-Token/`.
- Wheel contains the CLI package and license file; it intentionally does not contain `docs/` or `skills/`.
- Temporary build venv with `build` and `twine`: pass.
- `python -m build --sdist --wheel --outdir .release-build-dist`: pass.
- `twine check .release-build-dist\*`: pass for wheel and sdist.
- Source distribution includes `README.md`, `LICENSE`, `CHANGELOG.md`, `docs/release-readiness.md`, `skills/save-the-token-mcp-doctor/SKILL.md`, and `skills/save-the-token-mcp-doctor/agents/openai.yaml`.
- Isolated wheel install and installed `save-the-token --help`: pass.

Remaining release gaps after TODO-025:

- Public repository, documentation, and issue tracker URLs are now configured in `pyproject.toml`.
- TODO-026 completed mypy and format gates.
- TODO-027 completed CI and automated release smoke.
- TODO-028 still owns final release positioning, install modes, and safety boundary docs.

## Quality Gate Recheck

Recheck date: 2026-06-27

TODO-026 status: completed.

Passing checks:

- `python -m unittest discover -s tests -v`: pass, 65 tests.
- `python -m ruff check .\src .\tests`: pass.
- `python -m ruff format --check .\src .\tests`: pass, 33 files already formatted.
- `mypy .\src\save_the_token`: pass, 18 source files.
- `python -m py_compile` over `src/save_the_token/*.py`: pass.
- `python -m pip wheel . -w .release-audit-dist --no-deps`: pass.
- Isolated wheel install and installed `save-the-token --help`: pass.
- Benchmark smoke with explicit `PYTHONPATH=src`: pass, 20 total cases, 5 eligible full-sufficient cases, 5 successful reductions, and 69.3% weighted saving on successful cases.

Type-fix summary:

- Added explicit `tuple[str, ...]` annotations for empty `missing_facts` tuples where mypy inferred `tuple[()]`.
- Typed schema digest budget items as `ToolBudgetItem | None`.
- Narrowed evidence cache entry fields before building cache keys.
- Bound process stdout to a local variable before threaded reads.

Release impact:

- Static typing and format gates are no longer release blockers.
- Stable release remains blocked by TODO-028 and real public project URLs.

## CI Recheck

Recheck date: 2026-06-27

TODO-027 status: completed.

CI workflow:

- Added `.github/workflows/release.yml`.
- Runs on `push`, `pull_request`, and `workflow_dispatch`.
- Uses a Python matrix for 3.11 and 3.13.
- Installs the package with `python -m pip install -e ".[dev]"`.
- Runs unit tests, ruff lint, ruff format check, mypy, compileall, build, twine check, wheel install smoke, and tiny benchmark smoke.
- Does not run `doctor`, `tools`, `report`, or `slim`, so CI does not execute configured user MCP servers or call configured MCP URLs.

Tiny benchmark smoke:

- Added `tests/fixtures/benchmark-smoke`.
- Fixture contains two tiny local repo directories and a commit manifest.
- The CI benchmark command uses only local instruction files and writes `benchmark-smoke.json` plus `benchmark-smoke.md`.
- Added a unit test to keep the fixture small and ensure it produces one successful sufficient reduction.

Local validation:

- `python -m unittest tests.test_benchmark -v`: pass, 4 tests.
- `python -m ruff check .\src .\tests`: pass.
- `python -m ruff format --check .\src .\tests`: pass.
- CI-like temporary venv installed `.[dev]`: pass.
- CI-like sequence passed: unittest, ruff, format check, mypy, compileall, build, twine check, installed wheel `save-the-token --help`, and tiny benchmark smoke.
- Latest mypy in the CI-like venv found one extra `benchmark.py` type issue; fixed with a narrow TypedDict for `best_sufficient`.

Release impact:

- CI/release smoke automation is no longer a release blocker.
- Stable release remains blocked by TODO-028 and real public project URLs.

## Release Docs Recheck

Recheck date: 2026-06-27

TODO-028 status: completed.

Documentation updates:

- README now separates release positioning, install modes, read-only discovery, runtime-probing commands, Agent Skill distribution, safety boundaries, and benchmark claim limits.
- The Agent Skill README now states installed-package, wheel, and source-checkout modes, and it warns before commands that may start configured MCP server commands or call configured MCP URLs.
- Public benchmark copy is constrained to the current measured result: 5/20 successful repo-task cases, about 69% weighted savings among successful sufficient cases, with insufficient cases treated as coverage gaps.
- Runtime safety wording is now near the quick start: `scan`, `eval`, and `benchmark` do not start MCP servers, while `doctor`, `tools`, `report`, and `slim` may execute configured stdio commands or call configured MCP URLs with configured headers.
- Current coverage limits explicitly mention root-level instruction discovery and the remaining nested instruction TODO.

Release impact:

- Release-facing install, safety, and benchmark-claim documentation are no longer release blockers.
- Stable public release is no longer blocked by missing public project URLs. Recheck benchmark wording after the public push and any fresh benchmark run.
- TODO-021 is now implemented as an opt-in coverage improvement; nested-instruction benchmark results should still be reported separately from root-only benchmark results.

## Evidence Checked

Passing checks:

- `python -m unittest discover -s tests -v`: latest release gate passed with 66 tests after TODO-027.
- `python -m ruff check .\src .\tests`: passed.
- `python -m ruff format --check .\src .\tests`: passed.
- `mypy .\src\save_the_token`: passed.
- `python -m pip wheel . -w .release-audit-dist --no-deps`: built `save_the_token-0.1.0-py3-none-any.whl`.
- Wheel contents include the `save_the_token` package and `Save-The-Token` console entry point metadata.
- `benchmark` generated strict JSON and Markdown reports for the current `.bench/repos` corpus.

Remaining failing or missing checks:

- Public repository, documentation, and issue tracker URLs are not configured because this checkout has no public git remote.
- Local source-tree benchmark execution needs explicit package installation or `PYTHONPATH=src`; the RDD command registry and README document the supported modes.
- TODO-021 nested instruction discovery is implemented. Broader major-repo claims still need a fresh benchmark run with `--include-nested-instructions`, reported separately from root-only results.

## Release Blockers

1. Packaging metadata is too thin.

   TODO-025 added README binding, a package URL, classifiers, keywords, license-file declaration, and optional dev dependencies. Stable release still needs real public repository, documentation, and issue tracker URLs once the project has a public remote.

2. License and changelog are absent.

   Completed by TODO-025.

3. CI is absent.

   Completed by TODO-027.

4. Static typing is not release-clean.

   Completed by TODO-026.

5. Product packaging target is ambiguous.

   Completed by TODO-025: wheel is CLI-only, source distribution includes docs/skills, and the Agent Skill bundle ships from `skills/save-the-token-mcp-doctor` in the repository.

6. Benchmark claim is narrow.

   Completed by TODO-028 as a documentation blocker. The reproducible benchmark currently shows 5/20 successful repo-task cases. Successful cases save about 69-71% weighted tokens, but the overall major-repo success rate is 25%. Public copy now states the narrow claim and rejects broad 70% savings across all repos.

7. Runtime probing safety needs stronger release docs.

   Completed by TODO-028. `scan`, `eval`, and `benchmark` are documented as non-runtime-probing commands, while `doctor`, `tools`, `report`, and `slim` are documented as commands that may start configured MCP server commands or call configured MCP URLs with configured headers.

8. Release gate commands must be reproducible.

   Completed by TODO-027 and TODO-028. CI installs `.[dev]`, and local docs/commands distinguish installed CLI usage from source-checkout `PYTHONPATH=src` usage.

## Registered Follow-up TODOs

- TODO-024: release readiness audit and TODO registration. Completed by this document.
- TODO-025: harden packaging metadata, license, changelog, `.gitignore`, and distribution shape. Completed by Packaging Recheck.
- TODO-026: fix or scope static typing and add release quality gates. Completed by Quality Gate Recheck.
- TODO-027: add CI workflow and release smoke checks. Completed by CI Recheck.
- TODO-028: document release positioning, install modes, safety boundaries, and benchmark claim limits. Completed by Release Docs Recheck.
- TODO-032: re-evaluate actual release sufficiency after distribution smoke and command reproducibility checks. Completed by Gate Recheck 3.

TODO-021 is completed: nested `AGENTS.md` / `CLAUDE.md` discovery is available through `--include-nested-instructions`.

Stable-release metadata follow-up:

- TODO-033: completed for public repository bootstrap. `pyproject.toml` now includes Package, Repository, Documentation, and Issues URLs for `https://github.com/ch040602/Save-The-Token`. Recheck stable release wording after the first public push and benchmark refresh.

## Release Positioning

Safe current copy:

> Local-first token budget and MCP diagnostic CLI for agent coding environments, with strict benchmarks that count savings only when required evidence remains sufficient.

Unsafe current copy:

> Saves 70% tokens on major repositories.

Better quantified copy:

> On the current 10-repo benchmark, Save-The-Token finds safe reductions in 5/20 repo-task cases. Successful cases reduce instruction context by about 69% weighted average, while uncovered or insufficient cases are reported as coverage gaps rather than savings.
