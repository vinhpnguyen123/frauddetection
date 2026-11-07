# Chunking experiments

- Set: `dev` (50 items), date 2026-11-07
- Git SHA: `08e2a64`
- Labels: drafted by Claude (an AI model), reviewed item by item by Vinh
- Metrics use `real` answerable items. Each variant ran on its own database copy.
- Recall@20 and MRR are the main metrics: P@5 moves with the chunk size, because
  the number of relevant chunks changes, and 20 small chunks hold less text.

| Variant | Config | Chunks | Avg tokens | Over 512 | Under 20 | Unmatched anchors | P@5 (95% CI) | Recall@20 (95% CI) | MRR (95% CI) | p50/p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| chunk_v1 | hybrid_raw | 1326 | 317.1 | 277 | 55 | 0 | 0.200 (0.144-0.263) | 0.835 (0.721-0.930) | 0.535 (0.394-0.670) | 49.5 / 67.2 |
| chunk_v1 | rerank_top20 | 1326 | 317.1 | 277 | 55 | 0 | 0.219 (0.150-0.306) | 0.835 (0.721-0.930) | 0.483 (0.367-0.609) | 639.5 / 820.4 |
| chunk_300 | hybrid_raw | 1759 | 238.5 | 0 | 58 | 0 | 0.181 (0.119-0.250) | 0.805 (0.672-0.911) | 0.500 (0.355-0.655) | 93.2 / 121.7 |
| chunk_300 | rerank_top20 | 1759 | 238.5 | 0 | 58 | 0 | 0.194 (0.119-0.281) | 0.805 (0.672-0.911) | 0.494 (0.365-0.631) | 603.8 / 735.1 |
| paragraph | hybrid_raw | 6180 | 66.6 | 53 | 2782 | 2 | 0.138 (0.088-0.188) | 0.582 (0.424-0.729) | 0.347 (0.222-0.482) | 192.6 / 235.9 |
| paragraph | rerank_top20 | 6180 | 66.6 | 53 | 2782 | 2 | 0.163 (0.088-0.256) | 0.582 (0.424-0.729) | 0.346 (0.223-0.484) | 802.3 / 1153.1 |
| strip_urls | hybrid_raw | 1326 | 302.3 | 215 | 55 | 0 | 0.194 (0.138-0.256) | 0.842 (0.733-0.938) | 0.549 (0.411-0.686) | 154.5 / 197.6 |
| strip_urls | rerank_top20 | 1326 | 302.3 | 215 | 55 | 0 | 0.225 (0.156-0.312) | 0.842 (0.733-0.938) | 0.487 (0.374-0.614) | 912.9 / 1467.8 |
| no_short | hybrid_raw | 1271 | 330.4 | 277 | 0 | 0 | 0.200 (0.144-0.263) | 0.835 (0.721-0.930) | 0.535 (0.394-0.670) | 46.1 / 54.0 |
| no_short | rerank_top20 | 1271 | 330.4 | 277 | 0 | 0 | 0.219 (0.150-0.306) | 0.835 (0.721-0.930) | 0.483 (0.367-0.609) | 625.0 / 771.4 |
| section_context | hybrid_raw | 1326 | 317.1 | 277 | 55 | 0 | 0.194 (0.138-0.256) | 0.904 (0.814-0.975) | 0.528 (0.395-0.659) | 165.7 / 238.4 |
| section_context | rerank_top20 | 1326 | 317.1 | 277 | 55 | 0 | 0.238 (0.169-0.319) | 0.873 (0.760-0.963) | 0.487 (0.373-0.613) | 619.7 / 721.1 |

## Reading the results

Rule fixed before the run: `chunk_v1` stays unless a variant clearly beats it on Recall@20 or
MRR, meaning the CIs do not overlap heavily. No variant does, so `chunk_v1` stays.

- `chunk_v1` is the control on a database copy; every item matches the main rows.
- `no_short`: removing 55 chunks under 20 tokens changed no metric here.
- `strip_urls`: no clear difference.
- `chunk_300`: no chunk is over 512 tokens, yet rerank still does not beat hybrid. Its MRR gap to
  hybrid shrinks (0.494 vs 0.500, against 0.483 vs 0.535 on `chunk_v1`), but concept MRR still
  falls with rerank (0.445 to 0.367), so cut-off text is not the whole story.
- `paragraph`: lowest Recall@20 and MRR, with 2,782 chunks under 20 tokens and 2 anchors lost.
- `section_context`: highest Recall@20, but its CI overlaps `chunk_v1` heavily. `dev-036` goes
  from Recall@20 0 to 0.667 and `dev-025` from 0 to 1.0; `dev-035` drops to 0. This supports the
  idea that short chunks lost their context, on very few items.
- Latency is not comparable across variants: the rebuilt copies ran with different cache and
  index state. Only the control and `no_short` keep the stored index contents.
