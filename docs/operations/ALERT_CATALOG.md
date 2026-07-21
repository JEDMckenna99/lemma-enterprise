# Alert Catalog

Operator alerts for lemma.id Section 9 operational reliability.
Each alert must link to a runbook section and reach the on-call operator.

## On-call escalation

| Level | Trigger | Action | Runbook |
|---|---|---|---|
| L1 | UptimeRobot `/health` down 5m | Page primary on-call | [INCIDENT_DRILL_RUNBOOK.md](INCIDENT_DRILL_RUNBOOK.md) |
| L2 | `/ready` failing > 10m | Page + IC assignment | [DEPENDENCY_OUTAGE_PLAYBOOK.md](DEPENDENCY_OUTAGE_PLAYBOOK.md) |
| L3 | Auth/issuance error rate spike | Sentry critical → Slack/email | [INCIDENT_DRILL_RUNBOOK.md](INCIDENT_DRILL_RUNBOOK.md) Scenario A |
| L4 | Customer data / security event | IC + comms lead | Customer notification template below |

Primary on-call rotation: platform operator (update roster in secure ops store).

## Uptime monitors (UptimeRobot → status.lemma.id)

| Monitor | URL | Interval | Alert after |
|---|---|---|---|
| Liveness | `https://lemma.id/health` | 5 min | 1 failure |
| Readiness | `https://lemma.id/ready` | 5 min | 2 consecutive failures |
| Bloom filter | `https://lemma.id/api/revocation/bloom-filter` | 15 min | 1 failure |

Public status page: `https://status.lemma.id`

## Sentry alert rules

Configure in Sentry project `lemma-enterprise` (see [`monitoring/SENTRY_SETUP_GUIDE.md`](../../monitoring/SENTRY_SETUP_GUIDE.md)):

| Domain | Condition | Severity | Runbook |
|---|---|---|---|
| Authentication | Wallet/session 5xx rate > baseline | High | INCIDENT § Scenario A |
| Issuance | KMS/signing failures | Critical | DEPENDENCY § KMS |
| IDV | Didit callback errors spike | High | DEPENDENCY § IDV |
| Recovery | Recovery complete failures | High | Section 6 recovery docs |
| Revocation | bloom-filter 503 or stale freshness log | Critical | DEPENDENCY § Revocation |
| Database | Postgres connection errors | Critical | DEPENDENCY § PostgreSQL |
| Redis | Redis connection / nonce errors | High | DEPENDENCY § Redis |
| Billing | `billing_outbox_queue_age_seconds` log pattern | Warning | Section 8 billing runbook |
| Revocation freshness | `revocation_freshness_stale` log pattern | Warning | DEPENDENCY § Revocation |

Validate routing monthly:

```powershell
python scripts/run_sentry_alert_routing_drill.py
```

Store output under `ops/evidence/launch/*sentry-alert-drill*.md`.

## Structured log signals (Heroku log drain → Sentry)

| Log pattern | Meaning |
|---|---|
| `billing_outbox_queue_age_seconds=` | Billing outbox backlog |
| `revocation_freshness_stale` | Bloom snapshot older than max age |
| `Revocation readiness check failed` | Bloom not initialized |
| `Migration checksum drift` | Release phase blocked — do not force deploy |

## Customer incident notification template

Subject: `[lemma.id] Service incident — {short_title}`

```
We are investigating an issue affecting {impact_summary}.

Status: {investigating|identified|monitoring|resolved}
Started (UTC): {start_time}
Current impact: {user_visible_impact}

Updates: https://status.lemma.id

Contact: support@lemma.id
```

Post within 30 minutes of L2+ customer-visible impact. Resolve follow-up within 24 hours.

## Audit records

Durable audit logs: `audit_logs` table via `api/audit_logger.py`.
Retention per [`PRIVACY_ARCHITECTURE.md`](../architecture/PRIVACY_ARCHITECTURE.md).

Centralized metrics: Sentry performance + request telemetry (`monitoring/request_telemetry.py`).
Admin SLO snapshot: `/api/admin/platform-stats` (operator auth required).
