# Benchmark

This page records the current public benchmark claim for Save-The-Token.

## Run Shape

The benchmark uses local checkouts only. It does not clone repositories, start MCP servers, or call MCP URLs.

```bash
save-the-token benchmark \
  --repos-dir .bench/repos \
  --repo-commits .bench/repo-commits.json \
  --fallback-instruction CLAUDE.md \
  --include-nested-instructions \
  --json-out .bench/benchmark-current.json \
  --markdown-out .bench/benchmark-current.md
```

Tasks:

- `unit tests`
- `security review`

Repos:

| repo | commit |
|---|---|
| `django/django` | `99672c672a1537aeb0d1fd5911ca6f04154cc091` |
| `facebook/react` | `52912a14531dad54d7844c83bc0e35f2c6a74c11` |
| `fastapi/fastapi` | `b90c49aefad4958abdfbcacf9c2f816940a8f0e2` |
| `huggingface/transformers` | `d53986e104fc128420e38bdb362ce3d56c1b23af` |
| `kubernetes/kubernetes` | `5e7044610ed0bd6a9398e80486dcb090ca0cbb87` |
| `langchain-ai/langchain` | `00ad96ce85027502b62e5aa20a6d6161e969c454` |
| `microsoft/vscode` | `cfca77cfb987d3ab47d613ae20af8af04f5815eb` |
| `pallets/flask` | `36e4a824f340fdee7ed50937ba8e7f6bc7d17f81` |
| `rust-lang/rust` | `40557f6225e337d68c8d4f086557ce54135f5dd9` |
| `vercel/next.js` | `ff3a5f9dc94f4af6e5787f35efdc1d21842d18e3` |

## Summary

![Benchmark savings chart](assets/benchmark-savings.svg)

| metric | value |
|---|---:|
| Total repo-task cases | 20 |
| Eligible full-sufficient cases | 5 |
| Successful reduced cases | 5 |
| Success rate across all cases | 25.0% |
| Success rate among eligible cases | 100.0% |
| Weighted saving on successful cases | 69.3% |
| Median saving on successful cases | 63.5% |
| Compression/reorder successes | 1 |
| Selected-only successes | 4 |

## Successful Reductions

| repo | task | best variant | tokens | saving |
|---|---|---|---:|---:|
| `kubernetes/kubernetes` | `unit tests` | `compressed_context` | 345 -> 126 | 63.5% |
| `langchain-ai/langchain` | `unit tests` | `selected_context` | 7218 -> 3150 | 56.4% |
| `langchain-ai/langchain` | `security review` | `selected_context` | 7218 -> 846 | 88.3% |
| `vercel/next.js` | `unit tests` | `selected_context` | 5606 -> 2823 | 49.6% |
| `vercel/next.js` | `security review` | `selected_context` | 5606 -> 1034 | 81.6% |

## Caveats

- Savings are counted only when `full_context` and the reduced variant are both sufficient.
- Cases without sufficient `full_context` are coverage gaps, not token-saving successes.
- Evaluation is lexical over task terms and missing-fact counters; it is not semantic answer-quality grading.
- Compression and reordering savings are not claimed when they introduce missing facts.
- This run includes bounded nested instruction discovery; compare it separately from root-only benchmark runs.
