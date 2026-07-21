# Dependency Outage Playbook

Fail-closed and degraded behavior when lemma.id dependencies are unavailable.
Aligns with [`THREAT_MODEL.md`](../security/THREAT_MODEL.md) §3.13 and production-readiness Section 9.

## Summary matrix

| Dependency | User-visible behavior | Readiness | Verification / auth |
|---|---|---|---|
| PostgreSQL | 503 on DB-backed routes; `/ready` not ready | Fail | Fail closed — no issuance, recovery, billing writes |
| Redis | Nonce/replay store unavailable; rate limits may degrade | Fail if ping fails | Sensitive mutations fail closed (no in-memory fallback in prod) |
| KMS | Credential signing unavailable | Crypto check may pass; signing routes fail | Issuance fails closed |
| IDV provider (Didit) | IDV start/callback errors | N/A (external) | New human verification blocked; existing credentials still verify locally |
| Revocation Bloom | Stale or uninitialized bloom | Fail when stale/uninitialized | Verifiers return `unavailable` / 503 bloom-filter |
| Stripe / billing outbox | Meter reporting delayed | Informational unless `LEMMA_READY_REQUIRE_BILLING_OUTBOX=1` | Issuance may continue when enforcement off; outbox stays pending |

## PostgreSQL outage

**Detection:** `/ready` `checks.database.ok=false`; Sentry DB errors; Heroku Postgres alerts.

**Response:**

1. Confirm Heroku Postgres status and connection limits.
2. If primary unavailable, initiate restore/failover per [`SECTION9_OPERATIONAL_RELIABILITY.md`](SECTION9_OPERATIONAL_RELIABILITY.md).
3. Do not disable checksum or migration guards to “fix” schema drift.

**Expected:** No cross-tenant data exposure; fail closed on all authority mutations.

## Redis outage

**Detection:** `/ready` `checks.redis.ok=false`; replay/nonce errors; revocation pub/sub local-only mode.

**Response:**

1. Check `REDIS_URL` / `REDISCLOUD_URL` and connection cap (`LEMMA_REDIS_MAX_CONNECTIONS`).
2. Restart web dynos after Redis recovery to re-establish pub/sub listeners.

**Expected:** Action stamps and recovery tokens fail closed when durable store required.

## KMS outage

**Detection:** Issuance/signing 5xx; CloudTrail/KMS CloudWatch alarms.

**Response:**

1. Verify `LEMMA_KMS_KEY_ID`, `AWS_REGION`, and IAM policy (`scripts/verify_kms_policy.py`).
2. Do not fall back to local signing keys in production.

**Expected:** No unsigned credentials issued.

## IDV provider outage

**Detection:** Didit callback failures; IDV start errors; elevated 4xx/5xx on IDV routes.

**Response:**

1. Check Didit status page and webhook delivery.
2. Communicate signup/verification delay on status page if user-facing impact.

**Expected:** Existing passkey + presentation verification continues for already-issued credentials.

## Revocation infrastructure outage

**Detection:** `/ready` revocation stale; bloom-filter 503; `revocation_data_untrusted` errors.

**Response:**

1. Confirm DB `revocation_list` readable.
2. Restart web dynos to force bloom resync.
3. Never serve empty signed snapshot after DB/hash errors (Section 5).

**Expected:** Verification fails closed when revocation state unavailable.

## Billing / Stripe outage

**Detection:** Outbox queue age warnings; `billing_outbox_queue_age_seconds` logs; Stripe status.

**Response:**

1. Confirm `billing_worker` dyno running.
2. Run `scripts/reconcile_billing.py` after recovery.
3. Do not mark dry-run/skipped events as reported.

**Expected:** Usage remains in outbox `pending` until Stripe accepts idempotent meter events.

## Regional / provider-wide outage

1. Incident Commander declares severity per [`INCIDENT_DRILL_RUNBOOK.md`](INCIDENT_DRILL_RUNBOOK.md).
2. Post initial + updates on `https://status.lemma.id`.
3. Preserve fail-closed posture — do not bypass human-auth or replay controls for availability.

## Validation

Run [`scripts/section9_dependency_drill.py`](../../scripts/section9_dependency_drill.py) against production (read-only checks) or staging to confirm endpoint behavior matches this matrix.
