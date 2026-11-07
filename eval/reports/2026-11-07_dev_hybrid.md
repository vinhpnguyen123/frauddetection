# Retrieval eval: hybrid

- Set: `dev` (50 items), date 2026-11-07
- Git SHA: `139b0e5`
- Corpus: 43 documents, 1326 chunks, nomic-ai/nomic-embed-text-v1.5
- Labels: drafted by Claude (an AI model), reviewed item by item by Vinh
- Metrics use answerable items; the headline rows use `real` items only.
- P@5 ceiling: the best P@5 the labels allow, since few chunks may be relevant.
- Config `3aa7f8b9b481`: `{"method": "hybrid", "dense_mode": "exact", "query_expansion": true, "k_bm25": 50, "k_dense": 50, "rrf_k": 60, "rerank_model": null, "rerank_top_n": null}`

| Group | n | P@5 (95% CI) | P@5 ceiling | Recall@20 (95% CI) | MRR (95% CI) |
|---|---|---|---|---|---|
| real | 32 | 0.188 (0.138-0.244) | 0.419 | 0.849 (0.734-0.943) | 0.521 (0.391-0.651) |
| synthetic | 8 | 0.125 (0.050-0.200) | 0.250 | 0.875 (0.625-1.000) | 0.641 (0.289-1.000) |
| real / identifier | 13 | 0.231 (0.138-0.338) | 0.477 | 0.846 (0.667-1.000) | 0.562 (0.361-0.762) |
| real / concept | 13 | 0.138 (0.092-0.185) | 0.338 | 0.821 (0.641-0.974) | 0.460 (0.260-0.662) |
| real / multi_hop | 6 | 0.200 (0.100-0.300) | 0.467 | 0.917 (0.750-1.000) | 0.565 (0.315-0.833) |

Latency p50 72.1 ms, p95 299.3 ms.

Leaks: 0. Items with Recall@20 of 0: ['dev-005', 'dev-025', 'dev-036']
