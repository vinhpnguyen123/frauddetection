# M4-Q2 label audit preparation

**Status: awaiting independent review by Vinh. Q2 is not complete.** No label has been accepted or edited. No retrieval/reranker behavior changed. Q1 commit/review/CI remain pending; the user explicitly requested Q2 preparation.

## Deliverables

- Versioned [methodology](../review/METHODOLOGY_V1.md), including duplicate, source-specific, historical, partial, cross-page and occurrence policies.
- [Draft relevance scopes for all 32 queries](../review/scopes_v1.json); these are proposed requirements, not reviewed gold.
- [Pool summary](2026-11-08_m4_q2_review_summary.json): 2,314 blinded units; original gold plus four-method top-20 union and immediate authorized neighbors. Local passage cards and administrator keys are separated under gitignored eval/.cache/relevance-review-v1.
- 125 unique blinded top-five sets for independent Evidence Sufficiency@5 judgment. No method labels or ranks are shown to the reviewer.
- [Original-label metrics](2026-11-08_m4_q2_original_metrics.json), per-query values, confidence intervals and paired MRR deltas. Historical definitions remain unchanged.

## Original labels, 32 real answerable queries

| Method | P@5 | Hit@5 | Chunk Recall@5 | Anchor Recall@20 | MRR | Normalized P@5 |
|---|---:|---:|---:|---:|---:|---:|
| bm25_raw | 0.193750 | 0.656250 | 0.509983 | 0.815104 | 0.472868 | 0.523438 |
| dense_exact | 0.181250 | 0.593750 | 0.449219 | 0.741319 | 0.491840 | 0.469271 |
| hybrid_raw | 0.200000 | 0.781250 | 0.526042 | 0.834635 | 0.534770 | 0.543750 |
| rerank_top20 | 0.218750 | 0.781250 | 0.560330 | 0.834635 | 0.482626 | 0.585938 |

All methods share the original mean P@5 ceiling 0.418750. Ceiling normalization averages per-query ratios; it is auxiliary and does not replace raw precision. Both hybrid and rerank have Hit@5 0.781250, so the reranker increases the amount of labeled evidence in the top-five without increasing the count of queries with a top-five hit.

Evidence Sufficiency@5 is **null, 0/32 judged per method**. Adjudicated metrics, method-order changes due to new labels and original-versus-adjudicated paired intervals are unavailable until review. These are not assumed to improve.

## Review workload

| Query | Existing gold chunks | Pooled occurrences | Blinded units |
|---|---:|---:|---:|
| dev-001 | 3 | 77 | 77 |
| dev-002 | 1 | 66 | 66 |
| dev-003 | 8 | 75 | 75 |
| dev-004 | 2 | 81 | 81 |
| dev-005 | 2 | 74 | 74 |
| dev-006 | 1 | 70 | 70 |
| dev-007 | 1 | 64 | 64 |
| dev-008 | 2 | 62 | 62 |
| dev-009 | 9 | 79 | 79 |
| dev-010 | 2 | 46 | 46 |
| dev-011 | 2 | 103 | 103 |
| dev-012 | 4 | 77 | 77 |
| dev-013 | 1 | 71 | 71 |
| dev-014 | 1 | 77 | 77 |
| dev-015 | 1 | 44 | 44 |
| dev-016 | 1 | 56 | 56 |
| dev-017 | 2 | 58 | 58 |
| dev-018 | 1 | 74 | 74 |
| dev-019 | 4 | 71 | 71 |
| dev-020 | 1 | 83 | 83 |
| dev-021 | 2 | 80 | 80 |
| dev-022 | 3 | 87 | 87 |
| dev-023 | 3 | 100 | 100 |
| dev-024 | 1 | 73 | 73 |
| dev-025 | 1 | 93 | 93 |
| dev-026 | 1 | 85 | 85 |
| dev-027 | 2 | 63 | 63 |
| dev-028 | 3 | 64 | 64 |
| dev-029 | 2 | 60 | 60 |
| dev-030 | 3 | 44 | 44 |
| dev-031 | 3 | 63 | 63 |
| dev-032 | 1 | 94 | 94 |

## Confirmed versus unresolved

- Confirmed: sparse existing labels cap measurable P@5; exact duplicate occurrences can be grouped for reviewer workload while retaining provenance. The build accepts no new relevance labels.
- Unresolved: whether unlabeled retrieved passages are relevant, whether current anchors establish every answer facet, and whether duplicate/historical-source policies alter method ordering. These require judgments, not automatic fixes.
- Explicit adjudication is queued for dev-005, dev-012, dev-019, dev-024, dev-031 and dev-032. In particular, dev-032 wording does not literally name the advisory identifier, despite the original note describing it as naming the document. The historical scope needs a reviewer decision.
- Pooling is not exhaustive; semantic near-duplicates remain separate. Exact normalized duplicates merge only within the same document/version. Source corpus fingerprint is inherited from Q1; a changed corpus requires fresh source traces.

## Verification and next gate

`make lint` passed (Ruff check/format and strict app mypy). `make test`: **492 backend + 15 embedder passed**, no failed or skipped tests reported. Warnings: 5 backend dependency deprecations and 1 embedder dependency deprecation. Q2 adds six unit tests plus one real-ParadeDB SQL isolation test. Final `git diff --check` passed. Commit, independent code review and CI remain pending.

Vinh must review the blinded passage cards and set-level sufficiency forms, resolve the six ambiguity cases, then freeze judgments before opening the administrator key. Next: create a separate adjudicated dataset/provenance, rematch approved anchors, rerun original/adjudicated metrics and document method-order changes. No Q3/Q4 retrieval experiment or default promotion is authorized by this report.
