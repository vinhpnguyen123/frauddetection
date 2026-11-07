# Retrieval eval: rerank_top20_section_context

- Set: `dev` (50 items), date 2026-11-07
- Git SHA: `08e2a64`
- Corpus: 43 documents, 1326 chunks, nomic-ai/nomic-embed-text-v1.5
- Labels: drafted by Claude (an AI model), reviewed item by item by Vinh
- Metrics use answerable items; the headline rows use `real` items only.
- P@5 ceiling: the best P@5 the labels allow, since few chunks may be relevant.
- Config `625f8bd4ae24`: `{"method": "rerank", "dense_mode": "exact", "query_expansion": false, "k_bm25": 50, "k_dense": 50, "rrf_k": 60, "rerank_model": "cross-encoder/ms-marco-MiniLM-L-6-v2", "rerank_top_n": 20, "parent_expansion": false}`

| Group | n | P@5 (95% CI) | P@5 ceiling | Recall@20 (95% CI) | MRR (95% CI) |
|---|---|---|---|---|---|
| real | 32 | 0.238 (0.169-0.319) | 0.419 | 0.873 (0.760-0.963) | 0.487 (0.373-0.613) |
| synthetic | 8 | 0.175 (0.100-0.275) | 0.250 | 0.833 (0.583-1.000) | 0.603 (0.310-0.906) |
| real / identifier | 13 | 0.338 (0.185-0.508) | 0.477 | 0.828 (0.650-0.973) | 0.597 (0.384-0.795) |
| real / concept | 13 | 0.138 (0.092-0.185) | 0.338 | 0.859 (0.692-1.000) | 0.356 (0.217-0.549) |
| real / multi_hop | 6 | 0.233 (0.200-0.300) | 0.467 | 1.000 (1.000-1.000) | 0.533 (0.275-0.792) |

Latency p50 619.7 ms, p95 721.1 ms.

Leaks: 0. Items with Recall@20 of 0: ['dev-005', 'dev-025', 'dev-035']
