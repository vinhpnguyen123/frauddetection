# Q2 v3 source-checked AI anchor diagnostic

32 real answerable dev queries; four frozen methods. This is an **AI label diagnostic**, not an official independently adjudicated benchmark. Vinh accepted the v2 Vietnamese summary; the 32 additional v3 card refinements and two sufficiency corrections are AI changes and are not represented as item-by-item human review.

No retrieval/model rerun, gold edit, default change or held-out consultation. AI refinements followed the earlier v2 aggregate diagnostic; these are not blind independent annotations.

The inventory covers all 375 positive public cards under v3, with 375 page-local quote locators grouped into 372 source-location anchor groups. Seven groups are secondary corroboration and are excluded from the primary/direct-source variant. Quotes were inspected visually at their local source regions; this does not claim a full visual audit of every page of every long card. All locators match supplied card text and current SQL-ACL-authorized chunks with PDF/manifest/version hashes agreeing.

| Method | Original P@5 | AI primary P@5 | Original anchor Recall@20 | AI primary anchor Recall@20 | AI sufficient / 32 |
|---|---:|---:|---:|---:|---:|
| bm25 | 0.194 | 0.500 | 0.815 | 0.646 | 20/32 |
| dense | 0.181 | 0.487 | 0.741 | 0.610 | 18/32 |
| hybrid | 0.200 | 0.506 | 0.835 | 0.662 | 20/32 |
| reranked | 0.219 | 0.575 | 0.835 | 0.662 | 21/32 |

**Read the table as label sensitivity, not system improvement.** The anchor inventories and per-query denominators change between versions; no chunk-based recall is substituted. JSON includes 95% CIs, paired label deltas, MRR, primary-only versus all-public sensitivity, every per-query anchor count and exact input hashes. The primary versus all-public variants expose, rather than conceal, the treatment of corroborating sources.

Original P@5, MRR and anchor Recall@20 reproduce the earlier frozen-trace diagnostic exactly for every query/method. Source-location overlap aliases are explicitly grouped; no cross-source semantic merges are made. Corpus coverage is bounded by the blinded review pool and is not an exhaustive relevance census of the entire corpus.

Key refinements: distinguish SAR key terms from other field keywords/urgent phone notifications; distinguish AML program testing from model validation; preserve FATF version/applicability; require CTR same-person/business-day aggregation conditions; distinguish PML client marketing from service menus/mule recruitment; do not treat a rescission-status notice as an answer. Q32 remains explicitly historical.

The two formerly sufficient dev-003 sets are now insufficient under the clarified aggregation scope. All four methods are rescored consistently. Historical v2 diagnostics and original gold remain intact.

Q2 status: expanded AI anchor inventory and development comparison are ready for review; independent validation, accepted-gold promotion and the existing slice/commit/CI gate are not claimed complete.
