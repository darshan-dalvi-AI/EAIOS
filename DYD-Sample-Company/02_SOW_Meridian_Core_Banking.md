# Statement of Work — Meridian Bank, Core Banking Migration

**SOW ID:** DYD-SOW-C02-001 · **Project:** P03 · **Tier:** Platinum
**Term:** 15 July 2025 – 31 December 2026 · **Value:** ₹4,20,00,000 fixed price
**Delivery Manager:** Rohan Deshpande · **Client sponsor:** Ms. K. Raghavan, CTO

Governed by DYD-LEGAL-MSA-v4.2. Where this SOW and the MSA conflict, this SOW
prevails for engagement P03 only.

## 1. Scope — in

1. Migration of the core deposits and lending platform from on-premise Oracle
   Exadata to AWS `ap-south-1`, using a strangler-fig pattern across 6 waves.
2. Refactor of 14 batch jobs into event-driven services on Kafka.
3. Data migration of 11 years of account history — approximately 4.2 TB.
4. Dual-run reconciliation for 60 days per wave, with automated break reporting.
5. Regulatory evidence pack for RBI inspection, including data-residency proof.
6. Performance target: **95th-percentile response under 400 ms** at 3,000 TPS.
7. Knowledge transfer: 8 sessions, recorded, plus runbooks for each new service.

## 2. Scope — explicitly out

The following are **not** included and require a signed Change Request:

- Any change to the mainframe general-ledger interface (client retains ownership).
- Mobile or internet banking front-end work of any kind.
- Migration of the treasury or trade-finance modules.
- Third-party licence procurement or renewal.
- UAT execution — DYD supports, the client executes and signs off.
- Production support after go-live, which is covered separately under P05 (AMC).
- Any work arising from RBI regulatory changes published after 1 July 2025.

## 3. Milestones and payment

| # | Milestone | Due | % | Value (₹) | Status |
|---|---|---|---|---|---|
| M1 | Discovery and target architecture signed off | 2025-09-30 | 10 | 42,00,000 | Accepted |
| M2 | Landing zone and CI/CD operational | 2025-11-30 | 15 | 63,00,000 | Accepted |
| M3 | Wave 1 (savings accounts) in production | 2026-02-28 | 20 | 84,00,000 | Accepted |
| M4 | Waves 2–3 (current accounts, term deposits) | 2026-06-30 | 20 | 84,00,000 | Accepted |
| M5 | Waves 4–5 (retail lending, collections) | 2026-09-30 | 20 | 84,00,000 | **At risk** |
| M6 | Wave 6, decommission, evidence pack | 2026-12-31 | 15 | 63,00,000 | Not started |

**Acceptance:** a milestone is accepted when the named client sponsor confirms in
writing within **five working days** of DYD's completion notice. Silence past five
working days is deemed acceptance — a clause DYD relies on, because Meridian's
sign-off cycle has historically run to three weeks.

**Late delivery penalty:** 0.5% of the milestone value per week late, capped at 5%
of that milestone. Penalties do not apply where the delay is caused by client
dependency slippage logged in the weekly status report.

## 4. Known risks (as at July 2026)

| Risk | Impact | Likelihood | Mitigation | Owner |
|---|---|---|---|---|
| M5 dependent on client-side IAM rollout, 6 weeks late | Milestone slip, ₹84L delayed | High | Escalated to CTO 12 Jun; parallel stub built | Rohan Deshpande |
| Data migration break rate at 0.04%, target 0.01% | Regulatory finding | Medium | Reconciliation engine rewrite in sprint 24 | Kabir Menon |
| Only one engineer holds Oracle-to-Kafka CDC knowledge | Delivery stall | Medium | Pairing mandated; runbook due 31 Aug | Sneha Kulkarni |
| Spend at ₹3,86,00,000 of ₹4,20,00,000 with 2 milestones open | Margin erosion to 9% | High | Change Requests raised for out-of-scope IAM work | Rohan Deshpande |

## 5. Commercial position

Fixed price ₹4,20,00,000. Spend to date ₹3,86,00,000 — **92% of budget consumed
with 35% of milestone value outstanding**. Current forecast margin is 9%, against
a 28% target at bid. The recovery plan rests on two Change Requests for
client-caused IAM rework, valued at ₹31,00,000 combined, neither yet signed.
