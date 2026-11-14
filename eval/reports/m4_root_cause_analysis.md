Read: AGENTS.md; CLAUDE.md; IMPLEMENTATION_PLAN.md (M3/M4 slice tables, workflow, Deferred ledgers and Decision log); docs/SCHEMA.md; docs/DATASET.md; docs/ARCHITECTURE.md; docs/CONVENTIONS.md; docs/EVALUATION.md; eval/labeling_rules.md; dev.jsonl and dev.meta.json; retrieval/ingestion/embedder implementations and relevant tests; M4 default, expansion, rerank and chunking reports.

# M4 retrieval root-cause analysis

Mode: read-only M4 quality audit, not a milestone shipping approval.

Scope: the **32 real, answerable dev queries**, `dev-001`–`dev-032`. The full dev set has 50 items: these 32, 8 synthetic answerable items, and 10 refusal items. Supplemental synthetic examples are explicitly separated. No test-set evaluation, model inference, re-embedding, database writes, implementation edits, configuration edits, or relabeling was performed. Only this Markdown report is added to the repository.

## Executive assessment

**The clearest demonstrated ranking regression is reranking; the largest obstacle to interpreting the low headline P@5 is evaluation design and label coverage.** Hybrid already finds at least one labeled relevant chunk in 30/32 real queries and within the first five in 25/32. Its mean Recall@20 is 0.834635. MiniLM top-20 reranking raises mean P@5 from 0.200000 to 0.218750, but reduces MRR from 0.534770 to 0.482626. This is a repeatable outcome in saved reports, not evidence that its underlying semantic cause has been isolated.

The label-imposed P@5 ceiling is **0.418750**, not 1.0. P@5 therefore cannot be read as answer accuracy. This explains part of the low numerical headline, but does not excuse poor ranking or prove that unjudged results are correct. Data/context issues are credible secondary causes; neither broad PDF corruption nor a missing-corpus explanation for the principal misses is demonstrated.

## 1. Evidence, reproducibility and limits

Primary measurements are the saved `2026-11-07_dev_*_m04s4.json` files. `fts` and `bm25` use query expansion; `dense_exact`, `hybrid_raw`, and MiniLM rerank rows do not. An additional `bm25_raw` control is included to avoid blaming fusion for a preprocessing difference. Main report: [M4-S4 comparison](2026-11-07_dev_comparison_m04s4.md). Chunking evidence: [M4-S3 experiments](2026-11-07_dev_chunking.md).

The local database connection was attempted with `default_transaction_read_only=on`. The sandbox denied the initial connection; both escalation attempts were blocked before execution by an automatic-approval-review transport failure. No alternate database access was used to bypass that block.

Instead, a **local, in-memory reconstruction** used the unchanged parser and `chunk_document`, the existing default `chunk_v1`, local stage-1 PDFs and synthetic PDFs, and the cached pinned nomic tokenizer (`e9b6763023c676ca8431644204f50c2b100d9aab`, no model weights or network). Public PDF hashes were checked against the manifest. It reproduced 43 documents and 1,326 chunks, zero unmatched anchors across all 40 answerable dev items, and every saved per-query P@5 ceiling for the 32 real queries. The exact counts above five below come from this reconstruction, not a new benchmark run. Historical database UUIDs and embeddings could not be checked. The counts and ceilings agree with historical evidence, but corpus totals alone are not a proof of byte-for-byte database identity.

Saved reports contain per-query P@5, anchor Recall@20, reciprocal rank and latency, **not ranked chunk IDs, all candidate ranks, or reranker scores**. First relevant rank is recovered as `1 / reciprocal_rank` when nonzero; a zero means no labeled hit within 20, not no relevant passage in the corpus. Rank inversions below concern the first labeled-relevant result; the evidence cannot identify every individual chunk swap or establish a causal semantic explanation for each one.

The pinned MiniLM tokenizer (`233902d25c440f23af6f7d6e94d2946bac0bee0a`) was also used offline for input-length inspection, without loading a cross-encoder or running inference. All new calculations in this report are derived from saved results or explicitly identified reconstruction/tokenizer inspection. Existing reports are preserved.

Audit generated at 2026-11-08T21:28:16.669488+00:00. Dev dataset SHA-256: `ea823aed602c193d022ed3e84c9f3fed13fac9720f23403152838d53040e049d`.

## 2. Gold relevant chunks and theoretical P@5 maximum

An **anchor** is a labeled `(doc_id, page, quote)`. A **gold chunk** is a distinct chunk matching at least one anchor through the current evaluator. These are not interchangeable: several anchors can share a chunk, and one anchor can match several chunks through overlap or repeated text. Counts use the union of matched chunks, not the number of anchors.

For query q with Gq gold chunks, `P@5_max(q) = min(Gq, 5) / 5`. The 32-query mean ceiling is `sum(min(Gq, 5)) / (32 × 5) = 67 / 160 = 0.41875`. There are 74 query–gold-chunk pairs before capping at five; a chunk reused by another query is counted separately for that query. Thirteen queries have a maximum P@5 of 0.2 even with perfect ranking. This is a property of the current labels, not a calibrated estimate of true passage relevance.

| Gold chunks per query | Number of queries | Per-query maximum P@5 |
|---|---|---|
| 1 | 13 | 0.2 |
| 2 | 9 | 0.4 |
| 3 | 6 | 0.6 |
| 4 | 2 | 0.8 |
| 8 | 1 | 1.0 |
| 9 | 1 | 1.0 |

| ID | Query | Anchors | Gold chunks | Maximum P@5 |
|---|---|---|---|---|
| dev-001 | What does 31 CFR 1020.320 require banks to report? | 3 | 3 | 0.6 |
| dev-002 | How many days does a bank have to file a SAR after initial detection? | 1 | 1 | 0.2 |
| dev-003 | What is the dollar threshold for filing a CTR? | 8 | 8 | 1.0 |
| dev-004 | What does 31 CFR 1010.230 require for legal entity customers? | 3 | 2 | 0.4 |
| dev-005 | What SAR key term does FIN-2022-A002 ask filers to use? | 1 | 2 | 0.4 |
| dev-006 | What SAR key term does FIN-2023-Alert003 tell filers to include? | 1 | 1 | 0.2 |
| dev-007 | What key term should a SAR use for ransomware under FIN-2021-A004? | 1 | 1 | 0.2 |
| dev-008 | What is OFAC's 50 Percent Rule? | 2 | 2 | 0.4 |
| dev-009 | What does Section 314(b) of the USA PATRIOT Act allow? | 9 | 9 | 1.0 |
| dev-010 | What does 31 CFR 1010.610 require for correspondent accounts? | 2 | 2 | 0.4 |
| dev-011 | What does FATF Recommendation 12 require for PEPs? | 6 | 2 | 0.4 |
| dev-012 | How does FATF Recommendation 16 apply to VASPs? | 3 | 4 | 0.8 |
| dev-013 | What are the BSA pillars of an AML compliance program? | 1 | 1 | 0.2 |
| dev-014 | How can bank staff tell that a caregiver is stealing from an older customer? | 2 | 1 | 0.2 |
| dev-015 | What signs show a stolen check was altered before being deposited? | 1 | 1 | 0.2 |
| dev-016 | What financial activity may point to someone being trafficked? | 2 | 1 | 0.2 |
| dev-017 | How do scammers persuade victims to put money into fake crypto investments? | 2 | 2 | 0.4 |
| dev-018 | How can a bank notice that a customer's identity photo was generated by AI? | 4 | 1 | 0.2 |
| dev-019 | How should a bank decide how much monitoring a customer needs? | 3 | 4 | 0.8 |
| dev-020 | What must a bank do if it cannot find out who really owns a company opening an account? | 2 | 1 | 0.2 |
| dev-021 | How do ships hide where their cargo really came from? | 3 | 2 | 0.4 |
| dev-022 | What controls help a crypto company avoid dealing with blocked persons? | 3 | 3 | 0.6 |
| dev-023 | How do sanctioned people pretend to give up ownership of their assets? | 4 | 3 | 0.6 |
| dev-024 | Who may test a bank's anti-money-laundering program and how independent must they be? | 1 | 1 | 0.2 |
| dev-025 | How do professional launderers sell their services to criminals? | 2 | 1 | 0.2 |
| dev-026 | Why are foreign buyers of commercial property a laundering concern? | 3 | 1 | 0.2 |
| dev-027 | For a suspected ransomware payment, what key term goes in the SAR and how long does the bank have to file it? | 2 | 2 | 0.4 |
| dev-028 | How does the deadline for reporting blocked property to OFAC differ from the SAR filing deadline? | 3 | 3 | 0.6 |
| dev-029 | What red flags does FinCEN list for elder exploitation, and which perpetrators did BSA filings show most often? | 2 | 2 | 0.4 |
| dev-030 | How did mail-theft check fraud filings change, and what red flags should banks watch for? | 3 | 3 | 0.6 |
| dev-031 | Beyond identifying beneficial owners, what ongoing duties does customer due diligence impose? | 2 | 3 | 0.6 |
| dev-032 | What risk did FinCEN see in the St. Kitts and Nevis citizenship program, and how can institutions mitigate it? | 2 | 1 | 0.2 |

