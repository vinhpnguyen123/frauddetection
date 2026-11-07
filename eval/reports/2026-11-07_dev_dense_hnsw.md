# Retrieval eval: dense_hnsw

- Set: `dev` (50 items), date 2026-11-07
- Git SHA: `139b0e5`
- Corpus: 43 documents, 1326 chunks, nomic-ai/nomic-embed-text-v1.5
- Labels: drafted by Claude (an AI model), reviewed item by item by Vinh
- Metrics use answerable items; the headline rows use `real` items only.
- P@5 ceiling: the best P@5 the labels allow, since few chunks may be relevant.
- Config `057d845954c5`: `{"method": "dense", "dense_mode": "hnsw", "query_expansion": false, "k_bm25": 50, "k_dense": 50, "rrf_k": 60, "rerank_model": null, "rerank_top_n": null}`

| Group | n | P@5 (95% CI) | P@5 ceiling | Recall@20 (95% CI) | MRR (95% CI) |
|---|---|---|---|---|---|
| real | 32 | 0.181 (0.119-0.256) | 0.419 | 0.741 (0.613-0.851) | 0.492 (0.338-0.651) |
| synthetic | 8 | 0.150 (0.075-0.250) | 0.250 | 0.750 (0.500-1.000) | 0.538 (0.225-0.882) |
| real / identifier | 13 | 0.231 (0.092-0.385) | 0.477 | 0.671 (0.453-0.863) | 0.521 (0.275-0.779) |
| real / concept | 13 | 0.123 (0.062-0.185) | 0.338 | 0.769 (0.577-0.936) | 0.462 (0.247-0.680) |
| real / multi_hop | 6 | 0.200 (0.067-0.333) | 0.467 | 0.833 (0.667-1.000) | 0.492 (0.201-0.783) |

Latency p50 56.4 ms, p95 132.2 ms.

Leaks: 0. Items with Recall@20 of 0: ['dev-001', 'dev-005', 'dev-025', 'dev-036', 'dev-037']
