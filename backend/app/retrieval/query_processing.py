"""Query expansion: acronym <-> long form, so one spelling also finds the other.

The corpus often uses only one form in a chunk. Meant for the lexical paths (FTS, BM25).
"""

import re

# Each acronym with its long forms; the first is the one added to a query.
ACRONYMS: dict[str, tuple[str, ...]] = {
    "AML": ("anti-money laundering",),
    "BSA": ("bank secrecy act",),
    "CDD": ("customer due diligence",),
    "CFT": ("countering the financing of terrorism", "combating the financing of terrorism"),
    "CIP": ("customer identification program",),
    "CTR": ("currency transaction report",),
    "EDD": ("enhanced due diligence",),
    "FATF": ("financial action task force",),
    "FFIEC": ("federal financial institutions examination council",),
    "FinCEN": ("financial crimes enforcement network",),
    "KYC": ("know your customer",),
    "MSB": ("money services business",),
    "OFAC": ("office of foreign assets control",),
    "PEP": ("politically exposed person",),
    "SAR": ("suspicious activity report",),
    "SDN": ("specially designated national",),
    "TBML": ("trade-based money laundering",),
    "UBO": ("ultimate beneficial owner",),
    "VASP": ("virtual asset service provider",),
}


def _pattern(term: str) -> re.Pattern[str]:
    """Match `term` as whole words, in any case, plural, with a hyphen or a space."""
    words = r"[-\s]+".join(re.escape(word) for word in re.split(r"[-\s]+", term))
    return re.compile(rf"\b{words}(?:s|es)?\b", re.IGNORECASE)


PATTERNS = [
    (acronym, longs, _pattern(acronym), [_pattern(long) for long in longs])
    for acronym, longs in ACRONYMS.items()
]


def expand_query(query: str) -> str:
    """Append the missing form of every acronym or long form found in `query`.

    The original text is never changed, only added to, so legal identifiers such as
    `31 CFR 1020.320` survive verbatim. A query holding both forms gains nothing.
    """
    additions: list[str] = []
    for acronym, longs, acronym_pattern, long_patterns in PATTERNS:
        has_acronym = acronym_pattern.search(query) is not None
        has_long = any(pattern.search(query) for pattern in long_patterns)
        if has_acronym and not has_long:
            additions.append(longs[0])
        elif has_long and not has_acronym:
            additions.append(acronym)
    return " ".join([query, *additions])