Examples: `dev-011` has six anchors but only two gold chunks; `dev-018` has four anchors in one chunk. Conversely, `dev-005` has one anchor matching two overlapping chunks, and `dev-012` has three anchors matching four chunks. Recall is averaged over anchors, P@5 over chunks, and MRR over the first matching chunk; their denominators and sensitivity to chunking differ.

## 3. Per-query method comparison

Each cell is **first relevant rank / P@5 / anchor Recall@20**. `—` means no labeled-relevant chunk in the first 20. Values are taken from existing per-item results, not a retrieval rerun. `B+` uses expansion; `B0` does not. `H` is `hybrid_raw`; `R20` reranks H's top 20 and returns all 20. All main quality comparisons use the same 32 real items and default corpus.

| ID | FTS+ | B+ | B0 | Dense exact | H | R20 |
|---|---|---|---|---|---|---|
| dev-001 | — / 0.0 / 0.000 | 11 / 0.0 / 0.667 | 11 / 0.0 / 0.667 | — / 0.0 / 0.000 | 13 / 0.0 / 0.667 | 3 / 0.4 / 0.667 |
| dev-002 | 2 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 |
| dev-003 | 3 / 0.6 / 0.875 | 4 / 0.2 / 1.000 | 5 / 0.2 / 0.750 | 1 / 1.0 / 1.000 | 1 / 0.8 / 0.875 | 1 / 1.0 / 0.875 |
| dev-004 | 2 / 0.2 / 1.000 | 2 / 0.4 / 1.000 | 2 / 0.4 / 1.000 | 14 / 0.0 / 0.333 | 7 / 0.0 / 1.000 | 1 / 0.2 / 1.000 |
| dev-005 | — / 0.0 / 0.000 | — / 0.0 / 0.000 | — / 0.0 / 0.000 | — / 0.0 / 0.000 | — / 0.0 / 0.000 | — / 0.0 / 0.000 |
| dev-006 | — / 0.0 / 0.000 | 13 / 0.0 / 1.000 | 6 / 0.0 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 5 / 0.2 / 1.000 |
| dev-007 | 16 / 0.0 / 1.000 | 3 / 0.2 / 1.000 | 2 / 0.2 / 1.000 | 5 / 0.2 / 1.000 | 2 / 0.2 / 1.000 | 1 / 0.2 / 1.000 |
| dev-008 | 11 / 0.0 / 0.500 | 1 / 0.4 / 1.000 | 1 / 0.4 / 1.000 | 17 / 0.0 / 0.500 | 3 / 0.2 / 0.500 | 3 / 0.2 / 0.500 |
| dev-009 | 1 / 0.8 / 1.000 | 1 / 0.8 / 1.000 | 1 / 0.8 / 1.000 | 3 / 0.6 / 0.889 | 2 / 0.6 / 1.000 | 1 / 1.0 / 1.000 |
| dev-010 | 2 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.4 / 1.000 | 1 / 0.4 / 1.000 | 1 / 0.4 / 1.000 |
| dev-011 | 14 / 0.0 / 0.667 | 1 / 0.4 / 1.000 | 8 / 0.0 / 1.000 | 9 / 0.0 / 0.667 | 3 / 0.2 / 0.667 | 13 / 0.0 / 0.667 |
| dev-012 | 13 / 0.0 / 0.333 | 7 / 0.0 / 0.667 | 14 / 0.0 / 0.667 | 1 / 0.2 / 0.333 | 3 / 0.2 / 0.333 | 6 / 0.0 / 0.333 |
| dev-013 | 20 / 0.0 / 1.000 | 2 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 3 / 0.2 / 1.000 |
| dev-014 | 3 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 3 / 0.2 / 1.000 | 2 / 0.2 / 1.000 | 1 / 0.2 / 1.000 |
| dev-015 | 2 / 0.2 / 1.000 | 12 / 0.0 / 1.000 | 12 / 0.0 / 1.000 | 4 / 0.2 / 1.000 | 6 / 0.0 / 1.000 | 5 / 0.2 / 1.000 |
| dev-016 | 2 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 6 / 0.0 / 1.000 |
| dev-017 | 10 / 0.0 / 0.500 | 8 / 0.0 / 0.500 | 8 / 0.0 / 0.500 | 17 / 0.0 / 0.500 | 10 / 0.0 / 0.500 | 7 / 0.0 / 0.500 |
| dev-018 | 16 / 0.0 / 1.000 | 9 / 0.0 / 1.000 | 9 / 0.0 / 1.000 | 9 / 0.0 / 1.000 | 7 / 0.0 / 1.000 | 5 / 0.2 / 1.000 |
| dev-019 | 2 / 0.6 / 1.000 | 3 / 0.2 / 0.667 | 3 / 0.2 / 0.667 | 1 / 0.4 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 |
| dev-020 | — / 0.0 / 0.000 | — / 0.0 / 0.000 | — / 0.0 / 0.000 | 1 / 0.2 / 1.000 | 5 / 0.2 / 1.000 | 2 / 0.2 / 1.000 |
| dev-021 | 7 / 0.0 / 1.000 | 2 / 0.4 / 1.000 | 2 / 0.4 / 1.000 | 1 / 0.2 / 0.667 | 1 / 0.2 / 1.000 | 3 / 0.2 / 1.000 |
| dev-022 | — / 0.0 / 0.000 | 8 / 0.0 / 0.333 | 8 / 0.0 / 0.333 | 12 / 0.0 / 0.333 | 3 / 0.2 / 0.667 | 11 / 0.0 / 0.667 |
| dev-023 | — / 0.0 / 0.000 | 5 / 0.2 / 0.500 | 5 / 0.2 / 0.500 | 1 / 0.2 / 0.500 | 1 / 0.2 / 0.500 | 2 / 0.2 / 0.500 |
| dev-024 | — / 0.0 / 0.000 | 2 / 0.2 / 1.000 | 2 / 0.2 / 1.000 | 9 / 0.0 / 1.000 | 4 / 0.2 / 1.000 | 3 / 0.2 / 1.000 |
| dev-025 | — / 0.0 / 0.000 | — / 0.0 / 0.000 | — / 0.0 / 0.000 | — / 0.0 / 0.000 | — / 0.0 / 0.000 | — / 0.0 / 0.000 |
| dev-026 | 5 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 16 / 0.0 / 1.000 | 5 / 0.2 / 1.000 | 3 / 0.2 / 1.000 |
| dev-027 | 10 / 0.0 / 0.500 | 2 / 0.2 / 1.000 | 1 / 0.4 / 1.000 | 5 / 0.2 / 0.500 | 1 / 0.2 / 1.000 | 4 / 0.2 / 1.000 |
| dev-028 | 14 / 0.0 / 0.333 | 5 / 0.2 / 0.667 | 4 / 0.4 / 1.000 | 2 / 0.4 / 1.000 | 2 / 0.2 / 1.000 | 2 / 0.2 / 1.000 |
| dev-029 | 19 / 0.0 / 0.500 | 7 / 0.0 / 1.000 | 4 / 0.4 / 1.000 | 7 / 0.0 / 0.500 | 4 / 0.2 / 1.000 | 4 / 0.2 / 1.000 |
| dev-030 | 3 / 0.4 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.4 / 1.000 | 1 / 0.4 / 1.000 | 1 / 0.2 / 1.000 |
| dev-031 | 2 / 0.6 / 1.000 | 2 / 0.4 / 1.000 | 2 / 0.4 / 1.000 | 9 / 0.0 / 1.000 | 4 / 0.2 / 1.000 | 5 / 0.2 / 1.000 |
| dev-032 | 4 / 0.2 / 1.000 | 2 / 0.2 / 1.000 | 2 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 | 1 / 0.2 / 1.000 |

