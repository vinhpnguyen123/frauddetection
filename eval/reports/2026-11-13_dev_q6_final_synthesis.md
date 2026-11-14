# Q6 comparable development synthesis

32 real answerable dev queries; same unchanged corpus and frozen labels. Quality table uses AI-v3 primary/direct-source anchor groups; original and all-public results, paired differences, per-query rankings, source hashes and category sample sizes are in JSON. AI-v3 is not independently human validated. This is development evidence, not a final committed benchmark.

| Method | P@5 (95% CI) | Anchor Recall@20 (95% CI) | MRR (95% CI) | Known sufficient / known sets / total |
|---|---|---|---|---|
| fts | 0.3312 [0.2125, 0.4562] | 0.4157 [0.2992, 0.5265] | 0.4398 [0.2926, 0.5819] | 0 / 0 / 32 |
| bm25 | 0.4688 [0.3563, 0.5750] | 0.6549 [0.5335, 0.7585] | 0.6581 [0.5074, 0.7897] | 13 / 20 / 32 |
| dense_exact | 0.4875 [0.3750, 0.6000] | 0.6104 [0.5105, 0.7073] | 0.7484 [0.6115, 0.8748] | 18 / 32 / 32 |
| dense_hnsw | 0.4875 [0.3750, 0.6000] | 0.6104 [0.5105, 0.7073] | 0.7484 [0.6115, 0.8748] | 18 / 32 / 32 |
| hybrid_raw | 0.5062 [0.4000, 0.6125] | 0.6617 [0.5657, 0.7545] | 0.7579 [0.6287, 0.8765] | 20 / 32 / 32 |
| rerank_top20 | 0.5750 [0.4688, 0.6813] | 0.6617 [0.5657, 0.7545] | 0.7992 [0.6802, 0.9010] | 21 / 32 / 32 |
| rerank_top50 | 0.6000 [0.5000, 0.7063] | 0.7249 [0.6302, 0.8118] | 0.8017 [0.6833, 0.9033] | 17 / 24 / 32 |
| hybrid_k10 | 0.5062 [0.4000, 0.6125] | 0.6839 [0.5808, 0.7789] | 0.7918 [0.6667, 0.8993] | 15 / 24 / 32 |

FTS/BM25 use standard query expansion; Hybrid uses raw queries and exact dense. All methods return at most20. BM25 raw sensitivity is in Q2/Q5. Reranker top20/top50 rows reuse archived Q1 inference on unchanged source data after exact live leaf parity and SQL reauthorization; other rows use fresh SQL with frozen query vectors. No reranker scores were invented or recomputed from labels.

## k10 repeat and sensitivity

All32 k10 and k60 rankings and scores exactly reproduce Q5. Repeating the same questions is not independent validation. k10 was a Q5 secondary arm selected after seeing its result. No new labels, questions or hyperparameters were added.

| Label set | MRR delta | Six-arm adjusted percentile interval | Positive / negative queries | Leave-one-out delta range |
|---|---:|---|---|---|
| original | +0.038035 | [-0.003491300366300365, 0.11220238095238096] | 6 / 3 | [0.017757, 0.041950] |
| AI_primary_v3 | +0.033881 | [0.0, 0.10635683760683762] | 4 / 0 | [0.013468, 0.034974] |
| AI_all_public_v3 | +0.035719 | [0.0, 0.10819507290095526] | 5 / 0 | [0.015366, 0.036871] |

100,000 paired query bootstrap resamples, seed20261107; interval level1−0.05/6. This sensitivity covers six Q5 arms only and cannot account for the whole adaptive research history or label uncertainty. Original/all-public sensitivity must be considered alongside the primary AI inventory.

## Configuration decision

Keep the research baseline: raw query, body embeddings, exact dense,50 candidates per branch, equal RRF k60, output20, no reranker. Retain k10 as a promising separately named experiment. Do not promote it to production or accepted gold from this same-data repetition. No locked application pipeline decision is changed.

Q3 section-context primary comparisons showed no clear gain. Q4 specifically tested prefix-preserving tail windows and equal ranking fusion; neither qualified as a replacement. Q5 increased pool coverage with depth100 without improving fused-top20 recall. These outcomes do not prove all representation, window or fusion techniques fail.

## Latency and security scope

Fresh SQL timings and archived Q4 incremental reranker timings are reported separately in JSON. Cached query vectors remove embedding inference; archived reranker quality has no fresh end-to-end timing. A mixed timing column would be misleading, so no deployment-speed comparison is claimed. Full pipeline latency must be measured on clean committed configurations.

All fresh/reused output IDs passed SQL-authorized export checks for these32 queries; corpus/vector/index fingerprints stayed unchanged. Zero unreadable output IDs were detected in this run. This does not replace adversarial tenant tests or establish refusal/citation-support correctness. No generation ran.

Sufficiency is reused only when top5 matches an existing AI-judged set exactly; unknown new sets remain null. Positive passage labels alone do not imply a complete answer. Unpooled result counts are explicit in JSON; expanded-anchor metrics may undercount their relevance.

## Remaining gates

Development synthesis is ready. Independent validation of AI-v3 refinements, judgments for new top5 sets, clean committed comparable pipeline measurements, formal slice/milestone review and CI remain open. Existing test sanity budget is untouched; no held-out set was consulted and no additional test run is authorized by this report.


## Label coverage and reranker interpretation

The frozen-anchor scores do not establish exhaustive relevance for newly retrieved unpooled passages. FTS has42 unreviewed top5 occurrences and250 top20 occurrences; expanded BM25 has7 and57; rerank top50 has0 and51. Other reported methods have0 outside-pool occurrences at both cutoffs. Do not interpret absence from the frozen anchor inventory as a new human negative judgment.

On AI-primary labels, rerank top20 P5 delta is +0.06875 (paired95% CI [0.01875,0.11875]); rerank top50 P5 delta is +0.09375 [0.03125,0.15625]. Thus there is a conditional precision signal, not a claim that reranking never helps. Their MRR deltas are +0.04131 [−0.07139,0.15088] and +0.04382 [−0.06927,0.15340], respectively. Under original labels, both MRR delta intervals span0 and their means decrease. Label sensitivity, unjudged evidence, different candidate budgets and missing fresh comparable end-to-end latency prevent treating the highest observed mean as a validated replacement.
