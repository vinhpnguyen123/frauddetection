# Retrieval eval: rerank_top20_strip_urls

- Set: `dev` (50 items), date 2026-11-07
- Git SHA: `08e2a64`
- Corpus: 43 documents, 1326 chunks, nomic-ai/nomic-embed-text-v1.5
- Labels: drafted by Claude (an AI model), reviewed item by item by Vinh
- Metrics use answerable items; the headline rows use `real` items only.
- P@5 ceiling: the best P@5 the labels allow, since few chunks may be relevant.
- Config `625f8bd4ae24`: `{"method": "rerank", "dense_mode": "exact", "query_expansion": false, "k_bm25": 50, "k_dense": 50, "rrf_k": 60, "rerank_model": "cross-encoder/ms-marco-MiniLM-L-6-v2", "rerank_top_n": 20, "parent_expansion": false}`

| Group | n | P@5 (95% CI) | P@5 ceiling | Recall@20 (95% CI) | MRR (95% CI) |
|---|---|---|---|---|---|
| real | 32 | 0.225 (0.156-0.312) | 0.419 | 0.842 (0.733-0.938) | 0.487 (0.374-0.614) |
| synthetic | 8 | 0.175 (0.100-0.275) | 0.250 | 0.875 (0.625-1.000) | 0.609 (0.312-0.906) |
| real / identifier | 13 | 0.308 (0.154-0.492) | 0.477 | 0.772 (0.593-0.923) | 0.573 (0.355-0.776) |
| real / concept | 13 | 0.138 (0.092-0.185) | 0.338 | 0.840 (0.673-0.981) | 0.373 (0.230-0.555) |
| real / multi_hop | 6 | 0.233 (0.200-0.300) | 0.467 | 1.000 (1.000-1.000) | 0.547 (0.289-0.806) |

Latency p50 912.9 ms, p95 1467.8 ms.

Leaks: 0. Items with Recall@20 of 0: ['dev-005', 'dev-025', 'dev-036']
