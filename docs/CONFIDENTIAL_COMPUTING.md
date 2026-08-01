# K-OS — Confidential Computing (TEE) Architecture

**Status:** Design / Architecture Decision Record (not yet deployed)
**Author:** Darshan Dalvi · B.E. Computer Engineering capstone
**Last updated:** July 2026

> This document specifies how K-OS would run inside a **Trusted Execution
> Environment (TEE)** so that a company's private documents, chats and
> embeddings are protected *even from the cloud provider that hosts the
> service*. It is a design/threat-model artifact: the current deployment
> (Render compute + Supabase data) is a normal cloud stack and is **not**
> confidential. Confidential computing is an infrastructure change, not a
> configuration flag — this ADR is the plan for making that change.

---

## 1. Context and motivation

K-OS is pitched at mid-size, document-heavy companies that are nervous about
putting sensitive material (HR records, contracts, financials, source code)
into someone else's AI. The current architecture already protects data
**at rest** (Postgres/Storage encryption) and **in transit** (TLS). The gap it
does **not** close is data **in use**: while the FastAPI process is parsing a
contract, embedding it, or answering a question about it, that plaintext lives
in the host's RAM. Anyone with control of the host — a cloud operator, a
compromised hypervisor, a malicious insider, or an attacker who has rooted the
machine — can read it.

A **Trusted Execution Environment** closes that last gap. It is a
hardware-isolated, memory-encrypted region of a CPU in which code runs such
that even privileged software on the same machine (the OS, the hypervisor, the
cloud operator) cannot read or tamper with the data being processed. Two
properties make it useful:

1. **Confidentiality & integrity of data in use** — the CPU transparently
   encrypts the enclave's memory with keys held in hardware; the plaintext
   only ever exists inside the CPU package.
2. **Remote attestation** — the hardware can produce a signed, verifiable
   report proving *which exact code* is running inside a *genuine* enclave, so
   a remote client can refuse to send data until it has cryptographic proof it
   is talking to the real, unmodified K-OS and not an impostor or a
   tampered copy.

For K-OS the headline becomes: **"Your company's private AI, invisible even to
the cloud that runs it — and you can mathematically verify that."**

---

## 2. TEE technology landscape (2026)

There are two broad families of TEE, and the choice matters for a
container-based app like K-OS.

**Process-level enclaves (Intel SGX).** Protect a small slice of a single
process. Very strong isolation, but the application must be rewritten/split to
fit inside the enclave and stay within tight memory limits. Poor fit for a
full FastAPI + agents + RAG stack.

**VM-level enclaves / Confidential VMs (AMD SEV-SNP, Intel TDX).** Encrypt the
memory of an *entire virtual machine*. You "lift and shift" an existing
container image into a confidential VM with **no code changes**. This is the
right model for K-OS.

Current confidential-VM offerings (verified July 2026):

| Provider | Confidential VM | Hardware TEE | Attestation service |
|---|---|---|---|
| **Azure** | DCasv6 / ECasv6 (GA Sep 2025); DCesv6 / ECesv6 (Intel TDX, GA Feb 2026) | AMD SEV-SNP · Intel TDX | Microsoft Azure Attestation (MAA) |
| **Google Cloud** | Confidential VM (N2D, C3) | AMD SEV / SEV-SNP · Intel TDX | Google Cloud attestation (vTPM-based) |
| **AWS** | Nitro Enclaves (most EC2 families) + SEV-SNP on select instances | Nitro (VM-isolated) · AMD SEV-SNP | AWS Nitro attestation / NitroTPM (TPM 2.0) |

### Decision

**Deploy K-OS as a container inside an Azure Confidential VM using AMD SEV-SNP
(DCasv6/ECasv6 series), attested via Microsoft Azure Attestation (MAA).**

Rationale:

- **No application rewrite** — the existing Docker image runs unmodified inside
  the confidential VM; SEV-SNP encrypts the whole guest's memory.
