# Retrieval eval: hybrid_raw_paragraph

- Set: `dev` (50 items), date 2026-11-07
- Git SHA: `08e2a64`
- Corpus: 43 documents, 6180 chunks, nomic-ai/nomic-embed-text-v1.5
- Labels: drafted by Claude (an AI model), reviewed item by item by Vinh
- Metrics use answerable items; the headline rows use `real` items only.
- P@5 ceiling: the best P@5 the labels allow, since few chunks may be relevant.
- Config `3ac4765cb724`: `{"method": "hybrid", "dense_mode": "exact", "query_expansion": false, "k_bm25": 50, "k_dense": 50, "rrf_k": 60, "rerank_model": null, "rerank_top_n": null, "parent_expansion": false}`

| Group | n | P@5 (95% CI) | P@5 ceiling | Recall@20 (95% CI) | MRR (95% CI) |
|---|---|---|---|---|---|
| real | 32 | 0.138 (0.088-0.188) | 0.519 | 0.582 (0.424-0.729) | 0.347 (0.222-0.482) |
| synthetic | 8 | 0.125 (0.050-0.200) | 0.250 | 0.562 (0.250-0.875) | 0.525 (0.200-0.875) |
| real / identifier | 13 | 0.123 (0.062-0.185) | 0.569 | 0.587 (0.308-0.865) | 0.337 (0.150-0.567) |
| real / concept | 13 | 0.138 (0.046-0.246) | 0.477 | 0.487 (0.250-0.731) | 0.319 (0.154-0.524) |
| real / multi_hop | 6 | 0.167 (0.100-0.200) | 0.500 | 0.778 (0.611-0.944) | 0.431 (0.250-0.667) |

Latency p50 192.6 ms, p95 235.9 ms.

Leaks: 0. Items with Recall@20 of 0: ['dev-001', 'dev-004', 'dev-011', 'dev-012', 'dev-013', 'dev-015', 'dev-016', 'dev-019', 'dev-025', 'dev-035', 'dev-036', 'dev-037']
