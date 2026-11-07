# Retrieval eval: hybrid_raw_chunk_300

- Set: `dev` (50 items), date 2026-11-07
- Git SHA: `08e2a64`
- Corpus: 43 documents, 1759 chunks, nomic-ai/nomic-embed-text-v1.5
- Labels: drafted by Claude (an AI model), reviewed item by item by Vinh
- Metrics use answerable items; the headline rows use `real` items only.
- P@5 ceiling: the best P@5 the labels allow, since few chunks may be relevant.
- Config `3ac4765cb724`: `{"method": "hybrid", "dense_mode": "exact", "query_expansion": false, "k_bm25": 50, "k_dense": 50, "rrf_k": 60, "rerank_model": null, "rerank_top_n": null, "parent_expansion": false}`

| Group | n | P@5 (95% CI) | P@5 ceiling | Recall@20 (95% CI) | MRR (95% CI) |
|---|---|---|---|---|---|
| real | 32 | 0.181 (0.119-0.250) | 0.444 | 0.805 (0.672-0.911) | 0.500 (0.355-0.655) |
| synthetic | 8 | 0.150 (0.075-0.250) | 0.250 | 0.625 (0.250-1.000) | 0.625 (0.250-1.000) |
| real / identifier | 13 | 0.231 (0.108-0.369) | 0.477 | 0.718 (0.513-0.923) | 0.558 (0.329-0.785) |
| real / concept | 13 | 0.138 (0.077-0.200) | 0.385 | 0.840 (0.673-0.981) | 0.445 (0.264-0.673) |
| real / multi_hop | 6 | 0.167 (0.067-0.267) | 0.500 | 0.917 (0.750-1.000) | 0.496 (0.218-0.778) |

Latency p50 93.2 ms, p95 121.7 ms.

Leaks: 0. Items with Recall@20 of 0: ['dev-001', 'dev-005', 'dev-025', 'dev-035', 'dev-036', 'dev-037']
