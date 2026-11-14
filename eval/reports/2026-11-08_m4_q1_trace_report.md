# M4-Q1 retrieval observability validation

Development-only, pre-commit validation. No corpus, label, retrieval configuration or production-default change. Original M4 artifacts remain intact. Final reproducibility requires a clean committed checkout and CI. Answer sufficiency is unjudged, pending Q2.

## Provenance and metric parity

| Budget | P@5 | Recall@20 | MRR | Instrumented p50/p95 ms | Historical per-item parity |
|---|---:|---:|---:|---:|---|
| 20 | 0.218750 | 0.834635 | 0.482626 | 660.6/978.3 | Exact, all 50 items |
| 50 | 0.225000 | 0.828125 | 0.478813 | 1691.1/2451.6 | Exact, all 50 items |

Timing includes extra tokenizer inspection; nested stage times are not additive. These are observations under existing swap pressure, not a clean-machine speed comparison.

Artifacts:

- [2026-11-08_dev_rerank_top20_q1_trace_validation.json](2026-11-08_dev_rerank_top20_q1_trace_validation.json) and [2026-11-08_dev_rerank_top20_q1_trace_validation.trace.jsonl](2026-11-08_dev_rerank_top20_q1_trace_validation.trace.jsonl). Each JSON records source/input/dataset hashes, model revisions, corpus/vector fingerprint, index definitions and machine conditions.
- [2026-11-08_dev_rerank_top50_q1_trace_validation.json](2026-11-08_dev_rerank_top50_q1_trace_validation.json) and [2026-11-08_dev_rerank_top50_q1_trace_validation.trace.jsonl](2026-11-08_dev_rerank_top50_q1_trace_validation.trace.jsonl). Each JSON records source/input/dataset hashes, model revisions, corpus/vector fingerprint, index definitions and machine conditions.

Top-20 run initial swap: `vm.swapusage: total = 6144.00M  used = 5692.44M  free = 451.56M  (encrypted)`.

## All 32 real answerable queries

Ranks refer to the first existing gold chunk; `—` means absent. Leaf budgets are 50. RRF columns are replayed from the same captured candidates and verified against the actual hybrid prefix. R20/R50 return 20.

| Query | BM25 | Dense | RRF20 | RRF50 | R20 final | R50 final | Missing leaf anchors | Lost at RRF20 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| dev-001 | 11 | 22 | 13 | 13 | 3 | 3 | 1 | 0 |
| dev-002 | 1 | 1 | 1 | 1 | 1 | 1 | 0 | 0 |
| dev-003 | 5 | 1 | 1 | 1 | 1 | 1 | 0 | 1 |
| dev-004 | 2 | 14 | 7 | 7 | 1 | 1 | 0 | 0 |
| dev-005 | 21 | 45 | — | 27 | — | 16 | 0 | 1 |
| dev-006 | 6 | 1 | 1 | 1 | 5 | 5 | 0 | 0 |
| dev-007 | 2 | 5 | 2 | 2 | 1 | 1 | 0 | 0 |
| dev-008 | 1 | 17 | 3 | 3 | 3 | 3 | 0 | 1 |
| dev-009 | 1 | 3 | 2 | 2 | 1 | 1 | 0 | 0 |
| dev-010 | 1 | 1 | 1 | 1 | 1 | 1 | 0 | 0 |
| dev-011 | 8 | 9 | 3 | 3 | 13 | — | 0 | 2 |
| dev-012 | 14 | 1 | 3 | 3 | 6 | 6 | 1 | 1 |
| dev-013 | 1 | 1 | 1 | 1 | 3 | 3 | 0 | 0 |
| dev-014 | 1 | 3 | 2 | 2 | 1 | 1 | 0 | 0 |
| dev-015 | 12 | 4 | 6 | 6 | 5 | 5 | 0 | 0 |
| dev-016 | 1 | 1 | 1 | 1 | 6 | 6 | 0 | 0 |
| dev-017 | 8 | 17 | 10 | 10 | 7 | 7 | 1 | 0 |
| dev-018 | 9 | 9 | 7 | 7 | 5 | 5 | 0 | 0 |
| dev-019 | 3 | 1 | 1 | 1 | 1 | 1 | 0 | 0 |
| dev-020 | 39 | 1 | 5 | 5 | 2 | 2 | 0 | 0 |
| dev-021 | 2 | 1 | 1 | 1 | 3 | 3 | 0 | 0 |
| dev-022 | 8 | 12 | 3 | 3 | 11 | 15 | 1 | 0 |
| dev-023 | 5 | 1 | 1 | 1 | 2 | 2 | 0 | 2 |
| dev-024 | 2 | 9 | 4 | 4 | 3 | 4 | 0 | 0 |
| dev-025 | 40 | — | — | — | — | — | 0 | 2 |
| dev-026 | 1 | 16 | 5 | 5 | 3 | 3 | 0 | 0 |
| dev-027 | 1 | 5 | 1 | 1 | 4 | 4 | 0 | 0 |
| dev-028 | 4 | 2 | 2 | 2 | 2 | 2 | 0 | 0 |
| dev-029 | 4 | 7 | 4 | 4 | 4 | 4 | 0 | 0 |
| dev-030 | 1 | 1 | 1 | 1 | 1 | 1 | 0 | 0 |
| dev-031 | 2 | 9 | 4 | 4 | 5 | 5 | 0 | 0 |
| dev-032 | 2 | 1 | 1 | 1 | 1 | 1 | 0 | 0 |

