"""Starter document packs — the content that makes a new workspace answerable.

An empty knowledge base is why trials die. The customer picks their field,
opens the chat, asks the suggested question, and gets "I couldn't find that in
your documents" — which reads as "this product does not work" rather than "you
have not uploaded anything yet".

So each industry ships with a small corpus written the way that field actually
writes: the section headings, the obligations, the numbers. Every suggested
prompt in ``industries.py`` has a real answer with a real citation from these
documents within a minute of signing up.

They are clearly labelled as samples (``tags`` contains "sample") and can be
removed in one click — see ``industries.remove_samples``. Nothing here pretends
to be the customer's own data.
"""

Doc = tuple[str, str]   # (title, markdown body)


PACKS: dict[str, list[Doc]] = {
    # ── IT services & consulting ─────────────────────────────────────────
    "it_services": [
        ("Client Statement of Work — Northwind Retail", """# Statement of Work — Northwind Retail Platform Migration

## 1. Scope of work
Migration of the Northwind order-management platform from on-premise servers
to managed cloud hosting, including data migration, cutover and 30 days of
hypercare support.

## 2. Explicit exclusions
The following are **out of scope** unless agreed by written change request:
front-end redesign, mobile application work, third-party licence costs,
staff training beyond two handover sessions, and any integration with systems
not listed in Appendix A.

## 3. Delivery milestones
| Milestone | Date | Payment |
|---|---|---|
| Environment ready | 14 March | 20% |
| Data migration signed off | 11 April | 30% |
| Production cutover | 2 May | 40% |
| Hypercare complete | 1 June | 10% |

## 4. Acceptance criteria
A milestone is accepted when the named client sponsor confirms in writing
within five working days. Absent a response, the milestone is deemed accepted
on the sixth working day.

## 5. Service credits
If production availability falls below 99.5% in any calendar month during
hypercare, a service credit of 5% of the monthly fee applies. Below 99.0%,
the credit is 10%. Credits are capped at 20% of the monthly fee and are the
client's sole remedy for availability failures.

## 6. Change requests
Any change to scope, dates or fees requires a written change request signed by
both parties before work begins. Verbal instructions do not vary this SOW.
"""),
        ("Incident Response Runbook — Database Failover", """# Runbook: Database Failover

**Severity:** SEV-1 when the primary is unreachable for more than 3 minutes.
**Owner:** Platform on-call engineer.

## Prerequisites
- Access to the cloud console with `db-operator` role.
- The replica lag dashboard open.
- The incident channel opened and the client contact notified.

## Steps
1. **Confirm the primary is genuinely down.** Run the health probe against the
   writer endpoint. Confirmed when three consecutive probes fail. A single
   failed probe is usually a network blip — do not fail over on one.
2. **Check replica lag.** If lag exceeds 30 seconds, expect data loss on
   promotion. Record the lag figure in the incident channel before continuing.
3. **Stop the application writers.** Scale the API deployment to zero. This
   prevents split-brain writes during promotion.
4. **Promote the replica.** ⚠️ *This step is irreversible* — the old primary
   cannot be re-attached without a full rebuild. Confirm with the incident
   commander before running it.
5. **Repoint the writer endpoint** to the promoted instance and verify the DNS
   change has propagated before restoring traffic.
6. **Scale the API back up** and confirm write success with a canary
   transaction.
7. **Verify recovery:** error rate below 1% for five consecutive minutes.

## Rollback
There is no rollback after step 4. If promotion fails, restore from the most
recent snapshot — expect up to 15 minutes of data loss.

## Post-incident
Record the lag figure, the promotion time and the customer impact window in the
incident report within 24 hours.
"""),
        ("Managed Services Agreement — Support Terms", """# Managed Services Agreement — Support Terms

## Support hours
Standard support runs 09:00–18:00 local time, Monday to Friday, excluding
public holidays. Extended cover (24×7) is available under the Premium schedule
at an additional monthly fee.

## Response and resolution targets
| Priority | Definition | Response | Target resolution |
|---|---|---|---|
| P1 | Production down, no workaround | 30 minutes | 4 hours |
| P2 | Major function degraded | 2 hours | 1 business day |
| P3 | Minor issue, workaround exists | 1 business day | 5 business days |
| P4 | Question or request | 2 business days | Best effort |

## Service credits
Failure to meet the P1 response target in more than two incidents per quarter
entitles the client to a service credit of 5% of the quarterly fee. Claims must
be submitted within 30 days of the quarter end.

## Client responsibilities
The client must maintain a named technical contact, provide timely access to
systems, and apply recommended security patches within 30 days of notice.
Delays caused by the client do not count towards resolution targets.

## Term and termination
The initial term is 12 months, renewing automatically for successive 12-month
terms unless either party gives 60 days' written notice. Either party may
terminate for material breach not remedied within 30 days of written notice.
"""),
    ],

    # ── Healthcare & clinics ─────────────────────────────────────────────
    "healthcare": [
        ("Patient Intake Protocol", """# Patient Intake Protocol

**Applies to:** all reception and clinical staff. **Review cycle:** annual.

## 1. Identity verification
Confirm the patient's full name, date of birth and address against the record
before any clinical information is discussed or entered. Where the patient
cannot confirm these, escalate to the duty clinician — do not proceed on a
partial match.

## 2. Consent at first contact
At the first appointment, record: consent to treatment, consent to share
information with the patient's GP, and any explicit refusals. Consent is
recorded in the patient record with the date and the staff member who took it.
Consent is not implied by attendance.

## 3. Clinical triage
Reception staff record the presenting complaint in the patient's own words. No
member of reception staff assesses urgency. A registered clinician assigns the
triage category within 15 minutes of arrival.

## 4. Red flags requiring immediate escalation
Chest pain, difficulty breathing, altered consciousness, suspected sepsis,
suspected stroke, uncontrolled bleeding, or any patient the clinician judges
to be deteriorating. Escalate to the duty clinician immediately and record the
escalation time.

## 5. Interpreters and accessibility
Where the patient's preferred language is not English, book an approved
interpreter. Family members must not interpret for clinical consultations
except in an emergency, and this must be recorded with the reason.

## 6. Documentation
The intake record is completed before the patient leaves reception. Late
entries are permitted but must be timestamped as such and state the reason for
the delay.
"""),
        ("Infection Control Policy", """# Infection Control Policy

## 1. Hand hygiene
Staff decontaminate hands before and after every episode of patient contact,
before any aseptic procedure, and after contact with body fluids. Alcohol gel
is sufficient for visibly clean hands; soap and water are required where hands
are visibly soiled or where the patient has suspected or confirmed
*C. difficile*.

## 2. Equipment cleaning
| Item | Method | Frequency |
|---|---|---|
| Examination couch | Detergent wipe | After every patient |
| Blood pressure cuff | Detergent wipe | After every patient |
| Stethoscope | Alcohol wipe | After every patient |
| Consultation room surfaces | Detergent clean | Twice daily and when soiled |
| Treatment room floor | Detergent clean | Daily and after spillage |

Reusable instruments are not cleaned on site. They are returned to the
sterile services provider in a sealed transport container.

## 3. Spillage of blood or body fluids
Isolate the area, apply the chlorine-releasing granules from the spill kit,
leave for the stated contact time, then clean with detergent. Staff dealing
with a spillage wear gloves and an apron as a minimum.

## 4. Personal protective equipment
Gloves and aprons are single-use and changed between patients. Fluid-resistant
surgical masks are worn where splashing is anticipated. PPE is removed and
disposed of inside the clinical area before hand hygiene.

## 5. Sharps
Sharps are disposed of at the point of use by the person who used them.
Containers are replaced at the fill line, never overfilled, and are signed and
dated on assembly and closure.

## 6. Staff illness
Staff with diarrhoea or vomiting must not attend work until 48 hours after the
last episode.
"""),
        ("Consent, Confidentiality and Records Retention", """# Consent, Confidentiality and Records Retention

## 1. Lawful basis
Personal data is processed for the provision of healthcare. Special-category
health data is processed on the basis of the provision of health treatment by
a professional under a duty of confidentiality.

## 2. Consent requirements
Consent must be informed, specific and freely given, and may be withdrawn at
any time without affecting care. For any procedure carrying material risk,
consent is recorded in writing and includes the risks discussed and the
alternatives offered. Consent obtained more than 12 weeks before a planned
procedure is reconfirmed on the day.

## 3. Confidentiality
Patient information is disclosed only to those involved in that patient's
care, unless the patient consents or there is a legal obligation or an
overriding public interest. Every disclosure outside the care team is recorded
with the recipient, the reason and the date.

## 4. Retention periods
| Record type | Retention |
|---|---|
| Adult patient record | 8 years after last contact |
| Child patient record | Until 25th birthday, or 8 years after last contact if later |
| Maternity record | 25 years |
| Consent form | Held with the patient record |
| Staff training record | 6 years after employment ends |
| CCTV footage | 31 days |

## 5. Destruction
Records past their retention period are destroyed by confidential shredding or
certified secure deletion. A destruction log records the record type, the date
range and the person authorising it.

## 6. Subject access
A patient may request a copy of their record. The request is fulfilled within
one calendar month at no charge. Redaction is limited to third-party
information and is recorded with the reason.
"""),
    ],

    # ── Legal & professional services ────────────────────────────────────
    "legal": [
        ("Master Services Agreement — Acme / Redline", """# Master Services Agreement

**Parties:** Acme Holdings Ltd ("Client") and Redline Advisory LLP ("Supplier").
**Commencement:** 1 April. **Initial term:** 24 months.

## 3. Payment terms
Invoices are issued monthly in arrears and payable within **30 days** of
receipt. Late payment carries interest at 4% above base rate, accruing daily.
The Supplier may suspend services if an undisputed invoice remains unpaid for
45 days, on 10 days' written notice.

## 7. Limitation of liability
Neither party excludes liability for death or personal injury caused by
negligence, or for fraud. Subject to that, the Supplier's total aggregate
liability is capped at **the fees paid in the 12 months preceding the claim**.
Neither party is liable for loss of profit, loss of anticipated savings or
indirect loss.

## 9. Confidentiality
Each party keeps the other's confidential information secret for the term and
**5 years** after termination, and uses it only to perform the agreement.

## 11. Intellectual property
Pre-existing IP remains with its owner. IP created specifically for the Client
under a signed order form assigns to the Client on payment in full.

## 14. Termination
Either party may terminate for convenience on **90 days'** written notice, or
immediately on the other's insolvency or material breach not remedied within
30 days of notice.

## 16. Governing law
This agreement is governed by the laws of England and Wales, and the parties
submit to the exclusive jurisdiction of the English courts.
"""),
        ("Supplier Agreement — Beacon Logistics", """# Supply Agreement — Beacon Logistics

**Parties:** Acme Holdings Ltd and Beacon Logistics Ltd.
**Commencement:** 1 September. **Initial term:** 12 months, auto-renewing.

## 4. Payment terms
Invoices are payable within **60 days** of the end of the month in which they
are issued. No interest is payable on late sums for the first 30 days.

## 6. Service levels
On-time delivery must reach 97% measured monthly. Two consecutive months below
95% entitles Acme to terminate on 30 days' notice.

## 8. Limitation of liability
Beacon's aggregate liability is capped at **£250,000** per contract year.
Liability for loss or damage to goods in transit is capped at the declared
value of the consignment.

## 10. Confidentiality
Confidentiality obligations survive for **3 years** after termination.

## 13. Termination
Either party may terminate for convenience on **6 months'** written notice.
Acme may terminate immediately if Beacon undergoes a change of control to a
competitor of Acme.

## 15. Insurance
Beacon maintains public liability cover of not less than £5,000,000 and goods
in transit cover of not less than £1,000,000, and provides certificates
annually on the renewal date.

## 17. Governing law
Governed by the laws of England and Wales.
"""),
        ("Obligations and Key Dates Register", """# Obligations and Key Dates Register

A consolidated view of recurring obligations across current agreements.
Maintained by the contracts team; reviewed on the first Monday of each month.

## Renewal and notice dates
| Agreement | Renews | Notice required | Notice deadline |
|---|---|---|---|
| Acme / Redline MSA | 1 April | 90 days | 1 January |
| Beacon Logistics supply | 1 September | 6 months | 1 March |
| Office lease — Dock House | 24 June | 12 months | 24 June (prior year) |
| Insurance — professional indemnity | 30 November | n/a | Renewal quote by 1 October |

## Recurring obligations
- **Monthly:** issue service reports to Acme by the 5th working day.
- **Quarterly:** supplier performance review with Beacon; minutes circulated
  within 10 days.
- **Annually:** collect insurance certificates from all tier-1 suppliers on the
  renewal date; refresh conflict checks for all active matters.

## Escalation
Any obligation missed by more than five working days is reported to the
partner responsible for the client relationship, and recorded in the register
with the reason and the remedial action.

## Standing instruction
No agreement is allowed to auto-renew without a documented decision. The
register owner raises the renewal for decision **30 days before** the notice
deadline listed above.
"""),
    ],

    # ── Finance & accounting ─────────────────────────────────────────────
    "finance": [
        ("Expense and Approval Policy", """# Expense and Approval Policy

## 1. Approval thresholds
| Amount | Approver |
|---|---|
| Up to 500 | Line manager |
| 501 – 5,000 | Department head |
| 5,001 – 25,000 | Finance director |
| Above 25,000 | Board approval |

No individual may approve their own expense, nor an expense from which they
benefit. Splitting a single purchase to fall under a threshold is a
disciplinary matter.

## 2. Purchase orders
A purchase order is raised **before** goods or services are committed. Invoices
received without a matching PO are held in the exceptions queue and are not
paid until the PO is raised and approved retrospectively with a written reason.

## 3. Three-way match
Accounts payable matches the invoice to the purchase order and the goods
received note. Tolerance is 2% or 50, whichever is lower. Anything outside
tolerance is referred to the budget holder before payment.

## 4. Payment terms
Standard supplier terms are 30 days from invoice date. Early-settlement
discounts are taken where the discount exceeds the cost of capital. Payment
runs are made weekly on Thursdays.

## 5. Expense claims
Claims are submitted within 30 days of the expense with an itemised receipt.
Claims older than 90 days are not reimbursed without director approval.
Alcohol is reimbursable only as part of a client entertainment claim that
names the client and the business purpose.

## 6. Segregation of duties
The person who raises a payment cannot be the person who releases it. Bank
detail changes for any supplier require verbal verification with a known
contact using a number held on file — never a number supplied in the request.
"""),
        ("Month-End Close Checklist", """# Month-End Close Checklist

**Target:** working day 5. **Owner:** financial controller.

## Working day 1
- Close the purchase ledger to new invoices for the prior period.
- Post the payroll journal and reconcile to the payroll report.
- Confirm all bank feeds have imported to the last day of the month.

## Working day 2
- Bank reconciliations for all accounts; unreconciled items over 30 days old
  are listed with an explanation.
- Accruals for goods received not invoiced, taken from the GRNI report.
- Prepayments schedule updated and amortisation posted.

## Working day 3
- Fixed asset additions and disposals posted; depreciation run.
- Intercompany balances agreed and any difference resolved, not carried.
- Revenue cut-off review: confirm nothing invoiced after period end has been
  recognised in the period.

## Working day 4
- Draft trial balance issued for review.
- Variance analysis against budget for every cost centre above 10% or 10,000.
- Aged debt review; provisions updated for anything over 90 days.

## Working day 5
- Management accounts pack issued: P&L, balance sheet, cash flow, KPI summary
  and commentary on every material variance.
- Close the period in the ledger; no postings after close without controller
  approval.

## Controls
Every reconciliation is prepared by one person and reviewed by another, with
both names and dates recorded on the working paper.
"""),
        ("Revenue Recognition and Invoicing Standard", """# Revenue Recognition and Invoicing Standard

## 1. Principle
Revenue is recognised when control of the goods or services transfers to the
customer, not when the invoice is raised or the cash is received.

## 2. Contract types
- **Fixed-fee project:** recognised over time by reference to progress. Progress
  is measured by cost incurred against total forecast cost, reviewed monthly.
- **Time and materials:** recognised as the work is performed, in the period the
  time is recorded.
- **Subscription:** recognised evenly across the subscription term from the date
  access is granted. Setup fees that do not transfer a distinct service are
  spread across the term.

## 3. Invoicing
Invoices are raised within 5 working days of the milestone or period end and
must state: the purchase order reference where the customer requires one, the
period covered, and the payment terms. An invoice without a required PO
reference will be rejected by most customers and is the single most common
cause of late payment.

## 4. Credit notes
Credit notes require approval one level above the person who raised the
original invoice, and must state the reason. Credit notes are never used to
correct a coding error — that is a journal.

## 5. Deferred and accrued revenue
Amounts invoiced ahead of delivery sit in deferred revenue. Work delivered but
not yet invoiced sits in accrued revenue. Both are reconciled monthly and
supported by a schedule at contract level.

## 6. Bad debt
Debts over 120 days are provided at 50%, and over 180 days at 100%, unless the
credit controller documents a specific reason to expect recovery.
"""),
    ],

    # ── HR & staffing ────────────────────────────────────────────────────
    "hr_staffing": [
        ("Employee Handbook — Leave, Hours and Conduct", """# Employee Handbook

## 1. Annual leave
Permanent employees receive **24 days** of paid annual leave per year in
addition to public holidays, credited monthly in arrears. Up to **10 unused
days** may be carried forward into the next leave year and must be taken by
31 March, after which they lapse. Leave is requested at least two weeks in
advance and approved by the line manager.

Part-time employees receive a pro-rata entitlement based on contracted hours.

## 2. Notice periods
| Length of service | Notice by employee | Notice by employer |
|---|---|---|
| Probation (first 3 months) | 1 week | 1 week |
| Under 2 years | 1 month | 1 month |
| 2 years or more | 2 months | 2 months plus 1 week per completed year, capped at 12 weeks |

Notice must be given in writing. Payment in lieu of notice is at the
employer's discretion and is stated in the offer letter.

## 3. Remote working
Employees may work remotely up to **three days per week** by agreement with
their manager. Attendance in the office is expected on the team's designated
anchor day. Fully remote arrangements are possible for specific roles and are
recorded as a contractual variation, not an informal agreement.

Remote workers must have a suitable workspace, a secure network connection,
and must not work from a country outside the approved list without written
approval from HR, because of tax and right-to-work implications.

## 4. Working hours
Standard hours are 37.5 per week. Core hours are 10:00–16:00, with flexibility
either side by agreement. Overtime is not paid for salaried roles; time off in
lieu may be agreed for sustained additional hours.

## 5. Probation
Probation is three months and may be extended once by up to three months with
written reasons. Review meetings are held monthly during probation.

## 6. Sickness absence
Notify your manager before your normal start time on the first day. Self
certification covers the first 7 calendar days; a fit note is required beyond
that. Return-to-work discussions are held after every absence.
"""),
        ("Backend Engineer — Role Description", """# Role Description: Backend Engineer

**Team:** Platform. **Reports to:** Engineering Manager. **Level:** Mid to senior.

## Purpose
Build and maintain the APIs and data services behind the customer-facing
product, with a focus on reliability and clarity over cleverness.

## Essential requirements
- 3+ years building production backend services.
- Strong Python **or** Go, and comfortable in the other within a quarter.
- Relational database design and query tuning (PostgreSQL preferred).
- REST API design; understands versioning, pagination and idempotency.
- Automated testing as a habit, not an afterthought.
- Experience operating what they build: logs, metrics, on-call.

## Desirable
- Message queues or event streaming (Kafka, SQS, Pub/Sub).
- Containers and one cloud platform (AWS, GCP or Azure).
- CI/CD pipeline ownership.
- Exposure to retrieval or ML-backed features.

## Not required
A computer science degree. We assess demonstrated ability, not credentials.

## Scorecard weighting
| Area | Weight |
|---|---|
| Backend depth (language, data modelling) | 35% |
| System design and trade-off reasoning | 25% |
| Testing and operational maturity | 20% |
| Collaboration and written communication | 20% |

## Interview process
Screening call (30 min) → technical conversation on past work (60 min) →
practical exercise reviewed together (90 min) → team and values conversation
(45 min). We do not use unpaid take-home work longer than two hours.
"""),
        ("Recruitment and Selection Policy", """# Recruitment and Selection Policy

## 1. Fair and consistent assessment
Every candidate for a role is assessed against the same published scorecard.
Interviewers score independently before discussing, to avoid anchoring on the
first opinion voiced.

## 2. Right to work
Right-to-work checks are completed before the first day, without exception.
The check is performed on the original document or through the online service,
and a dated copy is retained for the duration of employment plus two years.

## 3. References
Two references are requested after a verbal offer, one of which must be the
most recent employer. Offers are conditional until references and right-to-work
checks are complete.

## 4. Candidate data retention
| Data | Retention |
|---|---|
| Unsuccessful applicant CV and notes | 6 months from decision |
| Successful applicant records | Duration of employment + 6 years |
| Interview scorecards | 6 months, or duration of employment if hired |
| Right-to-work evidence | Employment + 2 years |

Candidates are told at application how long their data is kept.

## 5. Non-discrimination
Selection decisions are made on ability to perform the role. Age, sex, race,
religion, disability, sexual orientation, gender identity, marital status and
pregnancy play no part. Reasonable adjustments are offered at every stage and
requesting one is never held against a candidate.

## 6. Internal applicants
Internal candidates are told the outcome before external candidates and are
offered feedback from the hiring manager within five working days.
"""),
    ],

    # ── Manufacturing & operations ───────────────────────────────────────
    "manufacturing": [
        ("SOP-014: Line 2 Product Changeover", """# SOP-014: Line 2 Product Changeover

**Revision:** 4. **Applies to:** production operators and shift leaders.
**Estimated duration:** 45 minutes.

## Safety before you start
Line 2 must be at zero energy state. Apply lock-out/tag-out at the main
isolator and the pneumatic supply. The shift leader verifies both locks are in
place and signs the changeover record before any guard is opened.

## PPE required
Safety footwear, ANSI-rated eye protection and cut-resistant gloves for all
steps. Hearing protection is required while the line is running.

## Steps
1. **Clear the line.** Run out remaining product and remove all units from the
   conveyor. Reconcile the count against the batch record.
2. **Purge the filler.** Three cycles with cleaning solution, then two with
   product. Record the final conductivity reading.
3. **Change the format parts.** Replace the star wheel, guide rails and the
   change part set for the new format. Each part is stamped with its format
   code — confirm the code matches the work order before fitting.
4. **Reset the machine recipe** to the new product code. Two people confirm the
   recipe number against the work order and both sign.
5. **Adjust the date coder** and print one sample. Verify the date, batch and
   lot against the work order.
6. **Remove lock-out** and run a five-unit trial at reduced speed.
7. **First-article inspection.** Quality inspects the five trial units against
   the specification. Production does not resume until quality signs off.

## Records
The changeover record captures: start and end time, format parts fitted,
recipe number, both verification signatures, and the first-article result.

## Common failure
The most frequent changeover defect is a mismatched guide rail causing units to
tip at the transfer. If units tip during the trial, stop and re-check the rail
format code before adjusting anything else.
"""),
        ("SOP-021: Welding Cell Operation", """# SOP-021: Welding Cell Operation

**Revision:** 2. **Process:** MIG welding, mild steel frames.

## PPE — mandatory, no exceptions
- Welding helmet with auto-darkening filter, shade 10 minimum.
- Flame-resistant welding jacket, fully fastened.
- Leather welding gauntlets.
- Safety footwear and long trousers with no cuffs.
- Respiratory protection (FFP3) where local exhaust ventilation is unavailable
  or has failed its monthly check.

Contact lenses may be worn. Synthetic clothing must not be worn under the
welding jacket.

## Before starting
1. Confirm local exhaust ventilation is running and within its inspection date.
2. Check the screens are in position so no one outside the cell has line of
   sight to the arc.
3. Confirm the fire extinguisher is present and in date; a hot-work permit is
   required for any welding outside the designated cell.
4. Inspect the torch, earth clamp and cables for damage. Damaged cables are
   removed from service, not taped.

## Parameters
| Material thickness | Wire | Voltage | Wire speed |
|---|---|---|---|
| 1.5 mm | 0.8 mm | 17–18 V | 4.5 m/min |
| 3.0 mm | 0.8 mm | 20–21 V | 6.5 m/min |
| 6.0 mm | 1.0 mm | 24–26 V | 8.0 m/min |

## After welding
Allow the workpiece to cool in the marked quench area. Hot work is monitored
for 30 minutes after the last arc before the area is left unattended.

## Weld quality
Visual inspection on every weld: no undercut, no visible porosity, consistent
bead width. Any weld showing porosity is ground out and re-welded — never
filled over.
"""),
        ("Non-Conformance and Corrective Action Log", """# Non-Conformance and Corrective Action Log

Reviewed at the weekly quality meeting. A non-conformance is closed only when
the corrective action has been **verified effective**, not when it has been
actioned.

## Open items
| NCR | Raised | Defect | Line | Corrective action | Verified |
|---|---|---|---|---|---|
| NCR-118 | 03 Mar | Mismatched guide rail after changeover | 2 | Format codes stamped on all change parts | **Not verified** |
| NCR-121 | 09 Mar | Weld porosity on frame batch B-77 | Weld | Gas flow check added to pre-start | **Not verified** |
| NCR-124 | 15 Mar | Date coder printed prior batch code | 2 | Two-person recipe verification added to SOP-014 | Verified 22 Mar |
| NCR-126 | 21 Mar | Label misalignment, 40 units | 3 | Sensor recalibrated | **Not verified** |
| NCR-129 | 28 Mar | Incoming steel out of flatness spec | Goods in | Supplier notified, batch quarantined | **Not verified** |

## Last month's findings by defect type
| Defect type | Count | Trend |
|---|---|---|
| Changeover error | 6 | Down from 11 |
| Weld porosity | 4 | Flat |
| Labelling / coding | 5 | Up from 2 |
| Incoming material | 3 | Up from 1 |
| Other | 2 | Flat |

## Escalation rule
Any non-conformance open for more than 30 days without a verified corrective
action is escalated to the operations manager and reported at the monthly
management review. Four of the five open items above are past that threshold.
"""),
    ],

    # ── Education & training ─────────────────────────────────────────────
    "education": [
        ("Module 3 — Data Structures: Teaching Notes", """# Module 3 — Data Structures

**Duration:** 3 weeks. **Prerequisites:** Module 2 (control flow, functions).

## Key concepts

### 3.1 Arrays and lists
Contiguous storage with constant-time access by index. Insertion in the middle
costs linear time because everything after the insertion point must shift.
*Example:* a seating chart in a theatre — finding row 12 seat 4 is instant, but
inserting an extra seat mid-row means moving everyone along.

### 3.2 Hash tables
Key-value storage with average constant-time lookup. A hash function maps the
key to a bucket. Collisions are resolved by chaining or open addressing.
Worst-case lookup degrades to linear when every key collides.
*Example:* a library index card system where cards are filed by the first two
letters of the author's surname — usually one card per drawer, but the "SM"
drawer is always full.

### 3.3 Trees
Hierarchical structure with a root and children. A binary search tree keeps
smaller values left and larger right, giving logarithmic search **when
balanced**. An unbalanced tree degenerates to a linked list.
*Example:* a knockout tournament bracket.

### 3.4 Graphs
Nodes and edges, directed or undirected, weighted or unweighted. Traversal by
breadth-first (shortest path in unweighted graphs) or depth-first.
*Example:* connecting flights between airports.

## Common misconceptions
- Students assume hash tables are always O(1) — press them on the worst case.
- Students assume tree operations are always O(log n) — press them on balance.
- Students confuse "sorted" with "searchable in log time"; a sorted *linked
  list* is still linear to search.

## Suggested activity
Give students a dataset and ask them to justify a structure choice in writing
before coding. The justification is the assessed part, not the code.
"""),
        ("Course Syllabus and Learning Outcomes", """# Course Syllabus — Introduction to Computer Science

## Learning outcomes
On completion, a student can:

| Code | Outcome | Assessed by |
|---|---|---|
| LO1 | Write, trace and debug programs using variables, control flow and functions | Coursework 1, Exam Q1–Q3 |
| LO2 | Select and justify an appropriate data structure for a given problem | Coursework 2 |
| LO3 | Analyse algorithmic complexity using big-O notation | Exam Q4–Q6 |
| LO4 | Design and normalise a relational schema | Coursework 3 |
| LO5 | Apply version control and automated testing in a team project | Group project |
| LO6 | Evaluate the ethical and privacy implications of a computing system | *Not currently assessed* |
| LO7 | Communicate a technical design in writing to a non-specialist reader | *Not currently assessed* |

## Module structure
1. Programming fundamentals (3 weeks)
2. Control flow and functions (2 weeks)
3. Data structures (3 weeks)
4. Algorithms and complexity (3 weeks)
5. Databases (2 weeks)
6. Team project (3 weeks)

## Assessment weighting
Coursework 1 — 15% · Coursework 2 — 20% · Coursework 3 — 15% ·
Group project — 20% · Final exam — 30%.

## Known gap
LO6 and LO7 appear in the outcomes but no assessment currently evidences them.
The group project is the natural home for both and this is flagged for the
next syllabus review.

## Academic integrity
Collaboration is encouraged on understanding, never on submitted artefacts.
Where AI tools are used, students declare what was generated and what they
changed; undeclared use is treated as misconduct.
"""),
        ("Assessment and Question Bank Standards", """# Assessment and Question Bank Standards

## 1. Every question maps to an outcome
No question enters the bank without a learning-outcome code. A question that
maps to nothing is either testing the wrong thing or the syllabus is missing an
outcome.

## 2. Cognitive spread
Each exam covers the range, not just recall:
| Level | Target share | Verb examples |
|---|---|---|
| Remember / understand | 30% | define, describe, explain |
| Apply | 40% | trace, calculate, implement |
| Analyse / evaluate | 30% | compare, justify, critique |

An exam that is 80% recall is a memory test, not an assessment of the outcomes.

## 3. Question construction
- One idea per question; if it needs "and", split it.
- Distractors in multiple choice must be plausible and reflect real
  misconceptions — never joke answers, which give the answer away by
  elimination.
- Avoid negatives ("which is NOT..."); if unavoidable, emphasise the negative.
- State the marks available and what earns them.

## 4. Marking
Every question has a model answer and a mark scheme written **before** the
paper is sat. Marks are awarded for method as well as result; a correct method
with an arithmetic slip earns most of the marks.

## 5. Moderation
A second marker reviews a 10% sample plus every fail and every mark within 2%
of a grade boundary. Disagreements over 5 marks go to a third marker.

## 6. Reasonable adjustments
Extra time and alternative formats are arranged in advance and never disclosed
to other students.
"""),
    ],

    # ── Real estate & property ───────────────────────────────────────────
    "real_estate": [
        ("Commercial Lease — Unit 4, Dock House", """# Lease — Unit 4, Dock House

**Landlord:** Dockside Estates Ltd. **Tenant:** Meridian Design Ltd.
**Term:** 10 years from **24 June** (year 1).

## 2. Permitted use
The premises may be used only as **offices within Use Class E**. Use as a
retail shop, a restaurant, or for any purpose generating noise audible from the
adjoining unit is prohibited. Any change of use requires the landlord's prior
written consent, not to be unreasonably withheld.

## 4. Rent
Initial rent: **£84,000 per annum**, payable quarterly in advance on the usual
quarter days.

## 5. Rent review
Rent is reviewed on the **fifth anniversary** of the term commencement — that
is, **24 June in year 5** — to open market rental value, upward only. Either
party may trigger the review by notice; if the parties do not agree within
three months, the matter goes to an independent surveyor appointed by the RICS.

## 7. Break clause
The tenant may terminate on the **fifth anniversary** by giving not less than
**six months' written notice**, conditional on:
(a) payment of all rent due to the break date;
(b) giving vacant possession; and
(c) no material subsisting breach of the repairing covenant.
The break is personal to Meridian Design Ltd and is not exercisable by an
assignee.

## 9. Repair
The tenant keeps the interior in good and substantial repair, excluding
structure, roof and exterior, which are the landlord's responsibility and
recovered through the service charge. The tenant is not obliged to put the
premises into better condition than evidenced by the schedule of condition
annexed to this lease.

## 11. Alterations
Non-structural internal alterations require written consent. Structural
alterations are prohibited.

## 13. Alienation
Assignment of the whole is permitted with consent. Underletting of part is
prohibited.
"""),
        ("Commercial Lease — Riverside Retail Unit 9", """# Lease — Unit 9, Riverside Centre

**Landlord:** Riverside Centre Management Ltd. **Tenant:** Kettle & Co Ltd.
**Term:** 5 years from **1 October** (year 1).

## 2. Permitted use
Use as a **coffee shop and light food preparation** within Use Class E.
Hot-food takeaway is expressly excluded. Trading hours are restricted to
07:00–19:00 Monday to Saturday and 09:00–17:00 on Sunday.

## 4. Rent
Initial rent: **£46,000 per annum**, payable monthly in advance.

## 5. Rent review
Rent is reviewed on the **third anniversary** — **1 October in year 3** — by
reference to the annual increase in the Consumer Prices Index, subject to a
collar of 1% and a cap of 4% per annum.

## 7. Break clause
Mutual break on the **third anniversary** on **nine months' written notice**.
The tenant's break is conditional on payment of rent to the break date and
vacant possession. There is no condition relating to repair.

## 9. Repair
Full repairing and insuring. The tenant repairs the whole of the demised
premises including the shopfront, and contributes to common parts through the
service charge.

## 10. Service charge
Capped at £8,000 per annum for the first three years, uncapped thereafter.

## 12. Reinstatement
At the end of the term the tenant removes the extraction equipment and makes
good, unless the landlord notifies otherwise not less than three months before
expiry.
"""),
        ("Portfolio Register — Key Dates and Obligations", """# Portfolio Register — Key Dates and Obligations

Reviewed monthly by the asset management team.

## Rent reviews falling due in the next twelve months
| Property | Tenant | Review date | Basis |
|---|---|---|---|
| Unit 4, Dock House | Meridian Design | 24 June (year 5) | Open market, upward only |
| Unit 9, Riverside Centre | Kettle & Co | 1 October (year 3) | CPI, collar 1% cap 4% |
| Warehouse 2, Fenmoor | Halden Logistics | 12 January | Open market, upward only |

## Break dates
| Property | Break date | Notice required | Notice deadline |
|---|---|---|---|
| Unit 4, Dock House | 24 June (year 5) | 6 months | 24 December (year 4) |
| Unit 9, Riverside Centre | 1 October (year 3) | 9 months | 1 January (year 3) |

## Repair obligations across the portfolio
- **Dock House units:** internal repair only; landlord retains structure, roof
  and exterior, recovered via service charge. Schedules of condition limit
  tenant liability on units 4 and 6.
- **Riverside Centre units:** full repairing and insuring, including shopfronts.
  Service charge capped for the first three years on unit 9 only.
- **Fenmoor warehouses:** full repairing, with a schedule of condition on
  warehouse 2 limiting liability for the existing roof.

## Standing action
Break notice deadlines are diarised **60 days ahead** of the deadline. A break
right lost by late notice is the single most expensive administrative failure
in the portfolio — a missed notice on Dock House commits five further years at
the reviewed rent.
"""),
    ],

    # ── Retail & e-commerce ──────────────────────────────────────────────
    "retail": [
        ("sales_by_category", """category,units_sold,revenue,returns,return_rate
Coffee Machines,412,164800,37,0.090
Grinders,388,77600,12,0.031
Filters & Papers,2140,21400,8,0.004
Mugs & Glassware,1655,33100,141,0.085
Beans & Blends,3980,119400,19,0.005
Accessories,921,27630,74,0.080
Cleaning & Descaler,640,12800,3,0.005
Gift Sets,505,50500,58,0.115
"""),
        ("Supplier Terms Summary", """# Supplier Terms Summary

## Current suppliers
| Supplier | Category | Lead time | MOQ | Payment terms |
|---|---|---|---|---|
| Brew Systems Ltd | Coffee machines | **6 weeks** | 24 units | 60 days |
| Grindwell BV | Grinders | **4 weeks** | 50 units | 45 days |
| Papertrail Co | Filters & papers | **10 days** | 5,000 units | 30 days |
| Ceramica SA | Mugs & glassware | **8 weeks** | 200 units | 30 days |
| Highland Roasters | Beans & blends | **5 days** | 40 kg | 14 days |
| Fitwell Parts | Accessories | **3 weeks** | 100 units | 30 days |

## Ordering rules
Reorder points are set at lead time plus two weeks of average demand. For
Ceramica SA the eight-week lead time plus an eight-week MOQ cycle means
glassware must be forecast a full quarter ahead — it is the most common cause
of stockouts in the range.

## Price breaks
Brew Systems: 5% at 48 units, 8% at 96 units per order.
Highland Roasters: 3% on standing monthly orders above 200 kg.
Ceramica SA: no price break; MOQ is the only lever.

## Quality and rejection
Goods are inspected within 5 working days of receipt. Rejected goods are
notified with photographs within that window; after 5 days the consignment is
deemed accepted.
"""),
        ("Returns, Warranty and Consumer Rights Policy", """# Returns, Warranty and Consumer Rights Policy

## 1. Change-of-mind returns
Online customers may cancel within **14 days** of delivery and return within a
further 14 days. Refunds are issued within 14 days of receiving the goods back,
or of proof of return. Return postage for change of mind is paid by the
customer unless the item was misdescribed.

## 2. Faulty goods
| When the fault appears | Customer's right |
|---|---|
| Within 30 days | Full refund |
| 30 days – 6 months | Repair or replacement; refund if that fails |
| 6 months – 6 years | Repair or replacement, customer may need to show the fault was present at delivery |

Faults reported within six months are presumed to have been present at delivery
unless we can show otherwise.

## 3. Manufacturer warranty
| Category | Warranty |
|---|---|
| Coffee machines | 2 years parts and labour |
| Grinders | 2 years parts, 1 year labour |
| Glassware | 30 days against manufacturing defect |
| Accessories | 1 year |

Warranty is in addition to, and does not replace, statutory rights.

## 4. Exclusions
Descaling failures, limescale damage, and damage from using non-recommended
cleaning products are excluded from warranty. Gift sets returned incomplete are
refunded less the value of the missing item.

## 5. High-return lines
Gift sets and coffee machines carry the highest return rates in the range.
Gift-set returns are predominantly seasonal and cosmetic (damaged outer
packaging); machine returns are predominantly descaling-related and are
reduced by including the descaler guide in the box.
"""),
    ],

    # ── Something else / general ─────────────────────────────────────────
    "general": [
        ("Company Handbook — How We Work", """# Company Handbook — How We Work

## Purpose
This handbook is the single place to look before asking. If something here is
wrong or out of date, correcting it is everyone's job.

## Working hours and flexibility
Standard hours are 37.5 per week with core hours 10:00–16:00. Work outside core
hours by agreement. We measure output, not attendance.

## Leave
24 days of paid annual leave plus public holidays. Up to 10 days carry forward
and must be used by 31 March. Request leave two weeks ahead where you can.

## Communication norms
- Write decisions down. A decision that exists only in a meeting did not happen.
- Default to asynchronous. Meetings are for things that genuinely need
  discussion, and every meeting has an agenda and an owner.
- Assume good intent, and be specific when disagreeing.

## Expenses
Spend up to 500 with your manager's approval. Anything higher needs a
department head. Submit claims within 30 days with an itemised receipt.

## Equipment and security
Company devices are encrypted and receive updates within 30 days of release.
Use the password manager for every work credential. Never approve a
multi-factor prompt you did not initiate — report it instead.

## Onboarding in the first week
Day 1: accounts, equipment, handbook. Day 2: product walkthrough. Day 3: shadow
a customer conversation. Day 5: first small change shipped, with a buddy.

## Leaving
Notice periods are in your contract. We run an exit conversation for everyone,
and what is said in it is reported only as themes, never attributed.
"""),
        ("Information Security and Data Handling Policy", """# Information Security and Data Handling Policy

## 1. Classification
| Level | Examples | Handling |
|---|---|---|
| Public | Marketing material, published docs | No restriction |
| Internal | Process documents, plans | Staff only; do not post externally |
| Confidential | Customer data, contracts, financials | Named access only; encrypt in transit and at rest |
| Restricted | Credentials, security keys | Password manager only; never in chat, email or code |

## 2. Access
Access follows least privilege and is reviewed quarterly. Access is removed on
the last working day, not the following week. Shared logins are prohibited.

## 3. Customer data
Customer data is processed only for delivering the service, and only in the
approved regions. It is never copied to personal devices or personal cloud
accounts, and never used to test in a non-production environment without
anonymisation.

## 4. Retention
| Data | Retention |
|---|---|
| Customer records | Duration of contract + 6 years |
| Application logs | 90 days |
| Backups | 35 days rolling |
| Recruitment records (unsuccessful) | 6 months |

## 5. Incidents
Report a suspected incident within one hour to the security contact — including
lost devices and mistaken emails. Reporting quickly is always the right call
and is never penalised, even when the cause was a mistake.

## 6. Third parties
No supplier receives confidential data without a signed agreement covering
confidentiality, security and deletion on termination.
"""),
        ("Quarterly Operating Plan and Key Dates", """# Quarterly Operating Plan

## Objectives this quarter
1. **Reduce onboarding time** for new customers from 21 days to 10.
2. **Improve retention** by closing the top three churn reasons from last
   quarter's exit interviews.
3. **Cut manual reporting effort** by automating the monthly customer report.

## Key dates and deadlines
| Date | Commitment | Owner |
|---|---|---|
| 15th of each month | Board pack circulated | Finance |
| Last working day of the month | Customer reports issued | Operations |
| 30 April | Insurance renewal — quotes required by 1 April | Finance |
| 31 May | Annual security review and access audit | Security |
| 15 June | Quarterly objective review | Leadership |
| 30 June | Supplier contract review; 90 days' notice due for annual renewals | Operations |

## Standing obligations
- Access review every quarter, evidenced in the audit log.
- Backup restore tested quarterly — an untested backup is not a backup.
- Every customer-impacting incident gets a written follow-up within 5 working
  days.

## Risks being tracked
| Risk | Impact | Mitigation |
|---|---|---|
| Key-person dependency in operations | High | Runbooks written for the top 5 recurring tasks |
| Supplier auto-renewal missed | Medium | Notice deadlines diarised 60 days ahead |
| Onboarding delays from data quality | High | Pre-flight checklist added before kickoff |
"""),
    ],
}


