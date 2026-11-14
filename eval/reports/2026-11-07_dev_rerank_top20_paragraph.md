# Retrieval eval: rerank_top20_paragraph

- Set: `dev` (50 items), date 2026-11-07
- Git SHA: `08e2a64`
- Corpus: 43 documents, 6180 chunks, nomic-ai/nomic-embed-text-v1.5
- Labels: drafted by Claude (an AI model), reviewed item by item by Vinh
- Metrics use answerable items; the headline rows use `real` items only.
- P@5 ceiling: the best P@5 the labels allow, since few chunks may be relevant.
- Config `625f8bd4ae24`: `{"method": "rerank", "dense_mode": "exact", "query_expansion": false, "k_bm25": 50, "k_dense": 50, "rrf_k": 60, "rerank_model": "cross-encoder/ms-marco-MiniLM-L-6-v2", "rerank_top_n": 20, "parent_expansion": false}`

| Group | n | P@5 (95% CI) | P@5 ceiling | Recall@20 (95% CI) | MRR (95% CI) |
|---|---|---|---|---|---|
| real | 32 | 0.163 (0.088-0.256) | 0.519 | 0.582 (0.424-0.729) | 0.346 (0.223-0.484) |
| synthetic | 8 | 0.125 (0.050-0.200) | 0.250 | 0.562 (0.250-0.875) | 0.463 (0.175-0.775) |
| real / identifier | 13 | 0.231 (0.062-0.446) | 0.569 | 0.587 (0.308-0.865) | 0.384 (0.162-0.632) |
| real / concept | 13 | 0.092 (0.031-0.169) | 0.477 | 0.487 (0.250-0.731) | 0.205 (0.084-0.377) |
| real / multi_hop | 6 | 0.167 (0.100-0.200) | 0.500 | 0.778 (0.611-0.944) | 0.569 (0.319-0.833) |

Latency p50 802.3 ms, p95 1153.1 ms.

Leaks: 0. Items with Recall@20 of 0: ['dev-001', 'dev-004', 'dev-011', 'dev-012', 'dev-013', 'dev-015', 'dev-016', 'dev-019', 'dev-025', 'dev-035', 'dev-036', 'dev-037']
