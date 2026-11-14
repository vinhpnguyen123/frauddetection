# Q3 section-context A/B/C/D — development experiment

Read: IMPLEMENTATION_PLAN.md; CLAUDE.md; docs/CONTEXT.md; docs/ARCHITECTURE.md; docs/SCHEMA.md; docs/CONVENTIONS.md; docs/GIT_RULES.md; docs/DATASET.md; docs/EVALUATION.md.

32 real answerable dev queries. Same frozen labels, chunk IDs/bodies/versions/ACL, frozen baseline BM25 top50 (SQL-reauthorized), dense exact top50, RRF k60 and MiniLM top20 across treatments. Two throwaway database copies; only the section copy’s embeddings changed. Production corpus and defaults remain unchanged. This dirty-tree exploratory experiment does not close pending Q1/Q2 validation/commit/CI gates.

Protocol and label/runtime hashes were frozen before treatment measurements. V3 labels are AI-reviewed, not independently human validated. Original-label and all-public sensitivity are in JSON.

| Variant | Document embedding | Reranker input | AI primary P@5 | AI primary anchor Recall@20 | AI primary MRR |
|---|---|---|---:|---:|---:|
| A | body | body | 0.575 | 0.662 | 0.799 |
| B | section_path + newline + body | body | 0.594 | 0.694 | 0.802 |
| C | body | section_path + newline + body | 0.569 | 0.662 | 0.781 |
| D | section_path + newline + body | section_path + newline + body | 0.588 | 0.694 | 0.786 |

## Predeclared primary contrasts

| Contrast | Metric | Mean delta | Paired 95% CI | Outcome |
|---|---|---:|---|---|
| embedding_B_minus_A | recall_at_20 | +0.032 | [-0.015, +0.084] | no clear improvement under the predeclared paired-bootstrap rule |
| reranker_C_minus_A | mrr | -0.018 | [-0.109, +0.074] | no clear improvement under the predeclared paired-bootstrap rule |

Intervals use 1,000 fixed-seed paired query bootstrap resamples; two exploratory primary hypotheses with unadjusted intervals. They do not include label uncertainty. Both secondary contrasts, all original-label sensitivities, per-query regressions and confidence intervals are in JSON. No isolated query rescue establishes a winner.

## Controls and limitations

- Body control reproduces frozen Q1 hybrid top20 ordering for all32 queries; frozen lexical top50 supplied to both arms is identical and SQL-reauthorized. Raw treatment-index BM25 is not used because embedding UPDATEs changed its ranking in the rejected control attempt.
- Same ordered candidate inputs for A/C and B/D; reranker-only Recall@20 is identical by construction and verified.
- Each anchor is rematched in each copy using RetrievalContext and SQL ACL. No chunk-ID carryover without content/version checks.
- Main vector/content fingerprints are unchanged before/after; both owned copies were removed.
- New/unreviewed top5 passages and unknown sufficiency are recorded, never counted as human judgments.
- Token visibility uses actual reranker preprocessing diagnostics; adding section paths can consume body token budget.

| Variant | Truncated pairs / 640 | Observed rerank p50 / p95 ms | Sufficiency coverage / 32 |
|---|---:|---:|---:|
| A | 235/640 | 683.3 / 1061.5 | 32/32 |
| B | 243/640 | 700.0 / 883.7 | 22/32 |
| C | 265/640 | 663.7 / 975.4 | 11/32 |
| D | 271/640 | 664.2 / 874.5 | 7/32 |

Latency includes diagnostics overhead and this machine’s observed load/swap; no clean latency or speedup claim. Models and revisions are fixed in JSON. Full per-query scores, candidate IDs, exact input hashes, visibility diagnostics and machine conditions support reproduction.

No production promotion. A positive contrast warrants review and a clean committed reproduction, with independent label validation and missing evidence-set review retained as separate work.
