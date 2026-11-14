# Q2 AI-assisted frozen-trace diagnostic

32 real, answerable dev queries. AI drafted the labels; Vinh read and accepted the Vietnamese summary. This is **not independent expert or card-by-card human validation**, and it does not close the Q2 adjudication gate. Rankings, models, corpus, original gold and defaults remain unchanged.

This run rescores saved rankings; differences below are **label sensitivity, not retrieval improvement**. Synthetic/internal policy passages are excluded from real-source relevance counts. Public-source secondary corroboration may count as partial retrieval evidence, but cannot substitute for primary evidence when judging full-answer sufficiency.

| Method | Original P@5 (95% CI) | AI public P@5 (95% CI) | Paired label delta (95% CI) | AI sufficient sets / 32 |
|---|---|---|---|---|
| bm25 | 0.194 [0.131, 0.256] | 0.556 [0.456, 0.656] | +0.362 [+0.269, +0.450] | 20/32 |
| dense | 0.181 [0.119, 0.256] | 0.531 [0.425, 0.637] | +0.350 [+0.250, +0.450] | 19/32 |
| hybrid | 0.200 [0.144, 0.263] | 0.562 [0.469, 0.656] | +0.362 [+0.256, +0.463] | 21/32 |
| reranked | 0.219 [0.150, 0.306] | 0.625 [0.525, 0.719] | +0.406 [+0.306, +0.506] | 22/32 |

Original anchor Recall@20 and both label versions of MRR are recorded per query and with aggregate CIs in the JSON. **AI anchor Recall@20 is null**: 42 visually checked locator quotes are not a complete replacement anchor inventory. No changed recall denominator is presented as the historical metric.

All 125 anonymous sets are mapped to the four methods using their exact top-five occurrence IDs; identical sets can be reused across methods, yielding 128 method/query judgments. Sufficiency values are AI proposals accepted at summary level, not a new human benchmark.

Provenance: JSON records exact input/script hashes, bootstrap seed/resamples and per-query results. Current corpus was checked read-only with RetrievalContext and the central SQL ACL predicate before this run. That check is not a substitute for a full security evaluation. No held-out data was consulted.

Remaining Q2 work: complete primary-evidence eligibility and anchor inventory, retain grouping/occurrence provenance, and record the required validation scope before official adjudicated comparisons. Q1 review/commit/CI gates remain separately pending.
