# Retrieval eval: rerank_top20_bge

- Set: `dev` (50 items), date 2026-11-07
- Git SHA: `139b0e5`
- Corpus: 43 documents, 1326 chunks, nomic-ai/nomic-embed-text-v1.5
- Labels: drafted by Claude (an AI model), reviewed item by item by Vinh
- Metrics use answerable items; the headline rows use `real` items only.
- P@5 ceiling: the best P@5 the labels allow, since few chunks may be relevant.
- Config `94092d06a3e8`: `{"method": "rerank", "dense_mode": "exact", "query_expansion": false, "k_bm25": 50, "k_dense": 50, "rrf_k": 60, "rerank_model": "BAAI/bge-reranker-base", "rerank_top_n": 20}`

| Group | n | P@5 (95% CI) | P@5 ceiling | Recall@20 (95% CI) | MRR (95% CI) |
|---|---|---|---|---|---|
| real | 32 | 0.200 (0.125-0.281) | 0.419 | 0.835 (0.721-0.930) | 0.562 (0.424-0.703) |
| synthetic | 8 | 0.200 (0.125-0.275) | 0.250 | 0.875 (0.625-1.000) | 0.729 (0.458-0.938) |
| real / identifier | 13 | 0.292 (0.154-0.446) | 0.477 | 0.772 (0.593-0.923) | 0.735 (0.509-0.949) |
| real / concept | 13 | 0.092 (0.031-0.169) | 0.338 | 0.821 (0.641-0.974) | 0.344 (0.192-0.521) |
| real / multi_hop | 6 | 0.233 (0.200-0.300) | 0.467 | 1.000 (1.000-1.000) | 0.658 (0.358-0.917) |

Latency p50 4718.9 ms, p95 6568.7 ms.

Leaks: 0. Items with Recall@20 of 0: ['dev-005', 'dev-025', 'dev-036']
