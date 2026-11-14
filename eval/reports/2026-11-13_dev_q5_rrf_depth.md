# Q5 candidate depth and RRF k development experiment

32 real dev queries; fixed corpus, cached query vectors, SQL ACL and frozen AI-v3 labels. Original and all-public sensitivities appear in JSON. No reranker. Output20 in every arm. Baseline exactly matches Q1 leaf rankings and Q4 Hybrid rankings/scores.

| Arm | P@5 | Anchor Recall@20 | MRR | Leaf-union coverage | Warm SQL+fusion p50/p95 ms |
|---|---:|---:|---:|---:|---:|
| d25_k60 | 0.5125 | 0.6914 | 0.7583 | 0.8445 | 19.5/30.6 |
| d50_k60 | 0.5062 | 0.6617 | 0.7579 | 0.9221 | 19.5/30.4 |
| d100_k60 | 0.5062 | 0.6616 | 0.7579 | 0.9713 | 20.9/32.5 |
| d50_k10 | 0.5062 | 0.6839 | 0.7918 | 0.9221 | 19.5/30.3 |
| d50_k30 | 0.5062 | 0.6665 | 0.7579 | 0.9221 | 19.5/30.3 |
| d50_k100 | 0.5125 | 0.6605 | 0.7579 | 0.9221 | 19.5/30.3 |

## Predeclared primary tests

- d100_k60 vs baseline: recall_at_20 delta -0.000143, paired95% CI [-0.018892973856209146, 0.016882586367880488]; criteria met: False.
- d50_k30 vs baseline: mrr delta +0.000000, paired95% CI [0.0, 0.0]; criteria met: False.

Depth100 requires positive Recall20 lower bound and no mean P5/MRR decline; k30 requires positive MRR lower bound and no P5/Recall20 decline. Other arms are secondary, not selected winners. Two exploratory primary intervals are unadjusted. All conclusions are conditional on frozen AI labels; no gold promotion.

## Where evidence is lost

Counts below are distinct query-anchor groups, not query-average recall.

| Arm | Absent from leaf union | Present, lost at fused20 | Retained20 below5 | Retained5 |
|---|---:|---:|---:|---:|
| d25_k60 | 80 | 67 | 134 | 84 |
| d50_k60 | 44 | 107 | 131 | 83 |
| d100_k60 | 18 | 131 | 133 | 83 |
| d50_k10 | 44 | 108 | 131 | 82 |
| d50_k30 | 44 | 105 | 133 | 83 |
| d50_k100 | 44 | 108 | 129 | 84 |

Depth prefix failures: 0 (details in JSON). Each actual SQL limit was measured separately. k arms reuse identical50-per-branch lists. Group recovery/loss records include both branch ranks, fused ranks and one-branch-only flags.

Equal RRF sums reciprocal ranks from both branches; documents occurring in both lists can outrank a high-ranked single-branch document. Increasing depth can introduce additional two-branch competitors, so increased leaf-union coverage need not increase fused-top20 recall. The per-group transitions support specific cases without assigning a unique semantic cause.

## Validation and limits

Corpus/vector and index-definition fingerprints unchanged; all returned IDs checked against SQL-authorized exports. Protocol/input/runtime hashes verified. No network model inference or database writes. Sufficiency reused only for exact previously judged top5 sets; new sets remain unknown. Unreviewed-pool occurrence counts, all label sensitivities, per-query regressions, category sizes and observed latencies are in JSON. Latencies exclude query embedding and reflect warm local conditions, not deployment performance. Independent label validation, formal review/commit/CI and Q6 remain pending.


## Secondary signal and concrete retention case

The predeclared secondary k10 arm improves AI-primary MRR by +0.033881 (paired95% CI [0.001068, 0.085991]), with unchanged mean P5. Recall20 rises +0.022159 but its CI [-0.016334, 0.074720] spans zero; six queries regress on Recall20. This exploratory secondary interval is unadjusted for multiple comparisons and does not establish a selected production winner. It warrants a separately frozen confirmation in Q6, with label uncertainty and all method comparisons disclosed.

Depth25 Recall20 delta +0.029675 has CI [-0.018889, 0.083981], so no clear recall improvement. Do not select it solely by the highest observed mean.

For dev-003, ai-v3-group-074 stays at BM25 rank25 and dense rank42 with the same RRF score0.02156862745, but depth100 moves its fused rank20 to22. Its loss is competition from additional candidates, not failure to retrieve that evidence. Baseline contains365 primary groups:44 absent from the leaf union,107 present but outside fused20,214 retained in fused20. Depth100 reduces absent groups to18 while fusion losses rise to131. These are micro counts, not the query-averaged recall denominator.
