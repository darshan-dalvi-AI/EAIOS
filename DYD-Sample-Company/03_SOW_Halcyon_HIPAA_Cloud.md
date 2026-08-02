# Statement of Work — Halcyon Health, HIPAA Cloud Landing Zone

**SOW ID:** DYD-SOW-C03-001 · **Projects:** P06, P07 · **Tier:** Gold
**Term:** 15 January 2026 – 31 August 2026 · **Value:** ₹1,26,00,000
**Delivery Manager:** Kabir Menon · **Client sponsor:** Dr. A. Fernandes, CIO

## 1. Regulatory context

Halcyon operates in India and serves US patients through a telehealth arm, so the
engagement carries **both** DPDP Act 2023 and HIPAA obligations. Where they differ,
DYD applies the stricter of the two. A Business Associate Agreement (BAA) is
executed and attached as Annexure C.

Protected Health Information (PHI) must:

- Reside in `ap-south-1` for Indian patients and `us-east-1` for US patients, with
  no cross-region replication of identifiable records.
- Be encrypted at rest with customer-managed KMS keys, rotated every 90 days.
- Be encrypted in transit with TLS 1.3; TLS 1.2 is permitted only for two named
  legacy HL7 endpoints, retiring 31 October 2026.
- Never appear in application logs, error traces, analytics events or support
  tickets. Log redaction is enforced at the collector, not the application.

## 2. Deliverables

1. Multi-account AWS landing zone (Control Tower) with four OUs: prod, non-prod,
   security, shared services.
2. PHI data-classification scheme and automated tagging enforcement via SCP.
3. HL7 v2 and FHIR R4 ingestion pipeline with de-identification for analytics.
4. Break-glass access procedure with dual authorisation and 12-month audit trail.
5. Patient portal (P07) — appointment booking, results viewing, secure messaging.
6. HIPAA technical-safeguards evidence pack mapped to §164.312.

## 3. Access control requirements

| Control | Requirement |
|---|---|
| Authentication | SSO via client Okta; no local accounts in any environment |
| MFA | Mandatory, hardware token for production |
| Least privilege | Time-bound elevation, maximum 4 hours, auto-revoked |
| Break-glass | Two named approvers, PagerDuty-logged, reviewed weekly |
| Audit retention | 6 years (HIPAA), exceeding DPDP's requirement |
| Offshore access | Named individuals only; list reviewed monthly by the CIO |

## 4. Out of scope

- Migration of the legacy PACS imaging archive.
- Clinical decision support, or anything meeting the definition of a medical device.
- HIPAA compliance of Halcyon's own on-premise systems.
- Medical coding, billing or claims processing logic.
- Penetration testing — client engages a third party; DYD remediates findings
  under a separate change request.

## 5. Commercial note

Halcyon carries the largest unpaid balance of any DYD client at **₹73,75,000**
across multiple invoices. Under MSA §8, DYD may suspend service after 60 days
overdue with 10 business days' notice. Suspension has not been exercised: the
account is strategically important and the delay is understood to be an internal
approval backlog rather than a dispute. Finance reviews this position monthly.
