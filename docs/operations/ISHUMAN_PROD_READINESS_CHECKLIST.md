# isHuman Production Readiness Checklist

## Before maintenance

- [ ] Snapshot Postgres and Redis.
- [ ] Confirm AWS KMS, region, Heroku AWS credentials, `LEMMA_KMS_KEY_ID`,
  column-encryption key, PPID root key, and MAU HMAC key are configured.
- [ ] Put issuance and billing into maintenance mode.
- [ ] Record dry-run output from `scripts/privacy_minimized_ishuman_cutover.py`.

## Schema and backfill

- [ ] Apply migration 038.
- [ ] Backfill lifetime site tokens from legacy derived rows using earliest
  creation time.
- [ ] Import current-month Redis MAU tokens.
- [ ] KMS-encrypt every assigned person root and verify round-trip decryption.
- [ ] Verify no plaintext, legacy-column, or invalid KMS root remains.
- [ ] Run the cutover script again and confirm idempotent zero-create counts.

## Identity continuity

- [ ] Existing and recovered users derive byte-identical PPIDs.
- [ ] Same-document recovery, new-document attachment, document expiry, QR
  transfer, and master reissue pass.
- [ ] Renewal preserves PPID and issues a fresh random credential ID.
- [ ] No runtime issuance path reads or writes `derived_credentials`.

## Billing

- [ ] Concurrent first issuance creates one lifetime site billing subject and one $0.50
  initial event.
- [ ] Concurrent later-month renewal creates one monthly row and one $0.03 MAU
  event.
- [ ] Current-month Redis import prevents duplicate billing.
- [ ] A matching active doubt plus successful fresh IDV bills one $0.33
  doubt-reentry event.
- [ ] Stripe payload contains only random event ID, customer/site billing
  identity, month, event type, and unit count.
- [ ] Monthly subject rows purge after 90 days; lifetime tokens remain.
- [ ] Postgres remains authoritative when Redis is unavailable.

## Site enforcement

- [ ] Site block survives fresh IDV, recovery, document renewal, and credential
  rotation.
- [ ] `site_blocked` never opens a recovery popup.
- [ ] Only authenticated site-unblock removes a block.
- [ ] Site doubt is reported separately as `doubt_required`.
- [ ] `verifyFreshForBackend()` clears only a matching doubt for the same PPID.
- [ ] Mismatched PPID and doubts on other sites remain active.
- [ ] Customer, admin approval, trust queue, and demo network-revoke endpoints
  return HTTP 410 `network_revocation_retired`.

## Migration evidence

- [ ] V2 evidence is signed, stateless, site-scoped, and contains no wallet ID
  or global merge ID.
- [ ] Tampering, expiry, PPID mismatch, and site mismatch fail closed.
- [ ] Unexpired v1 evidence verifies during the compatibility window only.

## KMS boundary

- [ ] Encryption context mismatch fails.
- [ ] KMS unavailability fails closed in production.
- [ ] No plaintext person root is stored or cached across requests.
- [ ] CloudTrail context contains only the opaque person HMAC.

## Test and smoke acceptance

- [ ] Run complete isHuman, billing, recovery, revocation, migration,
  browser-signature, and environment-parity suites.
- [ ] New human issuance succeeds.
- [ ] Returning monthly renewal succeeds.
- [ ] Backend presentation verification succeeds locally.
- [ ] Site doubt, fresh IDV, same PPID, and doubt clear succeeds.
- [ ] Site block followed by fresh-IDV attempt remains blocked.
- [ ] Lost-device same-document recovery produces the same PPID.
- [ ] Billing event inspection confirms aggregate-safe fields only.

## Destructive cleanup

- [ ] Complete all smoke checks while maintenance mode remains active.
- [ ] Apply migration 039 to drop `derived_credentials`, `person_merges`, and
  `ppid_migration_issued`.
- [ ] Re-run smoke checks, then leave maintenance mode.
- [ ] Archive snapshots and verification reports under the incident-controlled
  deployment evidence location.
