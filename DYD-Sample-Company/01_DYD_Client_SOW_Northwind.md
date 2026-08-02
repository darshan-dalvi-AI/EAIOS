# Statement of Work — Northwind Logistics Pvt. Ltd.

**Supplier:** DYD Technologies Pvt. Ltd.
**Client:** Northwind Logistics Pvt. Ltd., Bhiwandi, Maharashtra
**SOW reference:** DYD-SOW-2026-011
**Effective:** 1 April 2026 · **Ends:** 31 March 2027
**DYD engagement lead:** Darshan Dalvi (Delivery Manager)
**Client sponsor:** Kavita Menon (Head of Operations, Northwind Logistics)

---

## 1. Scope of Work — what IS included

DYD Technologies will deliver the following, and only the following, under this SOW:

1. **Warehouse Management System (WMS) migration** from the client's on-premise Oracle 11g
   estate to PostgreSQL 16 hosted on AWS Mumbai (ap-south-1).
2. **Application modernisation** of the existing consignment-tracking module: rewrite from
   Java 8 / Struts to Spring Boot 3, retaining the current database contract.
3. **Integration** with two third-party carriers — Blue Dart and Delhivery — via their REST
   consignment APIs, including retry and reconciliation logic.
4. **Hypercare support** for 90 calendar days following go-live, at P1 response within
   30 minutes and P2 response within 4 business hours.
5. **Knowledge transfer**: four half-day sessions for the client's internal IT team, plus
   runbook documentation handed over in Markdown.
6. **Performance target**: the consignment search endpoint must return within 800 ms at the
   95th percentile under a load of 200 concurrent users.

## 2. Explicitly OUT of scope

The following are expressly excluded from this SOW and will be quoted separately if required:

1. **Data migration of archived consignments older than 1 April 2023.** Historical archive
   migration is a separate engagement, quoted at ₹8,50,000.
2. **Third-party licence costs** — Oracle, AWS and carrier API fees remain the client's
   responsibility and are not included in the fees below.
3. **Mobile application development.** The existing Android driver app is out of scope; no
   changes will be made to it.
4. **End-user training beyond the four knowledge-transfer sessions** listed in section 1.6.
5. **24×7 support after the 90-day hypercare period.** Ongoing support requires a separate
   Managed Services Agreement.
6. **Hardware procurement** of any kind, including network equipment at client warehouses.
7. **Customs and regulatory compliance certification.** DYD will supply technical evidence
   but will not act as the certifying party.

## 3. Commercial terms

| Item | Amount (INR) |
|---|---|
| Fixed-price delivery fee | 42,00,000 |
| Hypercare (90 days, included) | 0 |
| Optional archive migration | 8,50,000 |
| Optional post-hypercare support, per month | 1,75,000 |

Payment schedule: 20% on signature, 30% on completion of migration, 30% on go-live,
20% on hypercare exit.

## 4. Acceptance criteria

Delivery is accepted when all of the following hold for five consecutive business days:

- Consignment search p95 latency ≤ 800 ms at 200 concurrent users
- Zero P1 defects open
- Fewer than five P2 defects open
- Carrier reconciliation discrepancy below 0.1% of daily consignment volume

## 5. Assumptions

- The client provides a stable staging environment mirroring production by 15 April 2026.
- Client subject-matter experts are available for a minimum of six hours per week.
- Carrier API sandbox credentials are supplied by the client within ten business days of
  signature. Delay here shifts the go-live date day for day.

## 6. Change control

Any change to scope, timeline or fees requires a written Change Request signed by Kavita Menon
for the client and Darshan Dalvi for DYD Technologies. Verbal instructions do not vary this SOW.
