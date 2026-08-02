# Delivery Methodology Playbook — DYD Technologies

**Document ID:** DYD-DEL-MTH-002 · **Version:** 5.0 · **Owner:** Rohan Deshpande (Delivery Head)

## 1. Engagement models

| Model | When we use it | Commercial risk | Governance |
|---|---|---|---|
| Fixed price | Scope genuinely stable and specified | DYD carries it | Milestone acceptance, change control |
| Time & materials | Discovery, evolving scope | Client carries it | Monthly timesheet sign-off |
| Managed service | Run and maintain | Shared, SLA-bound | Monthly service review |
| Staff augmentation | Client leads, DYD supplies capacity | Client carries it | Client's own process |

**Fixed price is the model that hurts.** P03 (Meridian) is fixed price at
₹4.2 crore, is 92% spent with 35% of milestone value outstanding, and has fallen
from a 28% bid margin to 9%. P09 (Vertex Warehouse Integrations) is already
**over budget at −8% margin**. Both were sold as fixed price against scope that
turned out to be negotiable in only one direction.

## 2. Sprint cadence

Two-week sprints, Monday start. Ceremonies are timeboxed and the timebox is real.

| Ceremony | Duration | Attendees |
|---|---|---|
| Planning | 2 hours | Whole squad + PO |
| Daily standup | 15 minutes | Squad |
| Refinement | 1 hour, mid-sprint | Squad + PO |
| Review / demo | 1 hour | Squad + PO + client |
| Retrospective | 45 minutes | Squad only |

Standups report against the board, not around the room. If an update takes more
than 60 seconds it is a conversation for after the standup.

## 3. Definition of Done

A story is done when **all** of the following are true. Partial completion is not
a percentage — it is "not done".

- Acceptance criteria met and demonstrated.
- Unit tests written and passing; coverage on changed lines at or above 80%.
- Integration tests passing in the pipeline.
- Code reviewed and approved by someone other than the author.
- SAST and dependency scans clean of critical and high findings.
- Documentation updated — API docs, runbook, or README, whichever applies.
- Deployed to staging and verified there.
- No new critical or high defects introduced.
- Observability in place: the new path emits metrics and structured logs.

## 4. Release gates

| Gate | Requirement | Who signs |
|---|---|---|
| G1 Code | CI green, review approved, scans clean | Tech Lead |
| G2 Test | Regression pass, UAT sign-off where contracted | QA Lead |
| G3 Change | CAB approval, rollback plan documented and tested | Delivery Manager |
| G4 Release | Deployment window confirmed, on-call briefed | Release Manager |
| G5 Post | Smoke tests pass, monitoring stable 2 hours | On-call |

**Rollback must be tested, not documented.** A rollback plan nobody has executed is
a hypothesis. Since the March 2026 Northwind SEV-1, every release rehearses its
rollback in staging before G3 is signed.

Production releases do not happen after 15:00 IST on a Friday, or on the day
before a public holiday. This rule has been waived twice and both waivers appear
in incident reviews.

## 5. Estimation

Story points, planning poker, Fibonacci. Points are capacity, never a commitment
to a date. Velocity is measured over the last three sprints and is used only for
forecasting — never for comparing squads, and never in an appraisal.

Estimates for fixed-price bids carry a **25% contingency** and a documented list
of assumptions. Every assumption that later proves false becomes a Change Request.
The Meridian IAM dependency is exactly this case: assumption A7 in the bid stated
the client's IAM rollout would complete by December 2025. It has not, and the
resulting rework is the substance of the two unsigned Change Requests.

## 6. Project health (RAG)

| Status | Meaning | Action |
|---|---|---|
| Green | On scope, schedule, budget and quality | Normal reporting |
| Amber | One dimension at risk with a credible recovery plan | Weekly review with Delivery Head |
| Red | Recovery plan absent or failed, or margin below 10% | Executive escalation within 48 hours |

Health is set by the Delivery Manager and challenged weekly. A project may not sit
Amber for more than three consecutive reporting cycles — it goes Green or it goes
Red. Lingering Amber is how P09 reached negative margin without an escalation.
