# Labeling rules

Written before any item was labeled. They apply to `dev.jsonl`, `test.jsonl` and
`adversarial.jsonl`. Item schema and metric definitions: see the eval runner.

## Order of work

1. Write the query first, from the topic of a document, without running any retriever.
2. Find its passages by searching the text for key terms. Never pick a passage because a
   retriever returned it: a label taken from one method's results favours that method.
3. Freeze the set in a commit before the first eval run on it.

## What counts as relevant

A passage is relevant if a compliance analyst would cite it to answer the query: it states
the rule, the threshold, the exception or the red flag asked about.

- A mention without substance is not relevant: a contents line, a heading alone, a passing
  reference to the term.
- Label every relevant passage you can find, not only the first. Recall depends on it.
- If the same rule appears in two documents, label both.
- A passage from a `rescinded` document is relevant only if the query asks about that document.
- For a `multi_hop` query, label one passage for each part of the answer.

## Anchors

- An anchor is `doc_id`, `page` and a verbatim `quote` of about 8 to 20 words.
- Pick a quote that carries the substance, not boilerplate shared with other passages.
- Copy it exactly; whitespace, case, punctuation and line-break hyphens are ignored when
  matching. Avoid a quote that crosses a page break.
- Chunk ids are never used: they change with chunking.

## Categories

| Category | Query shape |
|---|---|
| `identifier` | Names an acronym, CFR citation, form or document number |
| `concept` | Describes an idea in plain words, without the exact term of the source |
| `multi_hop` | Needs two or more passages, usually from different sections or documents |

## Items that must be refused

Set `answerable` to false, leave `relevant` empty and set `expected_refusal`:

- `out_of_scope`: not about AML, KYC, sanctions or financial fraud.
- `insufficient_evidence`: in scope, but the corpus holds no answer. A question about
  another tenant's private policy is also this, so that it looks like a missing answer;
  put that tenant's canary in `must_not_contain`.

## Ambiguity and provenance

- Do not guess. If an item is ambiguous, write why in `notes`.
- Record who drafted the labels and who reviewed them. Every report repeats this.
- Store that declaration in `<set>.meta.json` beside the JSONL, with `dataset_sha256`,
  `drafted_by` and `reviewed_by` (`null` until reviewed). The hash binds it to the exact
  dataset bytes. Commit both files before evaluation. A changed dataset needs a fresh
  review declaration; never carry a review claim onto labels the reviewer has not read.
- An explicitly authorized pre-commit run may use `--allow-uncommitted-labels`.
  The default commit gate remains enabled. Such reports must record the dirty working
  tree, dataset hash, and hashes of runtime sources/lockfiles; do not present their
  base git SHA as a commit containing the measured changes. Inputs must remain unchanged
  throughout the run. This exception does not authorize tuning on test results.
- After a run, a label error is fixed only with a note in the report and a re-run of every
  config. Never remove an item because of its result.
