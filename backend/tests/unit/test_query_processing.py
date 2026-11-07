import pytest

from app.retrieval.query_processing import expand_query


@pytest.mark.parametrize(
    "query",
    [
        "31 CFR 1020.320",
        "What does 31 C.F.R. § 1020.320(a)(2) require?",
        "FIN-2022-A002",
        "Form 8300",
        "Section 314(a)",
        "What is the capital of France?",
        "",
    ],
)
def test_a_query_without_known_terms_stays_exactly_the_same(query: str) -> None:
    assert expand_query(query) == query


def test_an_identifier_survives_expansion_verbatim() -> None:
    query = "Does 31 CFR 1020.320 cover a SAR?"
    assert expand_query(query) == f"{query} suspicious activity report"


@pytest.mark.parametrize(
    ("query", "added"),
    [
        ("What is a SAR?", "suspicious activity report"),
        ("When are SARs due?", "suspicious activity report"),
        ("kyc rules", "know your customer"),
        ("FinCEN advisories", "financial crimes enforcement network"),
        ("AML/CFT programs", "anti-money laundering countering the financing of terrorism"),
    ],
)
def test_an_acronym_gains_its_long_form(query: str, added: str) -> None:
    assert expand_query(query) == f"{query} {added}"


@pytest.mark.parametrize(
    ("query", "added"),
    [
        ("file a suspicious activity report", "SAR"),
        ("Suspicious Activity Reports", "SAR"),
        ("money services businesses", "MSB"),
        ("anti money laundering rules", "AML"),
        ("trade based money laundering", "TBML"),
        ("combating the financing of terrorism", "CFT"),
    ],
)
def test_a_long_form_gains_its_acronym(query: str, added: str) -> None:
    assert expand_query(query) == f"{query} {added}"


@pytest.mark.parametrize("query", ["sarcastic pepper", "ctrl key", "bsa2", "the msbuild tool"])
def test_a_term_inside_another_word_does_not_match(query: str) -> None:
    assert expand_query(query) == query


def test_a_query_holding_both_forms_gains_nothing() -> None:
    query = "SAR means suspicious activity report"
    assert expand_query(query) == query


@pytest.mark.parametrize("query", ["What is a SAR?", "know your customer", "AML/CFT and EDD"])
def test_expanding_twice_changes_nothing_more(query: str) -> None:
    assert expand_query(expand_query(query)) == expand_query(query)
