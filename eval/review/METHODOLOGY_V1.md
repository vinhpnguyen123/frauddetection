# M4-Q2 relevance review methodology v1

Status: independent human review pending. Original dev labels, corpus, configurations
and M4 reports remain frozen. Vinh agreed to review the blinded artifacts. Q1 review,
commit and CI remain pending; Q2 preparation proceeds by explicit user instruction.

## Pool and blinding

Freeze the Q1 MiniLM top-20 trace. For each of the 32 real answerable dev queries,
union existing gold, BM25 top-20, dense exact top-20, RRF top-20 and reranked top-20.
Add one authorized ordinal neighbor on either side of every initial candidate.
This is a review pool, not an exhaustive census of relevant corpus passages.

Exact normalized passage duplicates within the same document/version share a card;
all chunk occurrences retain page/section provenance. Do not merge across sources,
versions or merely similar wording. Semantic equivalence is a human judgment.
Different chunking configurations require rematching/review; never carry chunk IDs
or partial-match relevance silently between configurations.

`reviewer.jsonl` has query, source, status, authority, passage and occurrence provenance.
It excludes original gold, scores, producing method and ranks. Hash-based order is
deterministic and unrelated to rank. `administrator_key.jsonl` contains those hidden
fields and must not be shown before the independent judgment is frozen. This also
avoids anchoring the reviewer to existing labels. Existing annotation and independent
judgment can be joined by review_id only after review.

The SQL reader requires RetrievalContext and the central access predicate. Passage
content, queries and the administrator key remain under gitignored eval/.cache.
No review files may be written outside that directory by the pool builder. Treat
local reviewer files as sensitive; do not commit or publish them.

## Passage judgments

For each blinded card set judgment to `complete`, `partial`, `neither`, or `uncertain`;
record reviewer identity and a rationale. `complete` supports every required facet
of the question; `partial` supplies substantive evidence for at least one facet.
Topical mention, contents entries or unsupported inference count as neither.
Use evidence_scope to name supported facets. Uncertain requires adjudication.
Neither complete nor partial is automatically accepted as a new gold anchor.

- Exact evidence and semantically equivalent evidence may both qualify when the
  question is general; a matching string alone does not establish relevance.
- A source-specific question requires that named source as primary evidence.
  Secondary corroboration is recorded separately and does not silently substitute.
- Retain duplicate occurrences. Decide passage-instance versus equivalent-evidence
  grouping explicitly; page ambiguity must be resolved against source provenance.
- Historical/rescinded material supports an explicitly historical/source-specific
  question; it must not be treated as current obligations by default.
- Partial-answer evidence may be relevant for retrieval but cannot alone establish
  complete-answer sufficiency. Record which facet is missing.
- For cross-page content inspect both source pages; retain exact spans. Do not draft
  a new anchor quote spanning pages merely to bypass historical matcher behavior.
- Document-level relevance is insufficient: judge the supplied passage itself.
  A neighboring passage supporting the answer does not make this passage relevant.

## Mandatory adjudication cases

| Query | Decision required |
|---|---|
| dev-005 | Named advisory is primary; classify secondary corroboration separately |
| dev-012 | Distinguish repeated occurrences from separate answer-bearing evidence |
| dev-019 | Resolve repeated wording/page ambiguity and monitoring scope |
| dev-024 | Require both eligible tester and independence; current anchor alone does not settle the latter |
| dev-031 | Cover ongoing obligations separately; avoid duplicate evidence inflation |
| dev-032 | Decide whether the wording sufficiently signals the historical/rescinded source; do not assume it explicitly names an advisory identifier |

## Versioning and adjudication gate

Review cards are a draft, not a new gold dataset. Original anchors retain their own
version. A future adjudicated version must include source review/card hashes,
reviewer and adjudicator identities, per-change rationale, accepted anchors with
source/page/quote and their rematched chunk sets, unresolved decisions, and a fresh
dataset hash/provenance. An adjudicated metrics run must reject unresolved records.
No silent original-label edits, no automatic acceptance and no held-out consultation.

The current score_reviewed function takes explicit anchor sets for either version;
it does not load/approve review judgments or promote them to gold. Dataset export
and before/after evaluation occur only after human decisions have been recorded.

## Metrics

Historical P@5 is chunk-based; historical Recall@20 is anchor-based and remains so.
MRR uses the first labeled relevant chunk in the top-20. Added diagnostics:

- Hit@5: at least one labeled relevant chunk in the first five.
- Recall@5: distinct labeled relevant chunks in top-five / all labeled relevant chunks.
- Theoretical P@5 ceiling: min(number of relevant chunks, 5) / 5 per query.
- Ceiling-normalized P@5: per-query P@5 divided by its nonzero ceiling, then averaged.
  Auxiliary only; it is not a replacement for raw P@5 or a ratio of aggregate means.
- Evidence Sufficiency@5: a separate human judgment that the five passages jointly
  support every required answer facet. Passage judgments alone cannot derive it.
  Until judged, report null and coverage; never turn unknown into zero or silently
  average a selectively judged subset as if all queries were covered.

Paired bootstrap uses the same query IDs and resamples per-query differences with
1,000 fixed-seed resamples and percentile 95% intervals. Report original/adjudicated
versions separately and record every method ordering change. Missing adjudication
means no before/after result, not an assumed improvement.

## Reproduction

```sh
cd backend
PYTHONPATH=.:.. uv run --locked python -m eval.runner.relevance_review \
  ../eval/reports/2026-11-08_dev_rerank_top20_q1_trace_validation.trace.jsonl \
  ../eval/.cache/relevance-review-v1
```

Choose a new directory to regenerate; existing output is never overwritten. Builder
validates dev dataset provenance/hash and rerank configuration and fails on missing
or unauthorized candidate IDs. The manifest links the source trace/corpus hash;
its corpus hash describes the source run, not an independently revalidated current
vector snapshot. A future rerun must use the same corpus or regenerate traces.
