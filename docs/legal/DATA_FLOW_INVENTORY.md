# Data Flow Inventory (Draft)

**Status:** Draft pending counsel review  
**Last updated:** 2026-07-27  
**Engineering source:** `docs/architecture/PRIVACY_ARCHITECTURE.md`

This document describes personal and pseudonymous data flows for enterprise
buyers. It is not legal advice.

## Roles

| Party | Role | Typical data |
|---|---|---|
| End user | Data subject | Passkey, wallet, IDV outcome (transient) |
| Relying site | Controller (for their users) | Site-private PPID, signed presentations |
| Lemma.id | Processor (for relying sites) / Controller (for developer accounts) | Issuance metadata, billing tokens, audit logs |

## Flow 1: Developer / site registration

```text
Developer → lemma.id (email, company, domain) → Postgres (sites, site_admins)
Payment → Stripe (PCI handled by Stripe; Lemma stores customer ID only)
Domain ownership → DNS or /.well-known/ challenge → verified flag on site row
```

## Flow 2: isHuman identity verification (IDV)

```text
User browser → Didit IDV (document/liveness; provider-hosted)
Didit callback → lemma.id (verification outcome, not raw document images)
lemma.id → transient processing of document number, jurisdiction, DOB
         → AWS KMS encrypt assigned person root (kms1: ciphertext only)
         → discard raw IDV artifacts (not persisted in isHuman path)
```

**Lemma does not persist:** document images, selfie/liveness images, legal name.

## Flow 3: Credential issuance and site PPID

```text
Wallet (passkey) → derive-site-proof → lemma.id issuance API
lemma.id → HMAC(assigned_person_root, site hostname) → site-private PPID
         → KMS-signed site credential → returned to wallet
Postgres → keyed HMAC billing subject token (not raw PPID in billing tables)
```

Relying sites receive only their site-private PPID and signed credential.

## Flow 4: Presentation verification (relying site)

```text
User browser → signed presentation → relying site backend
Relying site → local verifier (Python/Node/Browser SDK)
             → optional POST /api/ishuman/verify-presentation (Lemma API)
```

Routine return-visit verification can run entirely on the relying site without
per-request calls to Lemma.

## Flow 5: Revocation and enforcement

```text
Site admin → block/doubt/revoke APIs (API key + site ownership)
lemma.id → bloom-filter snapshot + Redis nonce store
Verifiers → check revocation candidates (credential ID, PPID hash, wallet ID)
```

## Flow 6: Recovery

```text
User → IDV (lost device / account recovery purpose) → bound to initiating wallet
     → replacement passkey enrollment → new device authority
Developer recovery → email token + replacement passkey PPID (atomic consume)
```

## Flow 7: Billing

```text
Issuance event → billing outbox → Stripe meter (event ID, site, month, count)
Stripe payloads contain no PPID, wallet ID, person ID, or credential ID
```

## Flow 8: Audit and operations

```text
Security events → audit logs (site-scoped, tiered retention)
Errors → Sentry (anonymized stack traces)
Infrastructure → Heroku/AWS logs (request metadata)
```

## Cross-border transfers

Subprocessor locations are listed in [`SUBPROCESSORS.md`](SUBPROCESSORS.md).
Enterprise DPAs may require SCCs or equivalent mechanisms.

## Related documents

- [`DATA_RETENTION_INVENTORY.md`](DATA_RETENTION_INVENTORY.md)
- [`DPA_DRAFT.md`](DPA_DRAFT.md)
- [`../architecture/PRIVACY_ARCHITECTURE.md`](../architecture/PRIVACY_ARCHITECTURE.md)
