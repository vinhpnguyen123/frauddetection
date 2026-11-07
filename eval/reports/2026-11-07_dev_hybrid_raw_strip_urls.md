# Retrieval eval: hybrid_raw_strip_urls

- Set: `dev` (50 items), date 2026-11-07
- Git SHA: `08e2a64`
- Corpus: 43 documents, 1326 chunks, nomic-ai/nomic-embed-text-v1.5
- Labels: drafted by Claude (an AI model), reviewed item by item by Vinh
- Metrics use answerable items; the headline rows use `real` items only.
- P@5 ceiling: the best P@5 the labels allow, since few chunks may be relevant.
- Config `3ac4765cb724`: `{"method": "hybrid", "dense_mode": "exact", "query_expansion": false, "k_bm25": 50, "k_dense": 50, "rrf_k": 60, "rerank_model": null, "rerank_top_n": null, "parent_expansion": false}`

| Group | n | P@5 (95% CI) | P@5 ceiling | Recall@20 (95% CI) | MRR (95% CI) |
|---|---|---|---|---|---|
| real | 32 | 0.194 (0.138-0.256) | 0.419 | 0.842 (0.733-0.938) | 0.549 (0.411-0.686) |
| synthetic | 8 | 0.150 (0.075-0.250) | 0.250 | 0.875 (0.625-1.000) | 0.641 (0.291-1.000) |
| real / identifier | 13 | 0.231 (0.138-0.338) | 0.477 | 0.772 (0.593-0.923) | 0.590 (0.365-0.788) |
| real / concept | 13 | 0.123 (0.077-0.169) | 0.338 | 0.840 (0.673-0.981) | 0.455 (0.261-0.655) |
| real / multi_hop | 6 | 0.267 (0.200-0.400) | 0.467 | 1.000 (1.000-1.000) | 0.667 (0.375-0.917) |

Latency p50 154.5 ms, p95 197.6 ms.

Leaks: 0. Items with Recall@20 of 0: ['dev-005', 'dev-025', 'dev-036']
