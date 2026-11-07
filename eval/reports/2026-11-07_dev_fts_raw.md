# Retrieval eval: fts_raw

- Set: `dev` (50 items), date 2026-11-07
- Git SHA: `139b0e5`
- Corpus: 43 documents, 1326 chunks, nomic-ai/nomic-embed-text-v1.5
- Labels: drafted by Claude (an AI model), reviewed item by item by Vinh
- Metrics use answerable items; the headline rows use `real` items only.
- P@5 ceiling: the best P@5 the labels allow, since few chunks may be relevant.
- Config `140866467657`: `{"method": "fts", "dense_mode": null, "query_expansion": false, "k_bm25": 50, "k_dense": 50, "rrf_k": 60, "rerank_model": null, "rerank_top_n": null}`

| Group | n | P@5 (95% CI) | P@5 ceiling | Recall@20 (95% CI) | MRR (95% CI) |
|---|---|---|---|---|---|
| real | 32 | 0.144 (0.075-0.219) | 0.419 | 0.613 (0.438-0.770) | 0.254 (0.155-0.355) |
| synthetic | 8 | 0.050 (0.000-0.125) | 0.250 | 0.250 (0.000-0.625) | 0.250 (0.000-0.625) |
| real / identifier | 13 | 0.154 (0.062-0.277) | 0.477 | 0.587 (0.356-0.837) | 0.342 (0.167-0.538) |
| real / concept | 13 | 0.108 (0.031-0.215) | 0.338 | 0.577 (0.308-0.846) | 0.180 (0.076-0.292) |
| real / multi_hop | 6 | 0.200 (0.033-0.400) | 0.467 | 0.750 (0.417-1.000) | 0.224 (0.088-0.378) |

Latency p50 21.7 ms, p95 44.8 ms.

Leaks: 0. Items with Recall@20 of 0: ['dev-001', 'dev-005', 'dev-006', 'dev-011', 'dev-012', 'dev-020', 'dev-022', 'dev-023', 'dev-024', 'dev-025', 'dev-028', 'dev-035', 'dev-036', 'dev-037', 'dev-038', 'dev-039', 'dev-040']