The complete query text is in the gold table above. P@5 and recall values shown rounded; exact values remain in the linked JSON files. Sources: [S-fts](2026-11-07_dev_fts_m04s4.json), [S-bm25](2026-11-07_dev_bm25_m04s4.json), [S-bm25_raw](2026-11-07_dev_bm25_raw_m04s4.json), [S-dense_exact](2026-11-07_dev_dense_exact_m04s4.json), [S-hybrid_raw](2026-11-07_dev_hybrid_raw_m04s4.json), [S-rerank_top20](2026-11-07_dev_rerank_top20_m04s4.json).

| Method | Mean P@5 | Mean Recall@20 | MRR | Rank-1 hits /32 | Top-5 hit queries /32 | No hit @20 |
|---|---|---|---|---|---|---|
| fts | 0.143750 | 0.631510 | 0.213474 | 1 | 13 | dev-001,dev-005,dev-006,dev-020,dev-022,dev-023,dev-024,dev-025 |
| bm25 | 0.181250 | 0.812500 | 0.459833 | 9 | 21 | dev-005,dev-020,dev-025 |
| bm25_raw | 0.193750 | 0.815104 | 0.472868 | 10 | 21 | dev-005,dev-020,dev-025 |
| dense_exact | 0.181250 | 0.741319 | 0.491840 | 13 | 19 | dev-001,dev-005,dev-025 |
| hybrid_raw | 0.200000 | 0.834635 | 0.534770 | 12 | 25 | dev-005,dev-025 |
| rerank_top20 | 0.218750 | 0.834635 | 0.482626 | 10 | 25 | dev-005,dev-025 |
| rerank_top50 | 0.225000 | 0.828125 | 0.478813 | 10 | 25 | dev-011,dev-025 |

### What each method succeeds at and misses