## Known fusion retention losses

These are cutoff effects, not evidence that the RRF implementation is incorrect. Each row is a labeled chunk present in a leaf but absent from the RRF top-20; `—` is absent at the recorded cutoff. Score uses the configured sum of 1/(60 + leaf rank).

| Query | Chunk ID | BM25 rank | Dense rank | RRF50 rank | RRF score |
|---|---|---:|---:|---:|---:|
| dev-003 | `639035c4-7b9d-48cd-9970-487ea8a86fad` | — | 17 | 26 | 0.012987013 |
| dev-005 | `99a506e6-48ba-43d7-913b-fa0302653706` | 21 | — | 38 | 0.012345679 |
| dev-005 | `c3b4c3f1-e71e-41a0-b250-6ebfe99d9558` | 31 | 45 | 27 | 0.020512821 |
| dev-008 | `80b2b109-2115-4568-a8c3-7f012ffeb581` | 2 | — | 30 | 0.016129032 |
| dev-011 | `085b967a-5f48-4e16-b216-6d4c4477a2ec` | 12 | — | 27 | 0.013888889 |
| dev-012 | `60e42701-2ab4-45ce-a197-676500dff2e4` | — | 24 | 48 | 0.011904762 |
| dev-012 | `b4685118-516f-415d-9a53-f9a779afcb0b` | 14 | — | 37 | 0.013513514 |
| dev-025 | `f2d7883e-7740-4f1b-9acd-0cb8cdc4f87f` | 40 | — | >50 | 0.010000000 |

The traces retain every competing candidate, leaf position and score for reconstruction. In particular, top-50 fusion does not retain dev-025 gold despite its BM25 rank 40; a deeper reranker cannot repair evidence absent from its input. dev-012 also has an anchor absent from both top-50 leaves. These are label-relative findings; duplicate/source-equivalent relevance awaits Q2.

## Concrete reranker inversions and visibility

| Query | Chunk ID | RRF rank | Reranked rank | Model score | Effective/full tokens | Truncated | Full anchor visible | Label match visible |
|---|---|---:|---:|---:|---|---|---|---|
| dev-006 | `9f2a492d-a89e-4d62-9be3-007481b306a6` | 1 | 5 | 6.364349 | 87/87 | False | True | True |
| dev-011 | `cc19310d-95b5-492f-a034-2f04132ef110` | 3 | 13 | -1.787633 | 229/229 | False | True | True |
| dev-016 | `240b0aee-9106-415f-b02d-f86372f3d254` | 1 | 6 | 0.698164 | 512/539 | True | True | True |
| dev-022 | `8bc036b2-597a-4aed-98cd-d62472c7a943` | 3 | 19 | -8.544744 | 278/278 | False | True | True |
| dev-027 | `f17584c0-fff3-47fd-bea2-2fc8543f4f2c` | 1 | 4 | 1.503207 | 512/579 | True | True | True |

For dev-022 the table tracks the original rank-3 chunk itself (3 → 19); another gold chunk becomes the first hit at rank 11. Chunk-level inversion and query-level first-hit change are different diagnostics.

Across the 32 real queries, first-hit changes are 11 improved, 10 worsened and 11 unchanged. Top-20 reranking preserves candidate membership and Recall@20, while redistributing evidence within that set. P@5 can rise while rank-one evidence is demoted, reducing MRR. Tokenization is verified against actual pinned model preprocessing; fully visible regressions cannot be explained by truncation alone.

## Verification and limits

- `make lint`: Ruff check/format and mypy passed.
- `make test`: 485 backend tests passed (5 dependency deprecation warnings); 15 embedder tests passed (1 dependency deprecation warning). No failed or skipped tests reported.
- Eight new ParadeDB integration cases cover exact ranking/metric parity across six methods, foreign-gold exclusion, and aborting unauthorized observed IDs. ML providers are fake in tests; live model validation is confined to these dev evaluations.
- Both trace files contain 50 queries. Real answerable (32), synthetic answerable (8), and refusal (10) remain distinct in companion metrics; the table above uses only real answerable queries.
- Per-item quality metrics match the historical runs exactly. Exact normal/instrumented ranking and score parity is verified by the six-method integration test; historical reports did not retain candidate scores. Instrumentation adds SQL export validation, replay, and tokenizer work; no clean paired overhead estimate is available.
- No human judgment establishes complete-answer sufficiency yet. No labels were corrected. Q2 must investigate ambiguous/partial and duplicate evidence before behavioral experiments.
- No held-out test run, corpus mutation, default promotion, paid API call, commit, push or CI run occurred in Q1.

## Q1 decision

Observability is locally verified. Retain the approved hybrid_raw research baseline and optional reranking. Stop at the Q1 review/commit/CI gate; Q2 owns blinded relevance review. Do not infer an experiment winner from these diagnostics. Final clean-checkout reproduction and CI remain pending.
