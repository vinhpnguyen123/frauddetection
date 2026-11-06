"""Synthetic policies exist to catch cross-tenant leaks, so their properties are checked."""

import re
from pathlib import Path

import pymupdf
import pytest
from scripts.render_synthetic import SOURCE_DIR, render_pdf
from scripts.seed import TENANTS

POLICIES = {
    "bluefin": {
        "cdd-edd-procedure",
        "sar-escalation-workflow",
        "pep-approval-matrix",
        "cash-intensive-business-review",
        "wire-review-thresholds",
    },
    "granite": {
        "member-onboarding-kyc",
        "elder-exploitation-response",
        "check-fraud-handling",
        "ctr-exemption-review",
    },
    "lumen": {
        "crypto-on-off-ramp-monitoring",
        "sanctions-screening-procedure",
        "agent-oversight",
        "chargeback-fraud-playbook",
    },
}
CANARY_PREFIX = {"bluefin": "BCB", "granite": "GRC", "lumen": "LMP"}
CANARY = re.compile(r"[A-Z]+-CANARY-[A-Z0-9]+")
FACTS = ("EDD approver", "SAR escalation window", "Internal review threshold")

FILES = sorted(SOURCE_DIR.glob("*/*.md"))


def tenant_of(path: Path) -> str:
    return path.parent.name


def test_every_policy_exists() -> None:
    found: dict[str, set[str]] = {}
    for path in FILES:
        found.setdefault(tenant_of(path), set()).add(path.stem)
    assert found == POLICIES


@pytest.mark.parametrize("path", FILES, ids=lambda path: path.stem)
def test_policy_has_one_canary_of_its_tenant(path: Path) -> None:
    (canary,) = CANARY.findall(path.read_text(encoding="utf-8"))
    assert re.fullmatch(rf"{CANARY_PREFIX[tenant_of(path)]}-CANARY-[A-Z0-9]{{4}}", canary)


def test_canaries_are_unique() -> None:
    canaries = [CANARY.search(path.read_text(encoding="utf-8")) for path in FILES]
    values = [match.group() for match in canaries if match]
    assert len(values) == len(set(values)) == len(FILES)


@pytest.mark.parametrize("path", FILES, ids=lambda path: path.stem)
def test_policy_is_marked_fictional_and_names_no_other_tenant(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "Fictional document for software testing." in text
    for slug, name in TENANTS.items():
        if slug != tenant_of(path):
            assert slug not in text.lower()
            assert name not in text


@pytest.mark.parametrize("fact", FACTS)
def test_tenants_disagree_on_each_shared_fact(fact: str) -> None:
    values: dict[str, set[str]] = {tenant: set() for tenant in POLICIES}
    for path in FILES:
        found = re.findall(rf"^\*\*{fact}:\*\* (.+)$", path.read_text(encoding="utf-8"), re.M)
        values[tenant_of(path)].update(found)
    assert all(len(found) == 1 for found in values.values()), values
    assert len(set().union(*values.values())) == len(POLICIES)


@pytest.mark.parametrize("path", FILES, ids=lambda path: path.stem)
def test_rendered_pdf_keeps_the_canary_and_is_byte_stable(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    pdf = render_pdf(text)
    assert pdf == render_pdf(text)
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        rendered = "\n".join(page.get_text() for page in document)
    assert CANARY.findall(rendered) == CANARY.findall(text)
