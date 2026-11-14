# Retrieval eval: hybrid_raw_no_short

- Set: `dev` (50 items), date 2026-11-07
- Git SHA: `08e2a64`
- Corpus: 43 documents, 1271 chunks, nomic-ai/nomic-embed-text-v1.5
- Labels: drafted by Claude (an AI model), reviewed item by item by Vinh
- Metrics use answerable items; the headline rows use `real` items only.
- P@5 ceiling: the best P@5 the labels allow, since few chunks may be relevant.
- Config `3ac4765cb724`: `{"method": "hybrid", "dense_mode": "exact", "query_expansion": false, "k_bm25": 50, "k_dense": 50, "rrf_k": 60, "rerank_model": null, "rerank_top_n": null, "parent_expansion": false}`

| Group | n | P@5 (95% CI) | P@5 ceiling | Recall@20 (95% CI) | MRR (95% CI) |
|---|---|---|---|---|---|
| real | 32 | 0.200 (0.144-0.263) | 0.419 | 0.835 (0.721-0.930) | 0.535 (0.394-0.670) |
| synthetic | 8 | 0.150 (0.075-0.250) | 0.250 | 0.875 (0.625-1.000) | 0.640 (0.289-1.000) |
| real / identifier | 13 | 0.246 (0.138-0.369) | 0.477 | 0.772 (0.593-0.923) | 0.555 (0.348-0.756) |
| real / concept | 13 | 0.138 (0.092-0.185) | 0.338 | 0.821 (0.641-0.974) | 0.453 (0.255-0.655) |
| real / multi_hop | 6 | 0.233 (0.200-0.300) | 0.467 | 1.000 (1.000-1.000) | 0.667 (0.375-0.917) |

Latency p50 46.1 ms, p95 54.0 ms.

Leaks: 0. Items with Recall@20 of 0: ['dev-005', 'dev-025', 'dev-036']