- **FTS:** complete misses on `001, 005, 006, 020, 022, 023, 024, 025`; useful counterexamples include `009` at rank 1 and `015` at rank 2. Its broad OR matching and `ts_rank_cd` are a deliberately limited baseline, not BM25. Low results are not evidence of a broken BM25 index.
- **BM25:** strong on explicit identifiers and named terms: `004` rank 2, `008` rank 1, `011` rank 1, `026` rank 1. `020` is missed despite a dense rank-1 hit, consistent with a lexical/paraphrase mismatch hypothesis. Expansion does not help consistently: raw BM25 mean P@5 is 0.193750 versus 0.181250 with expansion; no broad superiority is established by these small differences.
- **Dense exact:** helps paraphrases (`020` rank 1) and some conceptual queries (`006`, `013`, `016`, `019`, `021`, `023` rank 1), but misses identifier query `001` and ranks `004` at 14 versus BM25 at 2. Embedding semantic mismatch is a plausible explanation, not a proved implementation defect. The saved forced-HNSW recall@50 against exact is 1.0000; ANN approximation is not the main demonstrated loss in this run.
- **Hybrid:** combines lexical and semantic successes (`020` found at 5; `029` reaches full anchor recall versus dense's 0.5), but compromises rank (`004`: BM25 2 → hybrid 7; `015`: dense 4 → hybrid 6). Label recall drops relative to an available branch in `003`, `008`, `011`, `012` (shown below). Only `005` and `025` have no labeled hit in the real-query top 20.
- **Rerank top-20:** rescues early relevance for `001` (13 → 3), `004` (7 → 1), `015` (6 → 5), `018` (7 → 5). It also demotes strong hybrid hits; `006`, `016` and `027` are concrete regressions. The same no-hit cases remain because this stage cannot add candidates.

## 4. Why P@5 rises while MRR falls

This is **not an arithmetic contradiction**. P@5 rewards the count of relevant chunks anywhere in the first five; MRR rewards how early the first one appears. Moving a sole gold chunk from rank 1 to rank 5 preserves P@5 = 0.2 but reduces reciprocal rank from 1 to 0.2. Collecting another repeated relevant paragraph in positions 2–5 can increase P@5 without improving the first hit.

Across the 32 real queries, R20 improves first-relevant rank for **11**, worsens it for **10**, and leaves it unchanged for **11**. P@5 improves on **6**, worsens on **5**, and stays unchanged on **21**. Net relevant top-five slots rise by only **3**, yielding `3 / 160 = 0.01875` extra mean P@5. Reciprocal-rank gains sum to **3.263553**, losses to **−4.932168**; dividing their net by 32 gives **−0.052144** MRR. A few large demotions outweigh more numerous small improvements.

These are first-relevant ranking inversions inferred exactly from saved reciprocal ranks. They do not identify whether the same gold chunk was first before and after when multiple gold chunks exist.

| ID | First rank H → R20 | P@5 H → R20 | Δ reciprocal rank | Interpretation |
|---|---|---|---|---|
| dev-001 | 13 → 3 | 0.0 → 0.4 | +0.256410 | Improvement |
| dev-003 | 1 → 1 | 0.8 → 1.0 | +0.000000 | Density-only change |
| dev-004 | 7 → 1 | 0.0 → 0.2 | +0.857143 | Improvement |
| dev-006 | 1 → 5 | 0.2 → 0.2 | -0.800000 | Regression |
| dev-007 | 2 → 1 | 0.2 → 0.2 | +0.500000 | Improvement |
| dev-009 | 2 → 1 | 0.6 → 1.0 | +0.500000 | Improvement |
| dev-011 | 3 → 13 | 0.2 → 0.0 | -0.256410 | Regression |
| dev-012 | 3 → 6 | 0.2 → 0.0 | -0.166667 | Regression |
| dev-013 | 1 → 3 | 0.2 → 0.2 | -0.666667 | Regression |
| dev-014 | 2 → 1 | 0.2 → 0.2 | +0.500000 | Improvement |
| dev-015 | 6 → 5 | 0.0 → 0.2 | +0.033333 | Improvement |
| dev-016 | 1 → 6 | 0.2 → 0.0 | -0.833333 | Regression |
| dev-017 | 10 → 7 | 0.0 → 0.0 | +0.042857 | Improvement |
| dev-018 | 7 → 5 | 0.0 → 0.2 | +0.057143 | Improvement |
| dev-020 | 5 → 2 | 0.2 → 0.2 | +0.300000 | Improvement |
| dev-021 | 1 → 3 | 0.2 → 0.2 | -0.666667 | Regression |
| dev-022 | 3 → 11 | 0.2 → 0.0 | -0.242424 | Regression |
| dev-023 | 1 → 2 | 0.2 → 0.2 | -0.500000 | Regression |
| dev-024 | 4 → 3 | 0.2 → 0.2 | +0.083333 | Improvement |
| dev-026 | 5 → 3 | 0.2 → 0.2 | +0.133333 | Improvement |
| dev-027 | 1 → 4 | 0.2 → 0.2 | -0.750000 | Regression |
| dev-030 | 1 → 1 | 0.4 → 0.2 | +0.000000 | Density-only change |
| dev-031 | 4 → 5 | 0.2 → 0.2 | -0.050000 | Regression |

The P@5 increases are concentrated in `001`, `003`, `004`, `009`, `015`, `018`. The falls are `011`, `012`, `016`, `022`, `030`. `006` goes 1 → 5 with **no P@5 penalty**, while `003` and `009`, which have many repeated/boilerplate gold chunks, gain top-five density. Thus label multiplicity partly shapes the apparent trade-off, although it does not invalidate the observed MRR regressions.

R20 anchor Recall@20 is identical to H **for every item**, as expected from a permutation of the same readable top 20. R50 can change membership: it finds `005` at rank 16 although H/R20 miss it, but loses `011` entirely from its final 20. The former proves at least one labeled hit was available in the fused top-50 candidate pool; it does not establish which retriever originally supplied it. The latter proves a reranker cutoff/ranking regression on already available evidence, absent an unrecorded corpus change.

### Truncation is real, but does not explain all regressions

The reports flag 277 chunks above 512 **embedding-tokenizer** tokens. This is a corpus risk count, not a per-query truncation attribution. Offline inspection using the cached MiniLM tokenizer finds the document-only over-512 count also happens to be 277, but token counts and visibility still depend on the query and tokenizer.

For the 74 reconstructed real-query gold-chunk pairs, **31 exceed 512 tokens when query, document and special tokens are included**. This is a potential truncation count across all gold pairs, not the number actually sent to reranking: candidate IDs were not logged, and a long pair can still retain its answer early. No model inference was performed during this audit.

Several regressions cannot be explained by long input alone:

| ID | Gold query–chunk pair token lengths | First rank H → R20 |
|---|---|---|
| dev-006 | 87 | 1 → 5 |
| dev-011 | 229, 129 | 3 → 13 |
| dev-013 | 328 | 1 → 3 |
| dev-025 | 92 | — → — |
| dev-027 | 535, 579 | 1 → 4 |

`006` has exactly one labeled gold chunk and a pair length of 87; it falls from 1 to 5 even though its full input fits. `011` has two gold pairs of 229 and 129 tokens and falls 3 → 13. These provide direct counterexamples to “all reranker failures are caused by truncation.” Domain/identifier sensitivity, missing section metadata and the rerank scoring objective remain hypotheses. The existing 300-token experiment narrows but does not remove the MRR gap (hybrid 0.500 versus rerank 0.494), also arguing against truncation as the sole cause.

## 5. Relevance-label and matching audit

### Confirmed design limitations and concrete adjudication candidates

1. **Anchor count is not gold-chunk count.** For `011`, six anchors collapse to two chunks; for `018`, four collapse to one. Hitting a single chunk can satisfy several anchors. The current evaluator measures anchor recall, not independent facts or the completeness of an answer. Some multi-hop query MRRs remain high while only one part is supplied.
2. **Page is a reference, not an enforced matching key.** `anchor_chunks` checks current `doc_key` and text but does not constrain page. Reconstruction finds `012`'s page-59 anchor also matching a full repeated passage in ordinal 177 on page 110; `019` and `031` page-1 anchors also match ordinal 9 on pages 8–9. These may be genuinely relevant repeats; they are **not automatically false positives**. The ambiguity is whether gold is passage-instance-level or document-wide semantic evidence. Existing documented matching permits them. Blindly adding a page filter would redefine the benchmark and can create false negatives.
3. **`005`: plausible missing evidence requires scope adjudication.** Only the page-1 advisory quote is labeled; it maps to two overlapping chunks (ordinals 2 and 3). Another public FinCEN document, `fincen-fta-elder-exploitation`, ordinal 1, pages 2–3, explicitly describes BSA reports using the advisory's key term. A Granite-private synthetic policy also repeats it. Those are plausible unjudged evidence, but the query specifically asks what the advisory requests, so they are not automatically equivalent to the primary-source label. The advisory's ordinal 25 also contains the term, but its instruction concerns **Form 8300**, not a SAR: that occurrence must not be marked relevant merely because the identifier matches. Saved reports have no ranked IDs, so this audit cannot claim an unjudged passage caused the actual miss.
4. **`024`: acknowledged query/label ambiguity.** The query asks both who may test and how independent they must be. Its sole anchor states personnel or outside party; the dataset notes explicitly acknowledge that the source section does not fully resolve independence. This is a partially scoped label, not evidence of a retrieval failure for the missing part.
5. **`013`: partial anchor versus full answer.** The anchor quotes internal controls and independent testing, while its matched chunk also discusses officer designation, training, CIP and CDD. A short anchor can correctly identify a useful larger chunk; it does not prove that all relevant passages across the corpus were judged. Do not label this wrong solely because the quote is short.
6. **`012` and `022`: label exhaustiveness is explicitly limited.** Dataset notes narrow travel-rule passages to those stating obligations and sanctions controls to general passages rather than all case studies. This may be an appropriate scope decision, but the model can retrieve unjudged substantively useful evidence. A relevance pool is required to measure any actual undercount.
7. **`032`: historical scope needs an explicit interpretation.** The question uses past tense about the citizenship program and the notes say the rescinded document is named; the query does not literally name its document ID. Historical intent is plausible, but a status-sensitive reviewer should document that interpretation. Retrieval validity alone cannot show current legal applicability. No status label was changed.
8. **No demonstrated corpus absence for the main two misses.** `005` has two matching default chunks; `025` has one 77-embedding-token marketing paragraph on PDF page 13 matching both labeled anchors. It is present and parseable. The absence of hits does not establish missing data or truncation. For `025`, adding section context in the existing experiment produces a hit, suggesting an indexing/representation issue rather than absent source material.

### Different chunking configurations change the measurement surface

All original anchors remain fixed, but the number of chunks they match and the fixed top-20 token budget change. Consequently, raw P@5 is not comparable as if its gold density were constant:

| Existing variant | Label-imposed P@5 ceiling | Unmatched anchors (whole dev set) | P@5 real | Recall@20 real | MRR real |
|---|---|---|---|---|---|
| chunk_v1 | 0.41875 | 0 | 0.200 | 0.835 | 0.535 |
| chunk_300 | 0.44375 | 0 | 0.181 | 0.805 | 0.500 |
| paragraph | 0.51875 | 2 | 0.138 | 0.582 | 0.347 |
| strip_urls | 0.41875 | 0 | 0.194 | 0.842 | 0.549 |
| no_short | 0.41875 | 0 | 0.200 | 0.835 | 0.535 |
| section_context | 0.41875 | 0 | 0.194 | 0.904 | 0.528 |

The paragraph variant has two unmatched anchors, counted as misses only under the experiment's `--allow-unmatched` behavior, not deleted from denominators. Reports record their count but not which anchors; no identities are invented here. The 60%-of-quote boundary rule can fail when a quote is split too evenly or when footnote/order material sits at the apparent edge. Changing chunk size therefore changes both evidence packaging and label matchability. A comparison on independently adjudicated passage relevance or a fixed evidence-token budget would answer a different, useful question; it must remain a separate versioned experiment.

### Parser and tokenizer claims: what is and is not established

- The parser/chunker already joins some cross-page continuations, keeps spans, and has tests for cross-page sentences and footnotes. It does not simply cut every page into a separate chunk. `continues_sentence` relies on punctuation and lowercase continuation, so uppercase/numbered continuations, tables, heading misclassification and footnote ownership remain concrete inspection targets, **not confirmed widespread defects**. Zero unmatched default anchors does not certify all PDF content.
- Current BM25 uses `pdb.unicode_words`, not the historically problematic `pdb.simple`. The integration test distinguishes `1020.320` from `1020 and 320`. Query expansion appends text and preserves the identifier. This audit did not run new SQL or establish a live `103.220` failure. Neural subword segmentation must not be confused with lexical-index identifier splitting.
- The default corpus retains URLs and short chunks. Existing `strip_urls` and `no_short` experiments show no clear quality gain; deleting the 55 sub-20-token chunks changes none of the reported main metrics. Neither is an established principal cause. Context loss can still affect short useful chunks; deleting short chunks is a different intervention from enriching them.

## 6. Failure taxonomy and strength of attribution

“Confirmed outcome” means the saved results or inspected representation establish the stage symptom; it is not necessarily a software defect. “Hypothesis” identifies a mechanism that needs traces or human judgment. Categories are not mutually exclusive and their counts must not be summed as independent errors.

| Failure class | Status | Evidence | Remaining discriminator |
|---|---|---|---|
| Corpus coverage | Not established as the primary failure | 005 and 025 have matching gold in local source reconstruction; all default anchors match. Broader dataset/source coverage remains limited. | Obtain a genuinely absent source or requested fact before attributing a miss to corpus absence. |
| PDF extraction errors | Unconfirmed for the principal misses | 025 marketing text and its anchors survive extraction; cross-page handling exists. No PDF-to-parser corruption case was isolated in the 32 queries. | Visual/raw-PDF versus parsed text audit on suspected pages; preserve block order, tables and exceptions. |
| Chunking / missing context | Supported hypothesis; existing intervention evidence | 025 improves under section_context; gold body excludes the heading. 036 is a supplemental synthetic example, not one of the 32. Smaller/paragraph chunks generally worsen recall. | Controlled metadata input intervention and actual gold/candidate traces. |
| Keyword tokenization | Historical risk, no current demonstrated defect | Current unicode_words and dotted-identifier integration test; dense misses 001 despite lexical hit. | Pinned-version lexical token inspection for the exact failing identifier; do not infer from model subwords. |
| Embedding semantic mismatch | Hypothesis supported by method contrast | Dense misses 001 and ranks 004 at 14; it solves 020 at rank 1 while BM25 misses. | Same corpus/query/gold, inspect exact distances/ranks and controlled context inputs. |
| Candidate generation failure | Confirmed downstream top-20 candidate shortfall; upstream cause partly unresolved | 005 absent from H20, but R50 returns labeled evidence at 16. For 025, no stored branch top-50 union exists to locate the loss. | Capture ACL-filtered branch@50 union and gold coverage before RRF; this is unavailable in historical reports. |
| RRF ranking failure | Confirmed top-20 retention loss on four real queries | 003,008,011,012 have lower anchor recall than a branch using identical raw preprocessing; candidates from that branch were available to fusion. | Trace exact missing anchors and ranks; distinguish score-design trade-off from implementation defect. |
| Reranker ranking regression | Confirmed outcome | 10 first-hit regressions; 006 1→5 and 016 1→6; short inputs disprove a truncation-only explanation. | Frozen-candidate reranker ablation with token visibility and section metadata. |
| Incomplete / incorrect evaluation labels | Confirmed design limitations; incompleteness itself not exhaustively quantified | P@5 ceiling 0.41875, multiplicity/page ambiguity, acknowledged 024 scope issue and unjudged evidence candidates for 005. | Blind pooled review; no automatic additions or test-based label changes. |

### Query-level attribution ledger

The matrix in section 3 is the outcome record. This ledger classifies the observed difficulties across all 32 real queries without assigning unsupported causes. “Early” means first labeled hit within five; it does not imply a complete or grounded answer.

| ID | Attribution / unresolved cause |
|---|---|
| dev-001 | Dense and FTS miss; lexical finds evidence. Identifier/semantic mismatch hypothesis; RRF delays the first hit; R20 improves it. No current token-splitting proof. |
| dev-002 | All methods early/full recall; no demonstrated failure. |
| dev-003 | RRF anchor-retention loss versus dense/raw BM25; R20 increases top-five density but cannot restore lost anchors. |
| dev-004 | Dense semantic/identifier mismatch hypothesis; RRF first-hit compromise 2→7 versus BM25; R20 rescues early rank. |
| dev-005 | Gold present; H20 candidate cutoff shortfall confirmed by R50 hit. Label-scope/incompleteness hypothesis; actual returned passage identity unknown. |
| dev-006 | Reranker regression 1→5 with an 87-token gold pair; not gold-input truncation. Lexical and FTS weaknesses also observed. |
| dev-007 | FTS late; dense/lexical/hybrid find early evidence; R20 improves first hit. |
| dev-008 | RRF loses anchor coverage available to raw BM25; reranking the same 20 cannot recover it. |
| dev-009 | Many boilerplate gold occurrences shape P@5; R20 increases density and improves first hit. No demonstrated coverage failure. |
| dev-010 | All methods early/full recall; no demonstrated failure. |
| dev-011 | RRF loses anchor coverage; R20 demotes 3→13 and R50 loses all final-20 hits. Both gold inputs fit below 512. |
| dev-012 | RRF loses anchor coverage; R20 demotes 3→6. Repeated cross-page quote matching needs explicit evaluation semantics. |
| dev-013 | R20 demotes 1→3 with a fitting 328-token gold pair. Full answer scope and short anchor must be distinguished. |
| dev-014 | All methods find the labeled evidence; R20 improves first hit. Two anchors share one gold chunk. |
| dev-015 | No top-five hit after RRF despite a dense top-five hit; R20 moves 6→5. Ranking, not missing corpus. |
| dev-016 | R20 demotes 1→6; confirmed rank regression despite unchanged top-20 recall. |
| dev-017 | Partial anchor recall and late first hits across methods; source coverage exists, but candidate-versus-ranking cause unresolved. |
| dev-018 | All anchors in one chunk; R20 moves 7→5. P@5 ceiling 0.2 despite multiple labeled facts. |
| dev-019 | H full anchor recall but low top-five density; repeated quote matches inflate number of gold instances. No primary coverage loss. |
| dev-020 | FTS/BM25 miss; dense rank 1. Lexical/paraphrase mismatch hypothesis; hybrid finds at 5; R20 improves to 2. |
| dev-021 | R20 demotes 1→3; unchanged hybrid full anchor recall. Dense alone lacks some anchor coverage. |
| dev-022 | FTS misses; hybrid improves branch coverage but remains partial. R20 demotes 3→11; label-exhaustiveness ambiguity. |
| dev-023 | FTS misses; lexical/dense/hybrid only partial anchor recall; R20 demotes 1→2. Exact candidate-stage cause unresolved. |
| dev-024 | FTS misses, others find the sole labeled chunk; explicit query/label scope ambiguity about independence. |
| dev-025 | Gold present, short and parseable, but all principal default top-20 outputs miss. Context hypothesis supported by existing section_context rescue; candidate-stage location unknown. |
| dev-026 | Dense late; lexical early; R20 improves 5→3. Three anchors share one gold chunk, ceiling 0.2. |
| dev-027 | Hybrid full recall, R20 demotes 1→4. Both gold pairs exceed 512: truncation is plausible here but not proved causal. |
| dev-028 | Hybrid/dense full recall versus partial lexical; R20 unchanged. No demonstrated fusion/rerank regression. |
| dev-029 | Hybrid full anchor recall and early hit versus partial dense; R20 unchanged. No demonstrated rerank loss. |
| dev-030 | R20 keeps rank 1 but loses a labeled top-five slot; P@5-only rerank regression, coverage remains full. |
| dev-031 | R20 demotes 4→5. Page-independent repeated match and multi-part obligations need evaluation interpretation. |
| dev-032 | Early/full hits outside FTS; historical/rescinded-source question intent needs adjudication, not automatic exclusion. |

### RRF loss evidence with preprocessing controlled

Use **raw** BM25 here, because H has expansion disabled. Each branch supplies 50 candidates; its previously observed top-20 gold is therefore available before fusion, subject to stable corpus/results. A lower final-20 anchor recall is evidence of fusion/top-k retention loss, not an absence in the candidate universe.

| ID | Raw BM25 Recall@20 | Dense exact Recall@20 | Hybrid Recall@20 |
|---|---|---|---|
| dev-003 | 0.750 | 1.000 | 0.875 |
| dev-008 | 1.000 | 0.500 | 0.500 |
| dev-011 | 1.000 | 0.667 | 0.667 |
| dev-012 | 0.667 | 0.333 | 0.333 |

## 7. Pipeline and evaluation consistency checks

| Check | Assessment |
|---|---|
| FTS/BM25 preprocessing | Expanded only in standalone expanded rows; raw controls also saved. H and rerank use original query. Comparing expanded BM25 to H without B0 confounds fusion with preprocessing. |
| Legal identifiers | expand_query appends rather than rewrites; unicode_words configured in migration. Existing dotted-ID test covers 1020.320, not every possible identifier. |
| Embedding input | Default ingestion embeds chunks.text; service applies search_document prefix. Dense query uses original query and search_query prefix. Prefixes are centralized and fake-model tests verify them. Numeric contents of historical stored vectors were not independently verified. |
| Lexical input versus neural input | FTS/BM25 index section_path + text, whereas default embeddings and reranker see body text only. This is a real representation asymmetry, not proof of a violated interface. Existing section_context changes document embeddings only, not chunk text or reranker input. |
| Reranker input | RerankRetriever reads only Chunk.text through access_predicate, then sends unprefixed query/text pairs. It replaces RRF rank with cross-encoder score and does not preserve lexical/RRF rank as a feature. No parent-section text is supplied. |
| Candidate limits | BM25@50 + dense@50, RRF k=60; R20 and R50 request fused 20/50 respectively and return final 20 for retrieval evaluation. A future answer final_k=5 is not applied to these metrics. |
| Access filters | All leaf retrieval statements include central access_predicate in SQL; rerank candidate text is rechecked in SQL. H propagates RetrievalContext to both branches. Real gold here is public; synthetic examples must use own-tenant context. Saved zero-leak results and SQL isolation tests support this, not a universal security proof. |
| Evaluation corpus | load_corpus is an administrative grading read, not a user retrieval endpoint. It loads current chunks globally; anchor_chunks checks doc_key and text, not tenant, page, status, or version explicitly. Current-version filtering is supplied upstream. Future reused doc_keys across tenants require label disambiguation; no collision-caused real-query error is shown here. |
| Relevance matching | NFKC normalization then ASCII alphanumerics; whitespace/punctuation/hyphenation ignored. Partial matches require at least 60% of quote tokens at chunk edges. This tolerates layout differences but is not a semantic relevance judge. |
| Metrics | P@5 uses union of matched chunks; Recall@20 counts anchors hit; MRR uses first relevant chunk. Refusal items are excluded from these quality means; real and synthetic summaries remain separate. Scores do not measure citation support or answer correctness. |
| Run provenance | M4-S4 files intentionally record dirty working tree and exact runtime input/dataset hashes for the user-authorized pre-commit exception. The base SHA alone does not reproduce that run. This audit verifies the current tracked state separately and does not overwrite old reports. |
| Latency | The saved M4-S4 run had high swap usage; observed p50/p95 should not be treated as clean-machine service capacity. This explains timing uncertainty, not the quality-rank inversion itself. |

## 8. Three highest-value controlled experiments

These are **proposals only**. No experiment, relabeling, configuration change or new benchmark was executed as part of this audit. Acceptance thresholds below are proposed decision rules, not predicted gains. Keep the held-out test set untouched until the planned final evaluation.

### Experiment 1 — Blind relevance-pool and scope audit (highest priority for trustworthy measurement)

**Hypothesis:** sparse or ambiguously scoped relevance labels materially distort P@5 and some method comparisons; the effect is not captured by counting anchors alone.

**Treatment and controls:** freeze original dev labels/reports, corpus bytes, chunking, models, query strings, access contexts and the six compared methods. Build a separate review pool from each method's dev top-20 union plus existing anchor-containing chunks and source-section neighbors. Hide model names, ranks and previous labels from reviewers. Two reviewers judge answer-bearing relevance, source restrictions, exceptions and historical status; resolve disagreements. Explicitly adjudicate `005`, `024`, repeated occurrences in `012/019/031`, and historical intent in `032`. Use a new versioned label artifact, never overwrite the original benchmark. Do not demand that numbers improve.

**Measurements:** unjudged-but-relevant count, changed/rejected labels, unresolved scope items, reviewer agreement, per-query gold counts and P@5 ceilings, and method metric deltas with paired query bootstrap CIs under original versus adjudicated labels.

**Acceptance:** all 32 queries have a documented scope and resolved reviewer disagreements; every accepted anchor maps to preserved evidence; all pooled passages receive judgments; original reports remain reproducible. Accept “labels materially affect the comparison” only if a method-order conclusion or the sign of a paired rerank-minus-hybrid quality difference changes with its reported uncertainty. If not, record that label incompleteness was insufficient to explain the ranking gap. This experiment is valuable even if it refutes the hypothesis.

### Experiment 2 — Preserve chunk bodies; test heading context in embedding and reranker inputs

**Hypothesis:** loss of section/document context, rather than smaller chunk size, suppresses useful short passages and harms neural ranking.

**Treatment and controls:** on a disposable experimental copy, retain identical chunk boundaries, body text, PDF versions, labels, tokenizer/model revisions, prefixes, BM25 index/query, ACL and candidate budgets. Compare body-only baseline with (a) section-path-prefixed document embeddings only, (b) section-path-prefixed reranker input only, and (c) both. The existing section_context row motivates (a) but does not test (b). Record actual token truncation when adding a heading. First measure full candidate generation; then rerank an identical frozen candidate list to separate retrieval from reranking effects. Do not change the locked production pipeline without a separate decision.

**Measurements:** branch@50 union gold coverage, H@20 anchor recall, first-hit rank, P@5 and MRR, changes on `025` and the separately reported synthetic `036`, identifier/category regressions, and latency under comparable machine conditions. Calculate metrics with the same reviewed label version across arms; retain original-label results too.

**Acceptance:** adopt a representation change only with a positive paired-bootstrap lower bound above zero on its predeclared primary metric (candidate/anchor recall for embedding-only; MRR for frozen-candidate reranking), no observed cross-tenant leak, and no decrease in overall Recall@20 for a reranker-only treatment. If uncertainty spans zero, report no clear difference; a rescue of one handpicked example is insufficient. No smaller-chunk or URL-removal changes are bundled into this experiment.

### Experiment 3 — Frozen-candidate rerank visibility and score-preservation ablation

**Hypothesis:** some regressions come from truncated evidence while others arise because standalone cross-encoder scores discard useful RRF/identifier ranking signals.

**Treatment and controls:** freeze the same ACL-filtered H top-20 candidate IDs for every dev query, all original chunk/section bytes, the model revision, query, labels and output length. Compare H order (no rerank) against current rerank, against rerank scored using a predetermined overlapping sentence-window aggregation that fits the actual tokenizer budget including query, and against a separately declared rank-preservation/fusion treatment. Fix window sizes, aggregation and fusion parameters before evaluation; do not choose them after seeing the 32 outcomes. Analyze fitting versus over-budget pairs separately. Keep the top-50 candidate-budget question outside this ablation.

**Measurements:** actual query+document token lengths and which gold text remains visible; first-hit regressions/improvements; labeled top-five count; MRR/P@5 paired CIs; unchanged candidate membership and anchor Recall@20; per-category results and warm-up-excluded latency. In particular verify whether `006` and `011` still regress even with fully visible gold.

**Acceptance:** a replacement rerank treatment must have a positive paired-bootstrap lower bound above zero for MRR versus current rerank, not reduce P@5, keep exactly the frozen readable candidates and their anchor Recall@20, and pass isolation checks. To claim reranking should replace H on quality grounds, it must additionally show a clear predeclared benefit versus H with its extra latency disclosed. If only long-pair queries improve while short regressions persist, attribute only that component to truncation; do not declare the whole problem solved. Score fusion is an experiment, not an unapproved production change to locked decisions.

## 9. Findings, acknowledged deferrals and plan gaps

### Findings / material audit observations

1. **[medium; high confidence] Evaluation interpretation:** the current mean P@5 ceiling is 0.41875 and relevance-instance multiplicity varies substantially. Reporting raw P@5 as answer accuracy or comparing chunk sizes without their ceilings would be misleading. The existing reports expose ceilings; this is an interpretation limitation, not a newly proved metric implementation bug.
2. **[medium; high confidence] Rerank quality regression under current labels:** multiple first-relevant ranks worsen on fitting inputs (`006`, `011`, `013`) and mean MRR falls. This is measured model/pipeline behavior, not by itself evidence that code violates the M4 delivery contract.
3. **[medium; high confidence] Observability gap:** ItemResult saves aggregate per-item metrics but omits ranked IDs, branch candidates and reranker scores. Historical candidate-generation versus fusion/reranker attribution is therefore incomplete. Adding read-only trace artifacts is needed before exact causal error accounting.
4. **[medium; medium confidence] Label scope ambiguity:** `024` explicitly asks for more than its anchor/source section establishes; `005` and historical-status cases need reviewer adjudication. The audit does not confirm all proposed extra passages as gold.

### Deferred (acknowledged)

- Parent-section context in the answer path and `final_k` → M5-S2; their absence is not a missing M4 generation feature.
- Revisit section-path embedding, label-error analysis and a documented rerun of all dev configurations after approved label fixes → M8-S1.
- Retrieval/rerank cache and parallel retrieval latency work → M8-S2; neither explains or fixes relevance labels by itself.

### Plan gaps

- **Persist intermediate ranked traces**, likely in M8-S1 error analysis: the plan owns error analysis, but does not explicitly require branch@50 IDs/ranks, fused@20/@50 IDs, per-query model scores and tokenizer-visible evidence. Without this, the requested causal split cannot be made from existing reports alone. Store metadata and identifiers, not raw private chunk text or prompts in committed traces.
- **Explicit label occurrence/scope policy**, likely alongside M8-S1 labeling audit: clarify whether page is merely locational, how repeated passages count, and whether a source-specific question permits secondary or synthetic corroboration. Record the decision rather than silently changing matcher semantics.

## 10. Verdict

**Primary demonstrated engineering bottleneck: reranking, with moderate confidence for top-of-list retrieval quality.** The candidate pool is already useful: H finds labeled evidence within 20 for 30/32 real queries. R20 cannot increase pool coverage; it introduces 10 first-hit regressions and a net MRR loss for only three additional labeled top-five slots. Short-input counterexamples show the issue is broader than tail truncation.

**Primary bottleneck to a trustworthy performance conclusion: evaluation quality and interpretation.** Sparse, uneven labels cap P@5 at 0.41875; scope ambiguities and missing pooled judgments make the absolute values and some method comparisons uncertain. This does not prove that label fixes would eliminate the rerank regression, nor that low P@5 is entirely an artifact.

Data processing/context is a supported secondary hypothesis, particularly `025`; it is not a confirmed corpus-wide PDF failure. Candidate retrieval still has real misses and RRF demonstrably loses some branch evidence, but missing ranked traces prevent assigning all residual loss to a single stage. On the current evidence, expanding the corpus, changing embeddings, or removing the reranker wholesale would be premature. Audit labels and capture stage traces first, then run controlled context and frozen-candidate rerank experiments on dev only.

## Appendix A. Reconstructed gold-chunk locations

Locations are `doc_key#ordinal [PDF pages]`, with zero-based chunk ordinals and one-based PDF pages. They are reconstruction references, not historical database UUIDs. No full chunk text is included. The dataset's existing quotes remain unchanged.

| ID | Gold locations |
|---|---|
| dev-001 | fincen-FIN-2022-A002#19 [pages 11]; fincen-FIN-2023-Alert002#11 [pages 8]; ffiec-manual-sar#17 [pages 12,13] |
| dev-002 | ffiec-manual-sar#17 [pages 12,13] |
| dev-003 | fincen-FIN-2022-A002#23 [pages 13]; fincen-FIN-2023-Alert003#12 [pages 7]; fincen-FIN-2023-Alert002#13 [pages 9]; fincen-FIN-2022-Alert001#14 [pages 7]; fincen-FIN-2023-Alert005#12 [pages 8,9]; fincen-FIN-2023-Alert001#15 [pages 9,10]; ffiec-manual-ctr#2 [pages 1]; ffiec-manual-ctr#4 [pages 2,3] |
| dev-004 | ffiec-manual-beneficial-ownership#0 [pages 1]; ffiec-manual-beneficial-ownership#2 [pages 1,2] |
| dev-005 | fincen-FIN-2022-A002#2 [pages 1]; fincen-FIN-2022-A002#3 [pages 1,2] |
| dev-006 | fincen-FIN-2023-Alert003#2 [pages 1] |
| dev-007 | fincen-FIN-2021-A004#2 [pages 1] |
| dev-008 | ofac-virtual-currency#2 [pages 7,8]; ofac-virtual-currency#3 [pages 8] |
| dev-009 | fincen-FIN-2022-A002#26 [pages 14]; fincen-FIN-2023-Alert003#14 [pages 8]; fincen-FIN-2020-A008#17 [pages 10]; fincen-FIN-2021-A004#18 [pages 10]; fincen-FIN-2023-Alert002#9 [pages 6]; fincen-FIN-2023-Alert002#17 [pages 11]; fincen-FIN-2022-Alert001#16 [pages 9]; fincen-FIN-2023-Alert005#14 [pages 9]; fincen-FIN-2023-Alert001#17 [pages 10] |
| dev-010 | ffiec-manual-correspondent-accounts#1 [pages 1]; ffiec-manual-correspondent-accounts#5 [pages 4] |
| dev-011 | fatf-recommendations#19 [pages 17]; fatf-recommendations#118 [pages 76] |
| dev-012 | fatf-va-vasp-guidance-2021#5 [pages 7,8]; fatf-va-vasp-guidance-2021#89 [pages 59]; fatf-va-vasp-guidance-2021#90 [pages 59]; fatf-va-vasp-guidance-2021#177 [pages 110] |
| dev-013 | ffiec-manual-compliance-program#1 [pages 1,2] |
| dev-014 | fincen-FIN-2022-A002#15 [pages 9,10] |
| dev-015 | fincen-FIN-2023-Alert003#7 [pages 4,5] |
| dev-016 | fincen-FIN-2020-A008#11 [pages 7] |
| dev-017 | fincen-FIN-2023-Alert005#1 [pages 1]; fincen-FIN-2023-Alert005#7 [pages 5,6] |
| dev-018 | fincen-FIN-2024-Alert004#9 [pages 5,6] |
| dev-019 | ffiec-manual-cdd#1 [pages 1,2]; ffiec-manual-cdd#2 [pages 2,3]; ffiec-manual-cdd#7 [pages 6,7]; ffiec-manual-cdd#9 [pages 8,9] |
| dev-020 | ffiec-manual-beneficial-ownership#6 [pages 4] |
| dev-021 | ofac-maritime-shipping#0 [pages 1]; ofac-maritime-shipping#3 [pages 2] |
| dev-022 | ofac-virtual-currency#12 [pages 13,14]; ofac-virtual-currency#16 [pages 17]; ofac-virtual-currency#17 [pages 17] |
| dev-023 | ofac-sham-transactions#0 [pages 1]; ofac-sham-transactions#1 [pages 1]; ofac-sham-transactions#4 [pages 3,4] |
| dev-024 | ffiec-manual-compliance-program#1 [pages 1,2] |
| dev-025 | fatf-professional-money-laundering#12 [pages 13] |
| dev-026 | fincen-FIN-2023-Alert002#3 [pages 2,3] |
| dev-027 | fincen-FIN-2021-A004#2 [pages 1]; ffiec-manual-sar#17 [pages 12,13] |
| dev-028 | ofac-virtual-currency#5 [pages 9,10]; ffiec-manual-sar#17 [pages 12,13]; ffiec-manual-ofac#5 [pages 4] |
| dev-029 | fincen-FIN-2022-A002#15 [pages 9,10]; fincen-fta-elder-exploitation#2 [pages 3] |
| dev-030 | fincen-FIN-2023-Alert003#3 [pages 2]; fincen-FIN-2023-Alert003#7 [pages 4,5]; fincen-fta-check-fraud#0 [pages 2] |
| dev-031 | ffiec-manual-cdd#1 [pages 1,2]; ffiec-manual-cdd#7 [pages 6,7]; ffiec-manual-cdd#9 [pages 8,9] |
| dev-032 | fincen-FIN-2014-A004#1 [pages 1] |

## Appendix B. Source and preservation checks

Primary sources: [dev labels](../datasets/dev.jsonl), [labeling rules](../labeling_rules.md), [anchor matcher](../runner/anchors.py), [metric definitions](../runner/metrics.py), [runner and saved schema](../runner/retrieval.py), [hybrid](../../backend/app/retrieval/hybrid.py), [rerank SQL/text input](../../backend/app/retrieval/rerank.py), [ACL predicate](../../backend/app/retrieval/acl.py), [chunker](../../backend/app/ingestion/chunk.py), [parser](../../backend/app/ingestion/parse.py), [BM25 migration](../../backend/alembic/versions/0002_bm25_index.py), [embedding/reranking service](../../embedder/main.py), [dotted-identifier test](../../backend/tests/integration/test_bm25.py), [chunk experiment definitions](../../scripts/chunk_experiment.py), [run machine conditions](2026-11-07_m04s4_conditions.json).

The label metadata describes the dev set as AI-drafted and reviewed by Vinh; this audit is not a substitute for a new independent human pooled relevance review. No historical test-set metrics were used to select experiments or alter labels.

| Read-only source | SHA-256 at audit |
|---|---|
| eval/datasets/dev.jsonl | ea823aed602c193d022ed3e84c9f3fed13fac9720f23403152838d53040e049d |
| eval/datasets/dev.meta.json | bea8dfb8c873c6fd687b3134e998527ae451adceb07d240145c7dba1428fcf6b |
| eval/runner/anchors.py | e2f229803e661862cb8b508e5d810394b1b4b179ba46d263db9e5f328e594e75 |
| eval/runner/metrics.py | 876e2585732cc7ba85a28839138b49efb252180f5165dee10285b00a1b791952 |
| eval/runner/retrieval.py | 347b29e34fc78d20982792ade923d3687f4277c771855f50a6a17ba5c1f1ede9 |
| backend/app/ingestion/chunk.py | 718cafbc7d29730a3fc176e88b225fb2073255b28f71995d9ec3fd3e4b61a3fd |
| backend/app/ingestion/parse.py | db31a889b554a44e3165c020a3a861f5824cd75cb165a0e6970d651e10b1c91b |
| embedder/main.py | 156e8ab1ee8a127c3db7c7548fb21f0c99faf875d198e6c340a6c3741fd5b8d0 |
| eval/reports/2026-11-07_dev_fts_m04s4.json | c1eeee70d587cac50e27e6a2380abbb9b3b222e208683a66cdb2cc8d7442a7f6 |
| eval/reports/2026-11-07_dev_bm25_m04s4.json | 06c8929f37d4df3d1f7a032ac259a5fa4963476ea7445b68c7be6e93bd1b75e3 |
| eval/reports/2026-11-07_dev_bm25_raw_m04s4.json | e125aa24ab2b160d63abe4922196fb075e7f2798358578c55f0ac398566dd98d |
| eval/reports/2026-11-07_dev_dense_exact_m04s4.json | 583e466dda3d069f750b960efd093666847f571a4af1c2b4001e4dfc6274bcf8 |
| eval/reports/2026-11-07_dev_hybrid_raw_m04s4.json | c36db5c772559d69cccb780a8486b76d98190c34cd1977fe6650b1f92b1baabe |
| eval/reports/2026-11-07_dev_rerank_top20_m04s4.json | ecb90ac382f76323f1000bd437fa6dff52a6028bc80d9f2f80ff6a3025201a73 |
| eval/reports/2026-11-07_dev_rerank_top50_m04s4.json | c7035703e01848f01ac02b05a01893190f95b8c2c8bdaa276f663c73e8565e32 |
