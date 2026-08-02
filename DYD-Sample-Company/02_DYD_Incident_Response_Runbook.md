# Incident Response Runbook — DYD Technologies

**Owner:** Rohit Kulkarni (Head of Platform Engineering)
**Version:** 4.2 · **Last reviewed:** 12 June 2026
**Applies to:** all production systems operated by DYD Technologies for client accounts

---

## 1. Severity definitions

| Severity | Definition | First response | Update cadence |
|---|---|---|---|
| P1 | Production down, or data loss occurring | 30 minutes | Every 30 minutes |
| P2 | Major function degraded, no workaround | 4 business hours | Every 4 hours |
| P3 | Minor function degraded, workaround exists | 1 business day | Daily |
| P4 | Cosmetic or documentation issue | 3 business days | On closure |

## 2. Database failover — PostgreSQL primary failure

This is the most frequently exercised procedure. Follow it in order; do not skip step 2.

### Step 1 — Confirm the primary is actually down
Do not fail over on a single failed health check. Confirm from two independent sources:
- `pg_isready -h <primary-host> -p 5432` returns non-zero **twice**, sixty seconds apart
- The CloudWatch alarm `rds-primary-unreachable` is in ALARM state

A network partition that resolves itself is far more common than a genuine primary failure,
and an unnecessary failover costs more downtime than the fault did.

### Step 2 — Stop application writes before promoting
Scale the API deployment to zero replicas:

    kubectl scale deployment/api --replicas=0 -n production

**Skipping this step is the most damaging mistake in this runbook.** Promoting a replica while
the old primary is still accepting writes produces split-brain, and reconciling divergent
write histories has previously taken nine hours.

### Step 3 — Verify replica lag is acceptable
On the standby:

    SELECT now() - pg_last_xact_replay_timestamp() AS lag;

If lag exceeds 30 seconds, escalate to the Head of Platform Engineering before promoting.
Accepting a lagged replica means accepting that many seconds of committed transactions are lost.

### Step 4 — Promote the standby

    pg_ctl promote -D /var/lib/postgresql/16/main

Confirm with `SELECT pg_is_in_recovery();` — it must return `false`.

### Step 5 — Repoint the application
Update the `DATABASE_URL` secret to the promoted host, then restore replicas:

    kubectl scale deployment/api --replicas=4 -n production

### Step 6 — Verify before declaring recovery
- `/api/health` returns 200 from all four pods
- A write test transaction commits and is readable
- Error rate in the dashboard returns to baseline for ten consecutive minutes

### Step 7 — Rebuild the failed node as the new standby
Do this the same day. Running without a standby is running without a failover option.

**Target recovery time for this procedure: 25 minutes.** Measured mean over the last four
drills: 18 minutes.

## 3. Escalation path

1. On-call engineer — see the rota in the Team Directory
2. Rohit Kulkarni, Head of Platform Engineering — after 30 minutes on a P1
3. Darshan Dalvi, Delivery Manager — client communication on any P1 exceeding one hour
4. Client sponsor — only via the Delivery Manager, never directly by an engineer

## 4. Client communication rules

- The client is informed of any P1 within **15 minutes** of confirmation, before root cause
  is known. "We are investigating" sent early beats a detailed explanation sent late.
- Never speculate on cause in writing to a client during an active incident.
- Service credits are calculated by Finance from the incident log, not estimated by engineers.

## 5. Post-incident review

Every P1 requires a blameless post-incident review within five business days, covering: the
timeline, the contributing factors, what detection missed, and the specific corrective actions
with named owners and dates. Reviews are stored in the knowledge base and are not confidential
within DYD.
