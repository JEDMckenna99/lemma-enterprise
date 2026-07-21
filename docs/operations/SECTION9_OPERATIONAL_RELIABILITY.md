# Section 9 Operational Reliability

Production reliability controls for lemma.id human-backed authentication.

## Objectives

| Metric | Target | Validation |
|---|---|---|
| RPO (Recovery Point Objective) | ≤ 15 minutes | Heroku Postgres Continuous Protection / PITR |
| RTO (Recovery Time Objective) | ≤ 60 minutes | Measured restore or fork drill |
| Liveness probe | Process up | `GET /health` — no dependency probes |
| Readiness probe | Dependencies healthy | `GET /ready` — DB, Redis, crypto, revocation freshness |

Only publish SLA numbers that measured drills support. Do not claim uptime beyond monitored evidence.

## Database backups and PITR

Production runs on Heroku Postgres (`lemma-enterprise`).

1. Confirm plan tier supports automated backups:
   ```powershell
   heroku pg:info -a lemma-enterprise
   ```
2. Confirm Continuous Protection (WAL / PITR) is enabled on the primary database.
3. Record plan, backup schedule, and protection status in `ops/evidence/launch/*section9-restore-drill*.md`.

### Restore drill (quarterly + before GA)

Run [`scripts/section9_restore_drill.py`](../../scripts/section9_restore_drill.py) or follow manually:

1. Record primary `DATABASE_URL` app name and current release version.
2. Create a fork or follower restore target (non-destructive):
   ```powershell
   heroku pg:backups:capture -a lemma-enterprise
   heroku pg:backups -a lemma-enterprise
   ```
3. Measure elapsed time from restore start to successful `SELECT 1` on restored database.
4. Compare measured RTO against the ≤ 60 minute objective.
5. Store evidence under `ops/evidence/launch/` with UTC timestamps.

## Migrations

- Release phase: `python migrations/run_migration.py` (Procfile `release:`).
- Advisory lock key: `20260721001` — only one migration runner at a time.
- Checksum drift on applied migrations **fails closed** (no silent skip).

Verify after deploy:

```powershell
heroku releases -a lemma-enterprise -n 3
heroku logs --tail -a lemma-enterprise --dyno release
```

## Health endpoints

| Endpoint | Purpose | Fail behavior |
|---|---|---|
| `GET /health` | Liveness | Always 200 when process serves requests |
| `GET /ready` | Readiness | 503 when DB, Redis, crypto, or stale revocation bloom |

Readiness env vars:

- `LEMMA_REVOCATION_FRESHNESS_MAX_SECONDS` (default `86400`)
- `LEMMA_READY_REQUIRE_BILLING_OUTBOX=1` — fail ready when billing outbox queue age exceeds threshold (default off)

## Workers

| Process | Role |
|---|---|
| `web` | HTTP API |
| `billing_worker` | Stripe meter outbox retries |
| `retention_worker` | Monthly subject-token purge (90d policy) |

Scale after deploy:

```powershell
heroku ps:scale retention_worker=1 -a lemma-enterprise
```

Didit upstream session purge runs on issuance when `LEMMA_ISHUMAN_DIDIT_PURGE=1` (default on).

## Monitoring and alerts

See [`ALERT_CATALOG.md`](ALERT_CATALOG.md) for Sentry and uptime rules.

Customer status page: `https://status.lemma.id` (UptimeRobot public page).

## Drills

| Drill | Script | Frequency |
|---|---|---|
| Prod smoke | `scripts/section9_prod_smoke.py` | Every deploy |
| Dependency fail-closed | `scripts/section9_dependency_drill.py` | Monthly |
| Load baseline | `scripts/section9_load_matrix.py` | Before GA + after major changes |
| Restore / PITR | `scripts/section9_restore_drill.py` | Quarterly |
| Alert routing | `scripts/run_sentry_alert_routing_drill.py` | Monthly |

## Exit criteria evidence

Section 9 is `PASS` when:

1. Measured restore drill meets RPO/RTO objectives.
2. Dependency-failure exercise matches [`DEPENDENCY_OUTAGE_PLAYBOOK.md`](DEPENDENCY_OUTAGE_PLAYBOOK.md).
3. Alerts reach on-call and link to runbooks (Sentry drill evidence).
4. SLA claims in docs match measured capabilities.