# ── first-week checklists ────────────────────────────────────────────────
# These land on the workspace's task board so the first session has a route
# through the product instead of a blank desktop. They name the customer's own
# documents, not ours — "upload your equipment log", not "upload a file".
CHECKLISTS: dict[str, list[str]] = {
    "it_services": [
        "Upload your current client SOW and ask what is out of scope",
        "Upload a runbook and ask the Runbook Engineer to summarise the recovery steps",
        "Check the service-credit thresholds across your client contracts",
        "Turn on the Contract intake review automation",
        "Invite the delivery lead who answers client scope questions",
    ],
    "healthcare": [
        "Upload your patient intake protocol and ask the Protocol Assistant to summarise it",
        "Upload your infection-control policy and check the equipment cleaning frequencies",
        "Ask which of your policies mention retention periods",
        "Review who can see personal data in Admin → Access",
        "Invite the practice manager and one clinical lead",
    ],
    "legal": [
        "Upload two agreements and ask Clause Finder to compare the liability caps",
        "Ask which agreements renew in the next 90 days",
        "Build the obligations register from your own contracts",
        "Turn on the New agreement triage automation",
        "Invite the fee earner who owns the contracts inbox",
    ],
    "finance": [
        "Upload last month's supplier invoices and run the invoice analyser",
        "Ask what your approval thresholds are and who can approve what",
        "Upload a sales export and chart revenue by category in Dashboards",
        "Turn on the Invoice intake automation",
        "Invite the financial controller",
    ],
    "hr_staffing": [
        "Upload your employee handbook and ask about leave carry-over",
        "Upload a CV and screen it against a role description",
        "Ask what notice period applies at two years of service",
        "Turn on the CV intake screening automation",
        "Invite your HR lead — give them the HR role, not admin",
    ],
    "manufacturing": [
        "Upload an SOP and ask which PPE it requires",
        "Upload your non-conformance log and ask which items are unverified",
        "Ask for last month's inspection findings by defect type",
        "Turn on the Quality record intake automation",
        "Invite a shift leader and check the SOP answers read correctly to them",
    ],
    "education": [
        "Upload a module's teaching notes and ask for an explanation with an example",
        "Generate ten exam questions from this week's material",
        "Upload the syllabus and ask which outcomes are not assessed",
        "Turn on the Course material intake automation",
        "Invite a colleague teaching the same module",
    ],
    "real_estate": [
        "Upload two leases and ask which have a rent review in the next twelve months",
        "Ask what the break clause conditions are on your newest lease",
        "Compare repair obligations across the portfolio",
        "Turn on the Lease intake automation",
        "Invite the asset manager who diarises notice deadlines",
    ],
    "retail": [
        "Upload a sales export and chart it by category in Dashboards",
        "Ask which products have the highest return rate",
        "Upload your supplier terms and ask for lead times and minimum order quantities",
        "Turn on the Supplier document intake automation",
        "Invite whoever places the purchase orders",
    ],
    "general": [
        "Upload five documents your team asks about most",
        "Ask a question you would normally have to look up manually",
        "Check the citations — every answer should point at a real document",
        "Turn on the Document intake summary automation",
        "Invite one colleague and see whether the answers hold up for them",
    ],
}


def for_industry(industry_id: str) -> list[Doc]:
    """Starter documents for a profile — empty list if the profile has none."""
    return PACKS.get(industry_id, [])


def checklist_for(industry_id: str) -> list[str]:
    return CHECKLISTS.get(industry_id, CHECKLISTS["general"])