- **Maturity & footprint** — SEV-SNP confidential VMs are generally available
  across 57+ Azure regions as of mid-2026, so the deployment is realistic, not
  experimental.
- **Turnkey attestation** — MAA gives a standard, verifiable attestation token
  without building a bespoke verifier, which keeps the project's scope sane.
- **Portability** — the same container also runs on GCP Confidential VMs or AWS
  Nitro with a different attestation front-end, so we are not locked in.

Intel TDX (DCesv6) is the natural alternative and the design below is
substantially the same; the only real difference is the attestation evidence
format (TDX quote vs. SEV-SNP report).

---

## 3. Threat model

**Trusted (inside the boundary):**

- The CPU package and its hardware root of trust (AMD Secure Processor).
- The K-OS container image *as measured at launch* — code, Python deps, config.
- The in-enclave memory: request plaintext, parsed documents, embeddings,
  decryption keys while in use.

**Untrusted (outside the boundary):**

- The hypervisor and host OS.
- The cloud operator and their staff / support tooling.
- Other tenants on the same physical host.
- Anyone who gains root on the host or physical access to the machine.
- The network.

**Attacks TEE defeats:**

- A cloud operator or rooted host dumping RAM to read documents/chats in use.
- A malicious hypervisor snapshotting or live-migrating the VM to exfiltrate
  memory (SEV-SNP adds integrity + anti-rollback vs. plain SEV).
- Serving a **tampered** build of K-OS — clients detect it via attestation
  because the measurement won't match the expected value.

**Attacks TEE does NOT defeat (stated honestly):**

- **Bugs inside K-OS itself.** A SQL-injection or auth flaw in the app is just
  as exploitable inside an enclave. TEE protects the *environment*, not the
  code's own correctness. (K-OS's existing RBAC, SQL guardrails, PII auditing
  still matter.)
- **Data that deliberately leaves the enclave.** See §5 — the external LLM call
  is the critical example.
- **Advanced physical side-channels** (power/timing/microarchitectural). CVMs
  raise the bar dramatically but are not a perfect guarantee; recent research
  (e.g., *SoK: A cloudy view on trust relationships of CVMs*, 2025) documents
  residual trust gaps in cloud CVM attestation chains.
- **A malicious cloud operator refusing service.** TEE protects
  confidentiality/integrity, not availability.

---

## 4. Remote attestation flow

