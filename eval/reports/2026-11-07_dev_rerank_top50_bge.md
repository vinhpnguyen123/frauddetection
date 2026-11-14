# Retrieval eval: rerank_top50_bge

- Set: `dev` (50 items), date 2026-11-07
- Git SHA: `139b0e5`
- Corpus: 43 documents, 1326 chunks, nomic-ai/nomic-embed-text-v1.5
- Labels: drafted by Claude (an AI model), reviewed item by item by Vinh
- Metrics use answerable items; the headline rows use `real` items only.
- P@5 ceiling: the best P@5 the labels allow, since few chunks may be relevant.
- Config `482e709f8c67`: `{"method": "rerank", "dense_mode": "exact", "query_expansion": false, "k_bm25": 50, "k_dense": 50, "rrf_k": 60, "rerank_model": "BAAI/bge-reranker-base", "rerank_top_n": 50}`

| Group | n | P@5 (95% CI) | P@5 ceiling | Recall@20 (95% CI) | MRR (95% CI) |
|---|---|---|---|---|---|
| real | 32 | 0.200 (0.131-0.269) | 0.419 | 0.826 (0.717-0.925) | 0.525 (0.390-0.663) |
| synthetic | 8 | 0.175 (0.100-0.250) | 0.250 | 0.875 (0.625-1.000) | 0.688 (0.396-0.917) |
| real / identifier | 13 | 0.308 (0.200-0.431) | 0.477 | 0.906 (0.786-1.000) | 0.739 (0.543-0.910) |
| real / concept | 13 | 0.077 (0.015-0.138) | 0.338 | 0.769 (0.538-0.962) | 0.249 (0.126-0.405) |
| real / multi_hop | 6 | 0.233 (0.200-0.300) | 0.467 | 0.778 (0.583-0.944) | 0.658 (0.358-0.917) |

Latency p50 12421.4 ms, p95 35897.7 ms.

Leaks: 0. Items with Recall@20 of 0: ['dev-022', 'dev-025', 'dev-036']
