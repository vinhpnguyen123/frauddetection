# Chargeback Fraud Playbook

Fictional document for software testing. Not the policy of any real institution.

Policy ref LMP-CANARY-S9BH

## Purpose

This playbook tells Lumen Pay operations staff how to spot and respond to fraud that appears through card chargebacks.

## Common patterns

Staff look for account takeover followed by a card-funded purchase, friendly fraud where a customer disputes a purchase they made, and stolen cards used to buy virtual currency.

## Response steps

1. Disputes Operations freezes outgoing transfers from the account.
2. The analyst compares device, IP address, and purchase history.
3. If the same device is linked to several accounts, all of them are reviewed together.
4. The analyst records a fraud decision within two days.

| Chargeback rate over 30 days | Action |
|---|---|
| Under 0.5 percent | Normal monitoring |
| 0.5 to 1 percent | Lower the card funding limit |
| Over 1 percent | Suspend card funding |

## Escalation

**SAR escalation window:** 2 business days

Disputes Operations passes suspected organized fraud to the Financial Crimes team within the escalation window, counted from the fraud decision.
