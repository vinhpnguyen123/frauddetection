# Crypto On-Ramp and Off-Ramp Monitoring

Fictional document for software testing. Not the policy of any real institution.

Policy ref LMP-CANARY-C8RJ

## Purpose

This standard describes how Lumen Pay monitors customers who convert between US dollars and virtual currency.

## Customer tiers

| Tier | Daily limit | Requirement |
|---|---|---|
| Basic | $1,000 | Verified identity |
| Plus | $10,000 | Verified identity and address |
| Business | Set per customer | Enhanced due diligence |

## Transaction monitoring

**Internal review threshold:** $5,000

Any single conversion at or above the internal review threshold is scored by blockchain analytics before the funds are released. A high-risk score sends the transaction to the Financial Crimes queue.

Alerts are raised for wallets linked to mixers, darknet markets, or sanctioned addresses, for rapid conversion and withdrawal, and for many small purchases from one device.

## Enhanced due diligence

Business tier customers and any customer flagged by analytics twice in 30 days require enhanced due diligence.

**EDD approver:** Head of Compliance

The account stays limited to the Basic tier until the EDD approver signs off.
