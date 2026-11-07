# Retrieval eval: hybrid_raw_m04s4_sanity

- Set: `test` (30 items), date 2026-11-07
- Git SHA: `df013ce`
- Corpus: 43 documents, 1326 chunks, nomic-ai/nomic-embed-text-v1.5
- Labels: drafted by Codex (AI); not human-reviewed
- Dataset SHA-256: `ae22e5758362446c8f4ab48fd619c288f60785d5120dd141cfa4bb0719aa6480`
- Working tree dirty: True; pre-commit labels allowed: True
- Input fingerprint: `d3a2d1cd182f13631f3554f1aff9cf2188d01eab1fa481a2b5072117f317aeb6`
- Metrics use answerable items; the headline rows use `real` items only.
- P@5 ceiling: the best P@5 the labels allow, since few chunks may be relevant.
- Config `3ac4765cb724`: `{"method": "hybrid", "dense_mode": "exact", "query_expansion": false, "k_bm25": 50, "k_dense": 50, "rrf_k": 60, "rerank_model": null, "rerank_top_n": null, "parent_expansion": false}`

| Group | n | P@5 (95% CI) | P@5 ceiling | Recall@20 (95% CI) | MRR (95% CI) |
|---|---|---|---|---|---|
| real | 20 | 0.200 (0.150-0.250) | 0.250 | 0.925 (0.800-1.000) | 0.762 (0.579-0.917) |
| synthetic | 4 | 0.200 (0.200-0.200) | 0.200 | 1.000 (1.000-1.000) | 1.000 (1.000-1.000) |
| real / identifier | 8 | 0.125 (0.050-0.200) | 0.200 | 0.875 (0.625-1.000) | 0.583 (0.271-0.896) |
| real / concept | 8 | 0.225 (0.200-0.275) | 0.225 | 1.000 (1.000-1.000) | 0.823 (0.573-1.000) |
| real / multi_hop | 4 | 0.300 (0.200-0.400) | 0.400 | 0.875 (0.625-1.000) | 1.000 (1.000-1.000) |

Latency p50 51.1 ms, p95 76.4 ms.

Leaks: 0. Items with Recall@20 of 0: ['test-002']
