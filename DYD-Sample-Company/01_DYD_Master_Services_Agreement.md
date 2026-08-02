# Master Services Agreement — DYD Technologies Pvt. Ltd.

**Document ID:** DYD-LEGAL-MSA-v4.2
**Effective:** 1 April 2025 · **Review cycle:** annual · **Owner:** Legal & Commercial (Priya Iyer)
**Applies to:** all Managed Services, Application Development, Cloud Migration and Data & AI engagements

This is the master framework. Each client engagement attaches a Statement of Work
(SOW) that names the tier, the scope and the commercials. Where an SOW is silent,
this MSA governs. Where an SOW conflicts, the SOW wins for that engagement only.

---

## 1. Service tiers and availability commitments

| Tier | Monthly uptime target | Support window | First response (SEV-1) | Service credit per breach | Credit cap (monthly fee) |
|---|---|---|---|---|---|
| Platinum | 99.95% | 24×7×365 | 15 minutes | 7.5% | 20% |
| Gold | 99.50% | 24×7, business-day change window | 30 minutes | 3.0% | 10% |
| Silver | 99.00% | 08:00–22:00 IST, Mon–Sat | 60 minutes | 2.0% | 10% |

Uptime excludes agreed maintenance windows notified at least 5 business days in
advance, and excludes downtime caused by the client's own systems or by a third
party the client directs DYD to integrate with.

## 2. Severity definitions

| Severity | Definition | Resolution target |
|---|---|---|
| SEV-1 | Complete loss of a production service, or confirmed data loss/breach | 1 hour |
| SEV-2 | Major function degraded; no workaround | 4 hours |
| SEV-3 | Minor function degraded; workaround exists | 8 hours |
| SEV-4 | Cosmetic, query, or scheduled request | 24 hours |

The clock starts when the incident is raised in the DYD service desk, or when DYD
monitoring detects it — whichever is earlier. It stops when service is restored,
not when the root cause is understood.

## 3. Service credits — how they are calculated

Credits are the client's **sole financial remedy** for missed availability or
missed resolution targets. They are not payable automatically: the client must
claim in writing within 30 days of the month end.

The calculation is deliberately simple:

> credit = (number of breached targets in the month) × (credit % for the tier) ×
> (that month's service fee), **capped** at the tier's cap.

Worked example, Silver tier at ₹9,80,000 per month with 10 breaches in the month:
10 × 2.0% = 20% of the fee = ₹1,96,000 — which exceeds the 10% cap, so the payable
credit is **₹98,000**. A tier's cap is reached at 5 breaches (Silver), 4 breaches
(Gold) and 3 breaches (Platinum); breaches beyond that point cost DYD nothing
financially, which is precisely why breach *rate* is tracked as a delivery health
metric and not only as a billing input.

Credits are applied against the following month's invoice. They are never paid in
cash and never carried past the end of the contract term.

## 4. Termination

| Trigger | Notice | Effect |
|---|---|---|
| Convenience (client) | 90 days written | Fees payable to the effective date; no early-exit penalty after month 12 |
| Convenience (DYD) | 180 days written | DYD funds transition assistance up to 200 person-hours |
| Material breach | 30 days to cure | Terminating party may exit if the breach is uncured |
| Chronic SLA failure | Immediate | Three consecutive months at or above the credit cap |
| Insolvency | Immediate | Either party |

**Chronic SLA failure is the clause that matters most in practice.** A client
sitting at the credit cap for three months running may terminate for cause with
no notice and no exit fee, and may recover reasonable migration costs up to one
month's fee. Hitting the cap therefore signals contractual jeopardy well before it
signals meaningful revenue loss.

## 5. Liability

Aggregate liability in any 12-month period is capped at the **fees paid in the
preceding 12 months**, or ₹2,00,00,000, whichever is lower. Excluded from the cap:
breach of confidentiality, infringement of third-party IP, wilful misconduct, and
liability that cannot be limited by Indian law.

Neither party is liable for indirect or consequential loss, loss of profit,
revenue, goodwill or anticipated savings — **except** that data-breach
notification costs and regulatory fines arising from DYD's proven negligence are
treated as direct loss.

## 6. Intellectual property

- Pre-existing IP stays with whoever brought it.
- Deliverables built and paid for under an SOW transfer to the client on **full
  payment of the invoice covering them** — not on delivery. An unpaid invoice
  means DYD still owns the code.
- DYD retains a perpetual licence to reusable components, frameworks, accelerators
  and know-how, provided they carry no client data or client-confidential logic.
- Open-source components are permitted under the approved licence list
  (MIT, Apache-2.0, BSD-2/3, ISC). **AGPL and SSPL are prohibited** in client
  deliverables without written waiver from Legal.

## 7. Data protection

- DYD acts as **data processor**; the client is controller.
- Client data is processed only in the contracted region. Default is `ap-south-1`
  (Mumbai). Cross-border transfer requires written client approval per engagement.
- Sub-processors require 30 days' notice and a right to object.
- Personal data is deleted or returned within 30 days of termination, certified in
  writing.
- Breach notification to the client within **24 hours** of DYD becoming aware —
  tighter than the 72 hours regulators allow, because clients need the head start.

## 8. Payment terms

| Item | Term |
|---|---|
| Standard payment terms | Net 45 days from invoice date |
| Late payment interest | 1.5% per month on overdue balances |
| Suspension right | After 60 days overdue, with 10 business days' notice |
| Annual rate escalation | 5%, or CPI, whichever is lower |
| Currency | INR unless the SOW states otherwise |
| Disputed amounts | Undisputed portion payable on time; dispute raised within 15 days |

## 9. Change control

No change to scope, timeline or price is binding until a Change Request is signed
by both parties' authorised signatories. Work performed on a verbal instruction is
performed at DYD's risk and is not invoiceable. Delivery managers may not approve
Change Requests above ₹5,00,000 — that authority sits with the Delivery Head.
