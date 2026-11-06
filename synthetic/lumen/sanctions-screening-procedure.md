# Sanctions Screening Procedure

Fictional document for software testing. Not the policy of any real institution.

Policy ref LMP-CANARY-V3GP

## Purpose

This procedure sets out how Lumen Pay screens customers, counterparties, and wallet addresses against sanctions lists.

## When screening runs

| Event | Lists | Owner |
|---|---|---|
| Onboarding | OFAC SDN list and consolidated lists | Automated |
| Every payout | OFAC SDN list and wallet address lists | Automated |
| Nightly | Full customer base | Automated |
| Potential match | Manual comparison | Sanctions analyst |

## Handling a potential match

An analyst compares name, date of birth, location, and identifiers within four hours during business hours. The payment stays on hold while the review is open. A match that cannot be cleared goes to the Sanctions Lead.

## Blocking and reporting

Confirmed matches are blocked or rejected as the program requires. Blocked property is reported to OFAC within 10 business days, and blocked assets are reported annually by September 30.

## Geographic controls

Lumen Pay refuses sign-ups from comprehensively sanctioned jurisdictions, and logins from those places are blocked by IP address and device checks.
