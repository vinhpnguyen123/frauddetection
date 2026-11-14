# Q3 root-cause follow-up

Post-hoc analysis of the fixed-label A/B/C/D experiment; no additional retrieval or model runs.

## Observed causes and boundaries

1. Adding section paths consumes the reranker's fixed 512-token pair budget. On identical A/C candidate lists, truncated pairs increase from 235/640 to 265/640. In dev-007, the relevant ransomware-advisory chunk was rank 1 under A and rank 4 under C. Tokenizer-visible source slices contain the literal `CYBER FIN-2021-A004` under A and exclude it under C. The prefixed input ends its visible body at the key-term lead-in. This establishes loss of the answer string from model input, and supports truncation as a concrete failure mechanism. It does not independently prove that all of the rank change, or all other regressions, is caused by truncation.

2. Two other reranker MRR regressions, dev-004 and dev-018, lose no previously fully visible labeled anchor quote in the inspected candidates. Their relevant passage was still supplied but ranked lower with section context. The controlled intervention establishes an effect of the input representation on ranking; whether heading semantics or another model interaction explains that effect is not yet identified. Do not attribute all regressions to truncation or assert an untested domain-training explanation.

3. Section-prefixed embeddings have mixed effects on candidate retrieval: 9 queries improve anchor Recall@20 and 7 regress; 16 are unchanged. The net +0.0323 paired delta has CI spanning zero. This is an observed ranking tradeoff, not evidence that the source corpus lacks answers, and it does not establish a unique semantic cause for each candidate change.

4. Raw BM25 order changed after embedding UPDATEs in rejected disposable-copy attempts. The valid run removed this confound by feeding identical frozen lexical top50 lists to both embedding arms and SQL-reauthorizing every use. This explains why unvalidated early attempts cannot be used as evidence of a section-context gain.

Primary next hypothesis: preserve the answer-bearing body using controlled windowed reranking, with identical frozen candidates and a declared aggregation rule. A same-length neutral-prefix control would separate lost-token effects from heading-semantic effects. These are proposed tests, not measured improvements or default changes.

Source: `2026-11-13_dev_q3_section_context_abcd.json`; literal visibility reconstructed from the unchanged reviewed card and saved actual tokenizer character ranges. V3 labels remain AI-reviewed.
