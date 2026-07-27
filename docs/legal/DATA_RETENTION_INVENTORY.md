# Data Retention Inventory (Draft)

**Status:** Draft pending counsel review  
**Last updated:** 2026-07-27  
**Automation:** `retention/retention_worker.py`, `billing/credential_billing.py`

| Data class | Storage | Default retention | Deletion mechanism | Owner |
|---|---|---|---|---|
| Site credential (issued) | Wallet (primary); issuance linkage metadata on server | 30 days (credential expiry) | Expiry + retention jobs | Platform |
| Monthly billing subject token | Postgres `ishuman_site_monthly_usage` | 90 days | `purge_monthly_subject_usage()` via retention worker | Billing |
| Lifetime billing subject token | Postgres `ishuman_site_billing_subjects` | Until site/customer deletion | Customer/site deletion workflow | Billing |
| Site/month usage aggregates | Postgres `ishuman_site_usage_aggregates` | Billing retention period | Customer/site deletion | Billing |
| Assigned person root | Postgres (KMS ciphertext `kms1:`) | Until erasure / account deletion | `POST /api/ishuman/erase`, site deletion | Platform |
| Site block | Postgres `site_blocks` | Until authenticated site unblock | Site admin API | Platform |
| Site doubt | Postgres `site_doubts` | Until clear or matching fresh IDV | Automatic on successful fresh IDV | Platform |
| Developer account | Postgres `sites`, `site_admins`, customer records | While account active | Account deletion request | Platform |
| API keys (verification) | Postgres (hash only) | Until revoked/deleted | Key revoke API | Platform |
| OAuth client secrets | Postgres (KMS encrypted) | Until rotated/deleted | Key rotation workflow | Platform |
| Audit logs | Postgres (site-scoped) | Tier-dependent: 30d / 90d / 1y / 7y | Tier expiry + retention policy | Platform |
| Stripe billing events | Stripe + outbox rows | Stripe retention + internal outbox lifecycle | Reconciliation / dead-letter | Billing |
| Revocation bloom snapshots | Postgres + CDN cache | Rolling snapshots with seq numbers | Superseded by newer snapshots | Platform |
| Redis nonces / sessions | Redis | TTL-bound (minutes to hours) | Automatic expiry | Platform |
| Error telemetry | Sentry | Per Sentry project retention | Sentry project settings | Ops |
| IDV provider artifacts | Didit (third party) | Provider policy | Provider deletion; Lemma does not retain raw docs | IDV |

## Retention worker

The `retention_worker` dyno runs on a configurable interval
(`LEMMA_RETENTION_WORKER_SLEEP_SECONDS`, default 3600) and purges eligible
monthly subject usage rows.

Didit-specific purge is gated by `LEMMA_ISHUMAN_DIDIT_PURGE_ENABLED`.

## Post-deletion

After account deletion, Lemma targets removal within **30 days** except where
legal retention requires longer storage (see privacy policy audit tiers).

## Related documents

- [`DATA_FLOW_INVENTORY.md`](DATA_FLOW_INVENTORY.md)
- [`DELETION_EXPORT_PROCEDURES.md`](DELETION_EXPORT_PROCEDURES.md)
- [`../architecture/PRIVACY_ARCHITECTURE.md`](../architecture/PRIVACY_ARCHITECTURE.md)
