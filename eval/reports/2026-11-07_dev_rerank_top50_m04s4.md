# Retrieval eval: rerank_top50_m04s4

- Set: `dev` (50 items), date 2026-11-07
- Git SHA: `df013ce`
- Corpus: 43 documents, 1326 chunks, nomic-ai/nomic-embed-text-v1.5
- Labels: drafted by Claude (AI); reviewed item by item by Vinh
- Dataset SHA-256: `ea823aed602c193d022ed3e84c9f3fed13fac9720f23403152838d53040e049d`
- Working tree dirty: True; pre-commit labels allowed: True
- Input fingerprint: `ab0d8d8c8502e597cbf60593164b5cb0ef8c96fd0486667e5e0c8db6c1d83726`
- Metrics use answerable items; the headline rows use `real` items only.
- P@5 ceiling: the best P@5 the labels allow, since few chunks may be relevant.
- Config `5ac5f001a028`: `{"method": "rerank", "dense_mode": "exact", "query_expansion": false, "k_bm25": 50, "k_dense": 50, "rrf_k": 60, "rerank_model": "cross-encoder/ms-marco-MiniLM-L-6-v2", "rerank_top_n": 50, "parent_expansion": false}`

| Group | n | P@5 (95% CI) | P@5 ceiling | Recall@20 (95% CI) | MRR (95% CI) |
|---|---|---|---|---|---|
| real | 32 | 0.225 (0.156-0.312) | 0.419 | 0.828 (0.719-0.927) | 0.479 (0.365-0.607) |
| synthetic | 8 | 0.175 (0.100-0.275) | 0.250 | 0.875 (0.625-1.000) | 0.606 (0.312-0.906) |
| real / identifier | 13 | 0.323 (0.169-0.508) | 0.477 | 0.846 (0.667-1.000) | 0.571 (0.354-0.774) |
| real / concept | 13 | 0.138 (0.092-0.185) | 0.338 | 0.769 (0.577-0.936) | 0.361 (0.220-0.551) |
| real / multi_hop | 6 | 0.200 (0.200-0.200) | 0.467 | 0.917 (0.750-1.000) | 0.533 (0.275-0.792) |

Latency p50 1701.7 ms, p95 3274.0 ms.

Leaks: 0. Items with Recall@20 of 0: ['dev-011', 'dev-025', 'dev-036']
