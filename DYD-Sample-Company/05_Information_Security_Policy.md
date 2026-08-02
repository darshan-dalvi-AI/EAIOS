# Information Security Policy — DYD Technologies

**Document ID:** DYD-SEC-POL-001 · **Version:** 2.6 · **Owner:** Meera Joshi (CISO)
**Certification:** ISO/IEC 27001:2022 (certified Nov 2025) · **Next surveillance audit:** Nov 2026

## 1. Data classification

| Class | Examples | Storage | Sharing | Retention |
|---|---|---|---|---|
| Restricted | PHI, cardholder data, credentials, private keys | Encrypted, client region only | Named individuals, logged | Per contract, then destroy |
| Confidential | Client source code, contracts, financials, designs | DYD-managed repos and drives | Need to know | 7 years |
| Internal | Runbooks, methodology, org charts | DYD systems | All employees | 3 years |
| Public | Marketing, published case studies | Anywhere | Anyone | Indefinite |

Every document must carry a class. Unclassified defaults to **Confidential** — the
safe direction to be wrong in.

## 2. Access control

- Identity through SSO (Okta). Local accounts are prohibited in all environments,
  including non-production.
- MFA everywhere. Hardware tokens for production and for anyone holding
  administrative rights.
- Least privilege, granted through role-based groups, never to individuals.
- Production access is **time-bound**: elevation lasts a maximum of 4 hours and
  auto-revokes. Standing production access does not exist, including for the CTO.
- Access reviews quarterly; leavers revoked within **4 hours** of exit notification.
- Shared accounts are prohibited. Where a legacy system forces one, credentials
  live in the vault and every use is ticketed.

## 3. Encryption

| Where | Standard |
|---|---|
| At rest | AES-256, customer-managed keys where the contract requires it |
| In transit | TLS 1.3 (TLS 1.2 only by documented exception with an expiry date) |
| Key rotation | 90 days for client-facing workloads, 180 days internal |
| Secrets | HashiCorp Vault or AWS Secrets Manager — never in code, config or CI variables |
| Laptops | Full-disk encryption enforced by MDM; non-compliant devices lose network access |

## 4. Secure development

- All code reviewed by someone other than the author before merge. No exceptions,
  including for hotfixes — a hotfix is reviewed post-merge within 24 hours and the
  reviewer is named in the incident record.
- SAST on every pull request; dependency scanning daily.
- Critical and high vulnerabilities: **7 days** to remediate. Medium: 30 days.
- No client data in non-production. Test data is synthetic or irreversibly masked.
- Infrastructure as code only. Console changes in production are an incident,
  even when they fix something.

## 5. Acceptable use of AI tools

Added v2.5 (March 2026) after two near-misses.

- Client code, client data and contract text must not be pasted into public AI
  services. This includes "just the error message" when the error message contains
  a connection string, and it has.
- Approved: DYD's own K-OS workspace, and GitHub Copilot Business under the
  enterprise agreement with training disabled.
- AI-generated code is the author's responsibility. "The model wrote it" is not a
  defence at code review.
- Client contracts may prohibit AI assistance entirely — Meridian's does for core
  banking code. Check the SOW before using any assistant on an engagement.

## 6. Incident reporting

Any suspected security incident is reported to `security@dyd.example` **and** the
CISO within one hour of suspicion — not of confirmation. Reporting something that
turns out to be nothing is explicitly encouraged and has never been held against
anyone. Failing to report is a disciplinary matter.

Client notification follows MSA §7: within 24 hours of DYD becoming aware.
