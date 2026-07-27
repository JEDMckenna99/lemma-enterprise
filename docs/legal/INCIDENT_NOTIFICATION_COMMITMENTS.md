# Incident Notification Commitments (Draft)

**Status:** Draft pending counsel review  
**Last updated:** 2026-07-27

Published commitments for security and privacy incidents affecting lemma.id
services. Operational runbooks remain authoritative for internal response.

## Customer-visible incidents

When an incident has **customer-visible impact** (L2 or above per
[`docs/operations/INCIDENT_DRILL_RUNBOOK.md`](../operations/INCIDENT_DRILL_RUNBOOK.md)):

| Action | Commitment |
|---|---|
| Status page | Post to `https://status.lemma.id` within **30 minutes** (investigating → identified → monitoring → resolved) |
| Enterprise email | Notify affected enterprise customers per contract when required |
| Public updates | No exploit details or tenant-specific data in public posts |

## Personal data breaches

When a breach may compromise personal information:

| Audience | Commitment |
|---|---|
| Affected individuals | Notify within **72 hours** via email where feasible |
| Website notice | Post summary on lemma.id when appropriate |
| Controllers (relying sites) | Notify without undue delay per DPA draft §9 |

## Severity ladder (internal)

| Level | Customer notice |
|---|---|
| L1 | Status page if user-visible; no email unless prolonged |
| L2 | Status page + enterprise email if contractually required |
| L3+ | Immediate IC + Security Lead; customer notice within 30 minutes |

## What we communicate

- Impact summary (availability, confidentiality, integrity)
- Affected services and estimated duration
- Remediation status and next update time
- Post-incident summary within 5 business days of resolution (enterprise)

## What we do not communicate publicly

- Active exploit techniques
- Unpatched vulnerability details before remediation
- Per-tenant data unless privately to affected controller

## Contacts

- Security reports: security@lemma.id  
- Privacy / breach: privacy@lemma.id  
- Status: https://status.lemma.id

## Related documents

- [`DPA_DRAFT.md`](DPA_DRAFT.md)
- [`docs/operations/ALERT_CATALOG.md`](../operations/ALERT_CATALOG.md)
- [`docs/operations/INCIDENT_DRILL_RUNBOOK.md`](../operations/INCIDENT_DRILL_RUNBOOK.md)
