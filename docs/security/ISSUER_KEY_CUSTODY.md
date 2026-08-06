# Issuer key custody — design note

Status: Option C (separate signing app) chosen — implemented 2026-08-06  
Date: 2026-07-28  
Audience: Platform security / operator

## Problem

Lemma platform Ed25519 issuer seeds are KMS-encrypted at rest but decrypted into application memory for signing (`api/kms_manager.py`, `api/issuer_management.py`). Compromise of the app decrypt path equals network-root compromise: an attacker could mint credentials accepted by every relying site until keys are rotated and verifiers refresh trust material.

Sign in with lemma.id increases blast radius because passkey-tier credentials are issued at scale without per-site registration.

## Requirements

1. Signing keys must not be extractable via routine app memory compromise alone (goal: HSM/KMS-bound signing).
2. Rotation must not break relying-site verifiers that cache the signed issuer trust list.
3. Latency for `derive-site-proof` and IDV issuance must stay within current SLO (~hundreds of ms p95, not seconds).
4. Rollback path must exist for failed rotations.

## Options

### A. AWS KMS asymmetric Sign (Ed25519)

Use KMS `Sign` with an ECC/Ed25519 key where the private key never leaves KMS.

| Pros | Cons |
|------|------|
| No seed in app memory | Ed25519 on KMS: confirm regional support + latency profile |
| Uses existing AWS footprint | Per-sign API call cost + RTT |
| IAM policy can scope signing principals | Requires refactor of `issuer_management.py` signing call sites |

**Open question:** Measure p95/p99 for Ed25519 Sign in the production region before committing.

### B. Cloud HSM cluster (PKCS#11)

Dedicated HSM with Ed25519 key generated inside the HSM.

| Pros | Cons |
|------|------|
| Strongest custody story | Ops complexity, cost, HA |
| Keys non-exportable by design | Latency + PKCS#11 integration work |

### C. Hardened signing sidecar

Minimal service (separate VPC/security group) holding decrypt capability; app sends digest-only sign requests over mTLS.

| Pros | Cons |
|------|------|
| Smaller attack surface than monolith | Still a software boundary; not as strong as HSM |
| Can ship incrementally | Another service to deploy/monitor |

## Recommended direction (pending latency data)

1. **Short term (shipped):** Option C — separate `lemma-signing` Heroku app (`signing_app.py`, `Procfile.signing`). Web dynos call `LEMMA_SIGNING_SERVICE_URL` with bearer token; federated seed decrypt stays on the signing app only. See [ENVIRONMENT_CONFIG.md](../operations/ENVIRONMENT_CONFIG.md).
2. **Medium term:** Migrate signing app backend to Option A (KMS Sign) once Ed25519 latency is validated.
3. **Long term:** Option B only if compliance or threat model requires hardware non-exportability.

## Key rotation procedure (all options)

Leverage the signed issuer trust list (`api/issuer_trust_list.py`):

1. Generate new issuer keypair in the chosen custody backend.
2. Publish new issuer DID + pubkey in the trust list bundle; keep old key in `previous_keys` with `not_after` timestamp.
3. Deploy verifiers/SDK trust refresh (default 15 min) — no relying-site action required.
4. Mint credentials only with the new key after `not_before`.
5. Monitor verification failure rate for `untrusted_issuer` / `invalid_signature`.
6. After max credential TTL + refresh window, retire old key from trust list.

Document emergency rollback: re-enable previous key in trust list, disable new key issuance, post incident review.

## Out of scope for this note

- Bloom revocation list custody (separate concern).
- Browser SDK trust embed defaults (`NETWORK_ROOT_PUBKEYS`).
- Customer site API key storage (already hashed).

## Decision log

| Date | Decision | Owner |
|------|----------|-------|
| 2026-08-06 | Option C — separate `lemma-signing` app; web uses `api/federated_signer.py` remote client | Operator |