Attestation is what turns "trust us, it's secure" into "verify it yourself."
The flow when a client (or an enterprise admin's browser) connects to K-OS:

```
 Client                          K-OS enclave (CVM)            AMD Secure Processor / MAA
   │                                    │                                 │
   │ 1. connect + random nonce ───────▶│                                 │
   │                                    │ 2. request attestation ────────▶│
   │                                    │    report (bind nonce +         │
   │                                    │    hash of enclave TLS pubkey)  │
   │                                    │◀─ 3. signed SNP report ─────────│
   │                                    │    (launch measurement,         │
   │                                    │     TCB version, nonce)         │
   │                                    │ 4. get MAA token proving        │
   │                                    │    report authenticity ────────▶│ (MAA)
   │◀── 5. attestation token + cert ────│◀────────────────────────────────│
   │                                                                       
   │ 6. client verifies:
   │    • token signed by MAA / AMD root cert chain
   │    • launch measurement == expected K-OS build hash
   │    • nonce matches (freshness, anti-replay)
   │    • TLS session bound to the attested key
   │ 7. only now send sensitive data ─▶
```

Key points:

- The SNP report is signed by the AMD Secure Processor with a **VCEK**
  (Versioned Chip Endorsement Key) that chains back to an **AMD root
  certificate** — so authenticity is rooted in silicon, not in the cloud
  operator.
- The report includes the **launch measurement** (a hash of exactly what was
  loaded into the VM). The client compares it to the known-good hash of the
  published K-OS image. If K-OS is tampered with, the measurement changes and
  verification fails.
- The client's **nonce** is included so an attacker can't replay an old report.
- The report is **bound to the enclave's TLS public key**, so the attested
  identity and the encrypted channel are the same entity (no MITM).

This is the mechanism behind the phrase examiners will want to hear:
*"the client cryptographically verifies the exact code and a genuine enclave
before any plaintext is sent."*

---

## 5. Mapping K-OS into the enclave (and the one hard problem)

Running the container in a CVM protects everything that stays **inside** the
box. Three data flows cross the boundary and must be reasoned about explicitly.

**5.1 Database & object storage (solvable).**
Postgres rows and uploaded files live in Supabase/managed storage *outside* the
enclave, so they must be **client-side encrypted inside the enclave** before
they leave. K-OS would hold the data-encryption key only in enclave memory
(released to it after successful attestation, e.g. via a secure key-release
service / sealed secret), encrypt documents and sensitive columns before
writing, and decrypt them only after reading them back in. The cloud storage
then holds ciphertext it cannot read. This is an incremental change to
`core/storage.py` and the models layer.

**5.2 The LLM call (the critical insight).**
This is the part most projects miss, and it is the strongest thing to say in a
viva. K-OS currently sends prompts (which contain retrieved document
passages) to an **external** LLM API (OpenRouter). **The moment plaintext
leaves the enclave for a third-party API, confidentiality is broken at that
boundary** — the enclave was pointless if the sensitive context is then shipped
to an outside model provider that can log it.

There are three honest resolutions, in increasing order of confidentiality:

1. **Run the model inside the enclave.** Use the existing Ollama path
   (`LLM_PROVIDER=ollama`) with a local model *inside* the confidential VM.
   Nothing leaves. Limited by CVM CPU/RAM for model size.
2. **Confidential GPU.** For larger models, use **NVIDIA Confidential Computing
   (H100/Blackwell)**, where the GPU itself is a TEE and the CPU↔GPU link is
   encrypted and attested. The model runs on the GPU without exposing prompts
   to the host. This is the production-grade "confidential AI" answer.
3. **Confidential inference endpoint.** Call an LLM that is *itself* running in
   an attested TEE, and extend the attestation chain to it. Emerging, and the
   cleanest fit with K-OS's existing "swap the provider" abstraction.

K-OS is well-positioned for this because the LLM layer is already a pluggable
interface (`llm/provider.py`) — moving from "external API" to "in-enclave
Ollama" or "confidential GPU endpoint" is a provider swap, not a rewrite.

**5.3 Secrets (solvable).**
JWT signing keys, the Supabase service key, etc. must never be baked into the
image (that would put them in the measured, publishable build). Instead they
are **released to the enclave only after it attests** — a secure key-release
pattern (Azure Key Vault "secure key release" bound to an attestation policy).
The enclave proves what it is, and only then receives its secrets.

---

## 6. What changes in the K-OS codebase

The beauty of the VM-level TEE choice is how little changes:

| Area | Change | Effort |
|---|---|---|
| Container image | None — same Docker image runs in the CVM | none |
| Host | Move compute from Render → Azure Confidential VM (DCasv6) | infra |
| `llm/provider.py` | Prefer in-enclave Ollama or confidential-GPU endpoint over external API | small |
| `core/storage.py` + models | Client-side encrypt documents/PII columns with an in-enclave key | medium |
| New `core/attestation.py` | Endpoint that returns the SNP/MAA attestation token; a `/api/attestation` route | small |
| Secrets | Move from plain env vars → attestation-gated secure key release | infra + small |
| Frontend | Optional: a "Verified enclave ✓" badge that checks the attestation token before login | small |

A nice demoable artifact: a `GET /api/attestation` endpoint that, when running
in a CVM, returns the live signed measurement, and a small client script that
verifies it against the expected build hash — the whole trust story in one call.

---

## 7. Trade-offs and consequences

**Costs**

- Confidential VMs are **paid, not free tier** — this cannot run on the current
  free Render/Supabase setup. A DCasv6 CVM is a real monthly cost.
- **Performance overhead** is modest for VM-level TEEs — typically single-digit
  to low-double-digit percent for memory-heavy workloads (SEV-SNP/TDX encrypt
  memory transparently); acceptable for K-OS's workload.
- **Operational complexity** — attestation policies, key-release, image
  measurement management, and reproducible builds (so the published measurement
  is verifiable) are real engineering work.

**Benefits**

- Data-in-use protection: the cloud operator genuinely cannot read customer
  documents, chats, or embeddings while they're processed.
- Verifiable integrity: clients prove they're using the untampered K-OS.
- A concrete regulatory / trust story (GDPR data-minimization, "digital
  sovereignty," regulated industries) — the exact market K-OS targets.

**Limitations to state plainly**

- TEE protects the environment, not K-OS's own code correctness.
- Full confidentiality requires solving the LLM-boundary problem (§5.2);
  otherwise it is "confidential up to the model call," which must be disclosed
  honestly.
- CVM attestation chains still involve some trust in the cloud/firmware; not an
  absolute guarantee against nation-state physical attacks.

---

## 8. Phased adoption plan

1. **Phase 0 — design (this document).** Threat model, TEE choice, attestation
   flow. *No cost.*
2. **Phase 1 — attestation-ready code.** Add `/api/attestation`, a reproducible
   build with a published measurement, and client-side verification script.
   Runs (as a labeled stub) on normal infra; becomes real inside a CVM.
3. **Phase 2 — confidential compute.** Deploy the existing container to an Azure
   DCasv6 Confidential VM; wire MAA; move secrets to attestation-gated release.
4. **Phase 3 — confidential data.** Client-side encrypt documents + PII columns
   with an in-enclave key so Supabase holds only ciphertext.
5. **Phase 4 — confidential AI.** Move inference in-enclave (Ollama) or to a
   confidential GPU (NVIDIA H100 CC) so no plaintext ever leaves — closing the
   §5.2 boundary and completing end-to-end confidentiality.

---

## 9. One-paragraph summary (for the viva)

> K-OS already protects data at rest and in transit; a Trusted Execution
> Environment closes the remaining gap — data **in use**. By deploying the
> existing container unchanged into an **AMD SEV-SNP confidential VM** on Azure,
> the whole application's memory is hardware-encrypted so the cloud operator
> can't read customer documents while they're processed, and **remote
> attestation** lets clients cryptographically verify they're talking to the
> genuine, unmodified K-OS before sending anything. The subtle part —
> and the strongest engineering point — is that a TEE is only as confidential
> as its weakest boundary: K-OS's external LLM call would leak plaintext, so
> true confidential AI means running the model **inside** the enclave or on a
> **confidential GPU**. Because K-OS's LLM layer is already pluggable, that
> becomes a provider swap rather than a rewrite.

---

## References

- [Azure Confidential Computing products — Microsoft Learn](https://learn.microsoft.com/en-us/azure/confidential-computing/overview-azure-products)
- [About Azure confidential VMs — Microsoft Learn](https://learn.microsoft.com/en-us/azure/confidential-computing/confidential-vm-overview)
- [Azure Confidential Computing for digital sovereignty and regulated workloads (2026)](https://techcommunity.microsoft.com/blog/AzureConfidentialComputingBlog/azure-confidential-computing-for-digital-sovereignty-and-regulated-workloads/4529932)
- [Confidential VM attestation — Google Cloud Documentation](https://docs.cloud.google.com/confidential-computing/confidential-vm/docs/attestation)
- [Remote attestation of SEV-SNP confidential VMs using e-vTPMs (arXiv)](https://arxiv.org/html/2303.16463)
- [Confidential VMs Explained: An Empirical Analysis of AMD SEV-SNP and Intel TDX (ACM)](https://dl.acm.org/doi/10.1145/3700418)
- [SoK: A cloudy view on trust relationships of CVMs (arXiv, 2025)](https://arxiv.org/pdf/2503.08256)
- [AMD SEV-SNP vs Intel TDX: who needs confidential VMs in 2026](https://servermall.com/blog/amd-sev-and-intel-tdx-who-needs-it/)
