# M4 retrieval quality follow-up: development handoff

This records the Q1–Q6 development checkpoint, not completion of M4 or an accepted
human benchmark. The code is committed as `e0aa7bd`; the experiments predate that
commit and retain their original dirty-tree provenance and exact input hashes.
Committing their reports does not turn them into clean-checkout measurements.

## Evidence

- [Q1 tracing](2026-11-08_m4_q1_trace_report.md): opt-in stage observations,
  actual-token visibility, ranking parity and SQL authorization checks.
- [Q2 source-checked AI-v3 anchors](2026-11-13_dev_q2_ai_v3_anchor_diagnostic.md):
  label sensitivity on unchanged rankings; original labels remain intact.
- [Q3 section context](2026-11-13_dev_q3_section_context_abcd.md) and
  [root cause](2026-11-13_dev_q3_root_cause.md): controlled representation arms,
  truncation example and the limits of that explanation.
- [Q4 window/fusion](2026-11-13_dev_q4_window_fusion.md): neither declared primary
  replacement qualifies; restoring visible evidence does not establish answer quality.
- [Q5 depth/RRF](2026-11-13_dev_q5_rrf_depth.md): increased leaf-union coverage can
  lose its benefit at the fused cutoff; k10 remains an exploratory secondary signal.
- [Q6 synthesis](2026-11-13_dev_q6_final_synthesis.md): seven standard methods plus
  k10, original/AI-primary/all-public sensitivity, category sizes, sufficiency
  unknowns and separate timing scopes. Same-data repetition is not independent
  confirmation.

## Decision

Retain the research baseline `hybrid_raw`: raw query, body embeddings, exact dense,
50 candidates per branch, equal RRF k60, output20 and no reranker. Keep k10 as a
separately named research candidate. No production configuration, locked application
pipeline, original gold, corpus or held-out protocol is changed by this checkpoint.
Reranker precision improvements on AI-v3 labels are reported, alongside uncertain
MRR and materially different original-label conclusions; no blanket failure claim.

AI-v3 refinements are not independently human validated. Vinh's acceptance was of
an earlier AI-assisted summary, not independent card-by-card expert adjudication.
New evidence-set sufficiency stays unknown. Raw passages, queries for review,
source PDFs, detailed review judgments and experiment scratch scripts remain in
ignored local storage. Their absence from git limits standalone reproduction of
these development experiments; the public reports retain hashes and limitations.

## Local verification before the code commit

`make lint` passed: backend Ruff check/format and mypy (30 source files), embedder
Ruff check/format and mypy (2 source files). `make test` passed: backend492 tests,
embedder15 tests; no failures or skips. Backend emitted5 existing PyMuPDF/SWIG
warnings; embedder emitted1 Starlette/httpx deprecation warning. These are local
checks, not a claim that remote CI has passed.

The first attempts could not launch pytest/mypy because virtualenv scripts pointed
to the previous workspace directory. Correcting the ignored local launcher paths
allowed the unchanged locked dependencies and Makefile checks to run successfully.

## Gates before closing M4

Independent validation of AI-v3 changes, judgments for new evidence sets, clean
committed comparable pipeline measurements, formal slice/milestone review and
remote CI remain open. Do not spend the existing once-only test budget again as
part of this handoff. M5 can use the retained configuration after the required M4
workflow gates; M8 owns later system-level optimization and final evaluation.
