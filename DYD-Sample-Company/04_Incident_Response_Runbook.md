# Incident Response Runbook — DYD 24×7 NOC

**Document ID:** DYD-OPS-RUN-011 · **Version:** 3.1 · **Owner:** Sneha Kulkarni (Head of Managed Services)
**Audience:** NOC engineers, SREs, on-call tech leads, delivery managers

## 1. The first five minutes

Do these in order. Do not skip step 2 to get to step 3 faster — an unacknowledged
incident with three engineers silently working it is how DYD missed the SLA on
INC-1027.

1. **Acknowledge** in PagerDuty. This starts the response clock and stops escalation.
2. **Declare severity** using the table below. When torn between two, pick the higher —
   downgrading later is free, upgrading late is not.
3. **Open the incident channel** `#inc-<id>-<client>` in Slack. Every decision goes here.
4. **Name the Incident Commander.** The first responder is IC until they hand over
   explicitly. The IC does not debug — the IC coordinates.
5. **Post the first client update** within the tier's first-response window, even
   if it says only "we are investigating, next update in 30 minutes".

## 2. Severity matrix

| Severity | Definition | First response | Resolution target | Who is woken |
|---|---|---|---|---|
| SEV-1 | Production down, or confirmed data loss / security breach | 15 min (Platinum), 30 (Gold), 60 (Silver) | 1 hour | IC + service owner + Delivery Manager + Head of MS |
| SEV-2 | Major function degraded, no workaround | 30 min | 4 hours | IC + service owner |
| SEV-3 | Minor degradation, workaround exists | 2 hours | 8 hours | On-call, business hours |
| SEV-4 | Cosmetic / query / request | Next business day | 24 hours | Queue |

**Automatic SEV-1 regardless of impact:** any suspected data breach, any PHI or
payment-card exposure, any incident a client's regulator has asked about, and any
outage lasting more than 30 minutes on a Platinum account.

## 3. Runbook — database failover did not promote replica

This is DYD's most expensive recurring failure. It caused the SEV-1 on Northwind
in March 2026 and has appeared in post-incident reviews four times since.

**Symptoms:** writes failing with `read-only transaction`, replica lag flat at a
non-zero value, health checks green (they only test connectivity, not writability).

1. Confirm the primary is genuinely gone: `pg_isready -h <primary>` from two
   different subnets. A network partition looks identical from one vantage point.
2. Check replica state: `SELECT pg_is_in_recovery();` — `true` means it never promoted.
3. Check replay lag: `SELECT now() - pg_last_xact_replay_timestamp();`
   **If lag exceeds 30 seconds, stop and escalate.** Promoting a lagging replica
   loses committed transactions, and for a banking or health client that is a
   worse incident than the outage.
4. Promote: `pg_ctl promote -D $PGDATA`, then confirm `pg_is_in_recovery()` is `false`.
5. Repoint the writer endpoint. Do **not** edit application config — move the DNS
   CNAME or the RDS endpoint, so rollback is one change and not fifty.
6. Verify a real write end-to-end, not a health check.
7. Rebuild the old primary as a replica **before** declaring resolution. An
   incident that ends with no standby is not resolved, it is deferred.

**Known trap:** the health check at `/healthz` returns 200 whenever the connection
pool responds, including when the database is read-only. It has masked this exact
failure twice. Fix tracked as `PLAT-2291`, unresolved since February.

## 4. Runbook — memory leak in order service

Root cause of **five** of DYD's SLA breaches this period, more than any other cause.

**Symptoms:** heap climbs steadily over roughly 40 hours, GC pauses lengthen, pods
OOMKilled and restart, orders time out during the restart window.

1. Confirm the pattern: `kubectl top pods -n orders` — look for a sawtooth.
2. Capture a heap dump **before** restarting, or the evidence is gone:
   `jcmd 1 GC.heap_dump /tmp/heap.hprof && kubectl cp ...`
3. Immediate mitigation: rolling restart, staggered, one pod at a time.
   `kubectl rollout restart deployment/order-service -n orders`
4. Raise replica count by 2 to absorb the restart window.
5. The underlying defect is an unbounded `ConcurrentHashMap` cache in
   `OrderEnrichmentService` with no eviction policy — tracked as `NWR-1184`,
   deferred three sprints running because it is not customer-visible until it is.

**Do not** raise the memory limit as a fix. It converts a 40-hour cycle into a
90-hour cycle and moves the outage to a week when nobody is expecting it.

## 5. Client communication

| Tier | First update | Cadence during incident | Post-incident review |
|---|---|---|---|
| Platinum | 15 minutes | Every 30 minutes | Within 5 business days |
| Gold | 30 minutes | Every 60 minutes | Within 10 business days |
| Silver | 60 minutes | Every 2 hours | On request |

Updates state: what is affected, what is not affected, what we are doing, when the
next update comes. They never state a cause before it is confirmed and never state
an ETA the team has not agreed. A wrong ETA costs more trust than no ETA.

## 6. Post-incident review

Mandatory for every SEV-1 and any SEV-2 that breached its target. Blameless: the
question is what made the error possible, never who made it. Every review produces
owned, dated actions — an action without a name and a date is a wish.

Reviews are logged in the incident register and the actions tracked to closure.
Any action open past 30 days is escalated to the Head of Managed Services.
