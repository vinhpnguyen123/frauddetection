# Q4 frozen-candidate window/fusion development experiment

32 real dev queries, same frozen Hybrid top20 and AI-v3 primary/direct-source anchor groups in every arm. Original/all-public label sensitivities, paired intervals and per-query regressions are in JSON. This is exploratory AI-labeled development evidence; no independent-human benchmark claim or default promotion.

Protocol frozen before inference: preserve current prefix scores, add sentence-aware tail windows of at most384 document tokens with target64-token overlap and actual query/special-token budget checks; take max per passage. F=equal RRF(H,R), k60. FW=equal RRF(H,W), k60. Every fitting passage keeps its exact R score. Max aggregation can favor long passages; no post-outcome parameter tuning.

| Arm | Description | P@5 | Anchor Recall@20 | MRR | Extra rerank p50 / p95 ms |
|---|---|---:|---:|---:|---:|
| H | Frozen Hybrid | 0.506 | 0.662 | 0.758 | 0.0 / 0.0 |
| R | Current reranker | 0.575 | 0.662 | 0.799 | 890.7 / 1488.0 |
| W | Prefix + tail windows, max | 0.575 | 0.662 | 0.795 | 1087.8 / 2403.0 |
| F | RRF(H,R) | 0.537 | 0.662 | 0.801 | 890.9 / 1488.7 |
| FW | RRF(H,W) | 0.550 | 0.662 | 0.800 | 1087.9 / 2403.3 |

## Predeclared primary tests

| Contrast | MRR delta (paired 95% CI) | P@5 delta | Replacement criteria met? |
|---|---|---:|---|
| W−R | -0.004 [-0.012, +0.000] | +0.000 | False |
| F−R | +0.002 [-0.078, +0.079] | -0.037 | False |

Acceptance requires positive paired MRR lower bound versus R, no mean P@5 decline, unchanged candidates/Recall20 and SQL authorization. Replacing H additionally requires a clear MRR benefit over H with latency disclosed. Two primary tests use unadjusted exploratory intervals (1,000 query bootstrap resamples, seed20261107); they do not account for label error. FW is a secondary contrast, not a post-hoc selected primary.

## Checks and interpretation

- Current R reproduces all32 Q3 body reranker orderings. All640 candidate occurrences were SQL-reauthorized and content/version-checked before/after; main corpus fingerprint is unchanged.
- The current pass had 640 input pairs; 235 additional tail windows were scored. Every tail input fits the actual tokenizer budget, every original document token is covered, and fitting-passage scores remain exactly R.
- Known anchor-instance full-quote visibility: R 215/224; W 223/224. Visibility is not answer correctness.
- Every arm returns exactly the same20 candidates, so anchor Recall@20 is identical by construction and verified.
- New top5 evidence sets are not automatically judged sufficient from passage labels; unknowns remain null.
- Actual window offsets, token hashes, diagnostics, warm incremental latency and runtime/input hashes are retained; no source text is published in this report.
- No database writes or external model calls. The offline worker used the pinned existing embedder-provider implementation and exited after inference.

## Previously identified fitting-input cases

| Query | Label version | H first relevant rank | R rank | W rank | F rank | FW rank |
|---|---|---:|---:|---:|---:|---:|
| dev-006 | original | 1 | 5 | 5 | 2 | 2 |
| dev-006 | AI_primary_v3 | 1 | 5 | 5 | 2 | 2 |
| dev-011 | original | 3 | 13 | 13 | 7 | 7 |
| dev-011 | AI_primary_v3 | 1 | 1 | 1 | 1 | 1 |

The window treatment restores visible evidence but does not resolve the fitting-input regressions: dev-006 remains rank5 under W, and dev-011 original-anchor evidence remains rank13. Fusion partially restores those ranks but lowers aggregate P@5. This does not prove a unique model-training or semantic cause, nor that every possible window/fusion strategy fails.

The JSON includes fit-first-relevant and truncated-first-relevant subsets, as well as the size of the fully fitting-query subset. Do not claim truncation explains all ranking behavior. All reported gains/losses are conditional on the frozen labels and this candidate pool. Pending label validation and slice/commit/CI gates are unchanged.
