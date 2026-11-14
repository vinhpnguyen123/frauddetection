# Retrieval traces v1

Opt-in **development evaluation only**:

```sh
make eval-retrieval SET=dev CONFIG=rerank_top20 LABEL=<unique-label> EVAL_FLAGS=--trace
```

Use `rerank_top50` to observe a larger reranker input. Tracing requires a label,
refuses existing run artifacts, and rejects the held-out test set. Normal production
retrieval and uninstrumented evaluation do not enable it.

Each report has a companion `*.trace.jsonl`, one `retrieval-trace/v1` record per
query. Validate records with `QueryTrace.model_validate_json`; the exported JSON
Schema is [schema_v1.json](schema_v1.json). The companion report JSON contains the
`retrieval-trace-manifest/v1`: source revision, dirty state, exact evaluation input
hashes, unchanged label hash, corpus/vector hash, index definitions and hash,
Postgres/extension versions, pinned model revisions, and machine conditions.
Pre-commit runs are development validation; final reproducibility runs require a
clean committed checkout. Preserve old artifacts and choose a new label each run.

## Stage interpretation

- `bm25` and `dense`: actual authorized leaf candidates, scores and ranks. Hybrid
  configurations request 50 from each leaf; standalone paths retain their own budget.
- `query_embedding`: actual query embedding time, no vector or query exported.
- `hybrid`: the actual RRF candidates passed downstream (20 or 50).
- `rrf_top20` / `rrf_top50`: diagnostic replay from the **same** captured leaves,
  using the production fusion function. An exact actual-prefix equality check is
  mandatory. No extra retrieval or embedding calls produce these rankings.
- `reranker_inputs`: complete input order, upstream position/score, model score,
  token visibility and matching anchor IDs. `reranker_all` records the complete
  scored order before the existing final result cutoff.
- `final_top20`: actual returned ranking; no trace-only reranking changes it.

`elapsed_ms` with `inclusive` includes nested operations. Do not add these timings:
for example dense includes query embedding and hybrid includes both leaves.
`derived_diagnostic` times replay computation, **not** an observed production fusion
stage. `reranker_metadata.scoring_ms` isolates model scoring;
`token_inspection_ms` measures extra diagnostic preprocessing. Instrumented request
latencies include inspection and are not clean production latency estimates.

## Evidence and visibility

Gold anchors are assigned per-query IDs, such as `dev-003:a1`. The corresponding
chunk IDs are the existing anchor matcher output restricted by the same SQL access
predicate as retrieval. Retention is anchor-based, matching historical Recall@20;
P@5 and MRR retain their existing chunk-based definitions.

Diagnostics distinguish evidence absent from both leaves, lost at each fusion
cutoff, lost from the final result, and demoted by the reranker. They concern
**existing labels**, not a new relevance judgment. `answer_sufficiency` remains null
and `sufficiency_status` remains `unjudged` until independent Q2 review; a retained
anchor does not establish that all parts of a question can be answered.

Tokenizer inspection includes query and special tokens. Offsets are accepted only
when independently reconstructed token IDs exactly match the model's own
preprocessing. Counts, visible character intervals and a token-ID hash are exported;
raw token IDs are not. `full_quote_visible` checks the full normalized quote;
`label_match_visible` applies the historical partial-overlap anchor matcher. Neither
is a human judgment of answer sufficiency.

## Privacy and access

No query text, chunk body, quote, prompt, tenant/user identifier, credential or
embedding vector belongs in a trace. Candidate UUIDs, scores and model metadata are
sensitive diagnostics: these files are development artifacts, not public API output.
Immediately before serialization, **all observed stage IDs** are checked in SQL with
`access_predicate(context)`. A forbidden, stale or revoked observed ID aborts the
trace. Foreign gold IDs are not exported. Candidate text exists only in memory to
calculate visibility and is dropped on successful collection.

Integration tests use the actual ParadeDB fixture and fake ML providers, comparing
normal and instrumented metrics and exact ranking for FTS, BM25, dense, hybrid,
rerank-20 and rerank-50. They also test foreign gold exclusion and fail-closed
handling of an injected unauthorized observed ID. Tests do not call model services.
