# Retrieval eval: hybrid_raw_section_context

- Set: `dev` (50 items), date 2026-11-07
- Git SHA: `08e2a64`
- Corpus: 43 documents, 1326 chunks, nomic-ai/nomic-embed-text-v1.5
- Labels: drafted by Claude (an AI model), reviewed item by item by Vinh
- Metrics use answerable items; the headline rows use `real` items only.
- P@5 ceiling: the best P@5 the labels allow, since few chunks may be relevant.
- Config `3ac4765cb724`: `{"method": "hybrid", "dense_mode": "exact", "query_expansion": false, "k_bm25": 50, "k_dense": 50, "rrf_k": 60, "rerank_model": null, "rerank_top_n": null, "parent_expansion": false}`

| Group | n | P@5 (95% CI) | P@5 ceiling | Recall@20 (95% CI) | MRR (95% CI) |
|---|---|---|---|---|---|
| real | 32 | 0.194 (0.138-0.256) | 0.419 | 0.904 (0.814-0.975) | 0.528 (0.395-0.659) |
| synthetic | 8 | 0.200 (0.125-0.275) | 0.250 | 0.833 (0.583-1.000) | 0.619 (0.338-0.906) |
| real / identifier | 13 | 0.231 (0.138-0.354) | 0.477 | 0.828 (0.650-0.973) | 0.603 (0.389-0.813) |
| real / concept | 13 | 0.123 (0.077-0.169) | 0.338 | 0.936 (0.833-1.000) | 0.422 (0.251-0.610) |
| real / multi_hop | 6 | 0.267 (0.200-0.333) | 0.467 | 1.000 (1.000-1.000) | 0.597 (0.361-0.833) |

Latency p50 165.7 ms, p95 238.4 ms.

Leaks: 0. Items with Recall@20 of 0: ['dev-005', 'dev-035']
