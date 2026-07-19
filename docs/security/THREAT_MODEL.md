# Lemma isHuman Threat Model

> Living document. The invariants below are enforced in code and pinned by
> [tests/test_cryptographic_invariants.py](../../tests/test_cryptographic_invariants.py).
> Update this file with each v2 phase.

## 1. Actors and trust assumptions

| Actor              | Description                                                                                  |
| ------------------ | -------------------------------------------------------------------------------------------- |
| Real human (user)  | The person being verified; holds a browser wallet protected by a passkey.                    |
| Wallet             | Browser process + IndexedDB + passkey (PRF-derived at-rest key). See `static/js/lemma-wallet.js`. |
| Relying site       | Customer frontend SDK (`static/js/ishuman-verifier.js`) + backend verifier package.          |
| Lemma.id network   | Credential issuer, trust-list publisher, Bloom snapshot publisher (`api/*.py`).              |
| IDV provider       | Didit (default upstream IDV rail); Stripe Identity retained for legacy document-root recovery only. |
| Adversaries        | See section 3.                                                                               |

## 2. Trust assumptions (things we believe)

- Browser WebCrypto correctly implements Ed25519, SHA-256, HKDF, HMAC.
- Passkey + PRF extension protects the wallet's at-rest encryption key.
- The IDV provider correctly verifies physical identity documents.
- `LEMMA_IDENTITY_ROOT_PEPPER_V*` and `LEMMA_PERSON_ROOT_SALT_V*` are kept secret
  (see [ENVIRONMENT_CONFIG.md](../operations/ENVIRONMENT_CONFIG.md)).
- The issuer's Ed25519 signing key (KMS-backed, `api/issuer_management.py`) is kept secret.
- Target state: clients pin an independently trusted network root that
  authenticates the issuer trust list. Current verifiers do not yet provide
  that independent pin; this is a P0 gap tracked by production-readiness
  Section 4.

## 3. Adversary capabilities and guarantees

### 3.1 Network observer (sees TLS-decrypted lemma.id traffic)
- Can see: PPIDs in transit, credential bodies, revocation events.
- Cannot see: `wallet_secret`, plaintext `person_root`, or browser passkey.
  Optional device transfer can seal root material to an authorized recipient;
  it must never disclose that material to a relying site.

### 3.2 Compromised relying site (RP backend has every byte it receives)
- Can see: the per-site VC + PPID for users at that site.
- Cannot see: PPIDs at other sites, pairwise unlinkability via
  `HMAC(person_root, "lemma.id/site-ppid/v1" + canonical_site)`
  (pinned in `test_ppid_derivation_is_deterministic_and_byte_pinned`).
- Cannot forge VCs (issuer Ed25519 signature required, verified locally).
- Cannot publish network revocation state. A registered site can block or doubt
  its own PPIDs through its authenticated site-policy controls.

### 3.3 Compromised wallet (attacker exfiltrates IndexedDB)
- If passkey not stolen: encrypted data is unreadable (PRF key gated by passkey).
- If passkey also stolen (shared device): attacker can act as the wallet until
  revocation, but cannot mint credentials for a different identity.
- Mitigation: `/api/ishuman/reissue-master` (Phase 1.3) revokes the prior master
  id on reissue, so leaked local master copies cannot be replayed.

### 3.4 Compromised browser / XSS on lemma.id (primary wallet threat)

Same-origin JavaScript during an unlocked session can read `session.walletSecret`,
call `unwrapBundle()` on the daily-unlock envelope, and invoke wallet SDK APIs.
Passkeys and PRF-at-rest encryption do not protect against this class of attack.

**Mitigations (current posture):**

| Control | Effect |
|---------|--------|
| CSP with per-request nonces (no `script-src` `unsafe-inline`) | Blocks most injected script execution |
| 10h encrypted daily-unlock bundle (device wrap key) | Shrinks window vs 24h; not XSS-proof |
| Fail-closed bundle persist when wrap unavailable | No plaintext `walletSecret` in localStorage |
| Wallet auto-init scoped to wallet/developer/admin routes | Marketing XSS cannot restore bundle via `globalLemmaWallet.init()` |
| CSP `report-uri` + Sentry | Detection of policy violations |
| `/api/ishuman/reissue-master` | User response after suspected compromise |

**Residual risk:** XSS on a wallet route during the 10h unlock window still equals
wallet compromise until lock + reissue.

### 3.5 Compromised IDV provider (fooled by a fake document)
- Network mints a credential for a fraudulent identity.
- Mitigated by: multi-issuer triangulation (Didit + legacy Stripe recovery paths) and document-quality monitoring.

### 3.6 Compromised Lemma.id (pepper/salt or issuer key exposed)
- pepper/salt exposure: attacker can compute PPIDs given documents.
  - Privacy guarantee broken; identity continuity unaffected.
  - Mitigation: versioned pepper/salt rotation (Phase 3.1, `LEMMA_ACTIVE_ROOT_VERSION`).
- Issuer key exposure: attacker can mint arbitrary credentials.
  - Trust-list rotation cuts off the old issuer key; clients refetch.
  - Mitigation: multi-issuer trust list (Phase 3.2).

### 3.7 Silent mobile IDV wallet handoff (URL-bearer + mk proof)

During Didit IDV, the source device (PC popup) encrypts the wallet secret and
deposits a one-time relay blob keyed by `handoff_id`. The Didit return URL on
the phone carries `handoff_id` and `mk` (AES key hex). The phone claims the
blob via `POST /api/ishuman/idv-mobile-handoff/claim` with
`handoff_id`, `session_id`, and `mk`.

**Controls (current posture):**

| Control | Effect |
|---------|--------|
| `SHA-256(mk)` fingerprint stored at deposit; `mk` required on claim | `session_id` or `handoff_id` alone cannot fetch the blob |
| Claim bound to in-flight `IsHumanVerification` row (wallet + status + TTL) | Stolen relay from unrelated/expired IDV cannot be claimed |
| One-time Redis delete on successful claim | Replay of the same handoff fails closed |
| AES-GCM AAD `idv_handoff_v1\|handoff_id\|session_id\|wallet_id` | Ciphertext not swappable across handoffs even if `mk` leaks elsewhere |
| Per-IP and per-`handoff_id` rate limits + mk-guess lockout | Slows online guessing within the TTL window |
| Default TTL 300s (`LEMMA_IDV_HANDOFF_TTL_SECONDS`) | Shrinks exposure vs prior 15-minute window |

**Residual risk:** An attacker who captures the **full return URL** (`handoff_id`
+ `mk` + `ishuman_session`) within the TTL can claim **one** wallet onto their
phone/browser. This is intentional for silent UX (no QR / second channel).

**Explicit non-goals:** Does not protect against a compromised phone/browser,
malware with URL visibility, or TLS termination that logs query strings.
Operational mitigation: strip query strings from access logs where possible;
never log `mk` or full return URLs in application logs.

**Emergency rollback:** `LEMMA_IDV_HANDOFF_STRICT_CLAIM=0` restores the legacy
session-only claim path (deprecated, logged).

### 3.8 Leaked wallet identifiers

- **Assets:** wallet sessions, device enrollment, master reissue, site proofs,
  device-transfer material, and revocation authority.
- **Attacker capability:** learns a random `wallet_id` from a client, request,
  log, support artifact, or compromised integration. The attacker can set
  arbitrary HTTP headers outside a browser.
- **Current controls:** wallet IDs contain sufficient random entropy; many
  sensitive issuance routes require wallet assertions.
- **Known gaps (historical):** `init-first-session` and wallet-id-only
  `signal-unlock` converted `wallet_id` plus an Origin check into server-trusted
  session state. Bare `register-signing-key` accepted a self-signature by the
  new key for unbound first devices.
- **Current controls (Section 2 in progress):** first trusted sessions require
  `session-unlock` WebAuthn; first-device enrollment requires
  `device-enroll` WebAuthn registration; additional devices require a one-time
  transfer/recovery grant; cross-device revoke requires fresh WebAuthn from the
  acting device.
- **Required controls:** a wallet ID remains public metadata. First-session and
  device-enrollment authority require verified WebAuthn, an existing authorized
  device assertion, or a completed human-recovery ceremony.
- **Residual risk:** disclosure still enables correlation inside lemma.id logs
  and targeted denial attempts; rate limiting and identifier minimization
  remain required.
- **Owner:** production-readiness Section 2.

### 3.9 Lost devices and compromised passkeys

- **Assets:** encrypted wallet material, device signing keys, passkey
  credentials, account continuity, and recovery authority.
- **Attacker capability:** obtains a locked or unlocked device, a synced
  passkey, or local browser storage. A legitimate user may lose every enrolled
  authenticator.
- **Current controls:** PRF-derived non-extractable AES-GCM storage keys,
  user-verifying WebAuthn, encrypted daily-unlock state, device keys, device
  revocation, QR transfer, and IDV-backed person-root recovery.
- **Known gaps:** authority for adding a new device is not consistently approved
  by an existing device or recovery ceremony. Several recovery paths use email
  or server session state without proving replacement-passkey control.
- **Required controls:** separate ceremonies for first enrollment, additional
  device enrollment, daily unlock, device revocation, and lost-device recovery.
  Recovery atomically consumes one-time state and binds a verified replacement
  passkey to the canonical person.
- **Residual risk:** compromise of an unlocked device or a legitimately synced
  passkey permits actions until containment and revocation. Recovery disputes
  require an emergency suspension path.
- **Owner:** production-readiness Sections 2 and 6.

### 3.10 Account sharing

- **Assets:** the one-verified-human-per-account policy and relying-site trust.
- **Attacker capability:** a verified person voluntarily shares an unlocked
  device, passkey, wallet session, or application account.
- **Current controls:** user-verifying passkeys, optional fresh-passkey action
  attestations, device inventory, site-local blocks, and action-bound stamps.
- **Known gaps:** routine passkey or session success cannot prove that the
  originally verified person personally performed every action.
- **Required controls:** describe isHuman as verified-human enrollment and
  continuity, not continuous human presence. Require fresh passkey and
  action-bound proof for sensitive mutations; let relying sites apply behavior
  and account-sharing policy.
- **Residual risk:** voluntary sharing and coercion cannot be eliminated by
  this protocol.
- **Owner:** product claims plus production-readiness Sections 1 and 11.

### 3.11 Cross-tenant attacks and malicious relying sites

- **Assets:** site-private PPIDs, site policy, audit logs, API keys, domain
  ownership, billing, and administrator permissions.
- **Attacker capability:** controls one legitimate customer, site credential,
  wallet session, or site API key and supplies another site's identifiers.
- **Current controls:** canonical hostname binding, pairwise PPIDs,
  `require_site_ownership` on selected developer routes, and site-scoped block
  storage.
- **Known gaps:** ownership enforcement is not universal. Audit, revocation,
  site registration, and legacy API-key paths can trust caller-supplied site
  identifiers or conflicting stores.
- **Required controls:** every site operation binds authenticated principal,
  canonical hostname, internal ownership record, and requested resource.
  Domain creation requires ownership proof and cannot overwrite an existing
  owner. Database tenant isolation provides a second boundary.
- **Residual risk:** a relying site legitimately sees and controls its own PPID
  policy and can correlate activity inside its own service.
- **Owner:** production-readiness Sections 3 and 7.

### 3.12 Replay and race conditions

- **Assets:** action authorization, recovery tokens, transfer artifacts,
  webhooks, nonce state, and billing events.
- **Attacker capability:** copies a valid request or artifact, submits it
  concurrently, delays it, or replays it against another process.
- **Current controls:** signed action bindings, timestamps, Redis `SET NX`
  patterns, one-time handoff deletes, webhook signatures, and Stripe event
  identifiers.
- **Known gaps:** Node nonce handling does not await Promise-based Redis clients;
  some verifiers consume a nonce before completing signature checks; recovery
  token use is not atomic; not every webhook has a transactional event ledger.
- **Required controls:** validate all signatures and bindings before an atomic
  consume, use durable distributed replay storage, and make recovery, transfer,
  webhook, and billing transitions idempotent.
- **Residual risk:** a distributed store outage denies sensitive mutations by
  design; availability must not be recovered by disabling replay protection.
- **Owner:** production-readiness Sections 5, 6, and 8.

### 3.13 Database, Redis, KMS, IDV, and network outages

- **Assets:** availability, revocation integrity, identity continuity, key
  confidentiality, replay protection, and billing accuracy.
- **Attacker capability:** causes or exploits dependency failure, stale state,
  timeout, partial transaction, or regional network isolation.
- **Current controls:** local-first presentation verification, KMS production
  requirements for person roots and issuer keys, database readiness checks,
  cached signed revocation state, and billing outbox rows.
- **Known gaps:** revocation database errors can produce a newly signed empty
  snapshot; some Redis rate-limit paths degrade; billing dry-run can acknowledge
  undelivered events; readiness does not cover every required dependency.
- **Required controls:** fail closed for authority, revocation, replay,
  recovery, and billing entitlement. Preserve the last trusted snapshot within
  its validity window, return unavailable rather than minting empty state, and
  expose dependency-specific readiness and alerts.
- **Residual risk:** fail-closed behavior reduces availability during outages.
  Published SLOs must account for the required dependencies.
- **Owner:** production-readiness Sections 5, 8, and 9.

### 3.14 Issuer, trust-root, and signing-service compromise

- **Assets:** validity of all credentials, trust lists, revocation snapshots,
  convergence artifacts, and fresh-passkey attestations.
- **Attacker capability:** obtains an issuer private key, controls a signing
  service, or replaces the trust-list distribution response.
- **Current controls:** production KMS boundaries, signed trust lists and Bloom
  snapshots, issuer status and validity windows, and cached local verification.
- **Known gaps:** the trust-list signing key is delivered inside the same
  response it authenticates; Node does not verify the trust-list signature.
  Issuer-to-site authorization and emergency rotation evidence are incomplete.
- **Required controls:** independently pin an offline/network root, bind issuers
  to allowed credential classes and sites, support overlapping root and issuer
  rotation, and maintain an emergency reissue and revocation procedure.
- **Residual risk:** compromise of an online issuer remains catastrophic until
  trust distribution updates propagate. Short validity, monitoring, and
  compartmentalized issuers reduce the blast radius.
- **Owner:** production-readiness Sections 4, 5, and 9.

## 4. Failure modes

| Behavior                                   | Fails ...  | Rationale                                                        |
| ------------------------------------------ | ---------- | ---------------------------------------------------------------- |
| Bloom/trust-list fetch unavailable         | closed     | Verifier requires a trusted Bloom + trust list before asserting human. |
| Site-binding mismatch on issued credential | closed     | Per site-identity guardrails, never coerce mismatched bindings. |
| Unverified wallet requests site proof      | closed     | `derive-site-proof` returns `wallet_not_verified` (Phase 1.2).   |
| Stale `master_credential_id` hint          | open (graceful) | Falls back to the wallet's latest verified record (Phase 1.2). |
| Redis rate-limiter unavailable             | open (memory fallback) | In-process fixed-window limiting; `fail_open` only if configured. |
| Reissue beyond per-day cap                 | closed     | `reissue_rate_limited` 429 (Phase 1.3).                          |
| Mobile IDV handoff claim without `mk` proof | closed     | `handoff_id_session_id_mk_required` 400 / `handoff_mk_mismatch` 403. |
| Mobile IDV handoff claim with wrong session | closed     | `handoff_session_invalid` 403, blob not consumed.               |
| Revocation database unavailable            | **target: closed** | Return unavailable; never sign a fresh empty snapshot. Current implementation gap is tracked in Section 5. |
| Distributed nonce store unavailable        | closed     | Sensitive action cannot proceed without durable replay protection. |
| KMS unavailable for production signing/root access | closed | Do not generate replacement trust material implicitly. |
| IDV provider unavailable                   | closed for new/step-up IDV | Existing locally verifiable credentials remain subject to expiry and revocation policy. |
| Billing meter unavailable                  | pending, not acknowledged | Persist the event for retry and block when entitlement cannot be established. |
| Tenant ownership lookup unavailable        | closed     | Do not infer ownership from caller-supplied `site_id`. |

## 5. Things this design does NOT protect against

- Coerced IDV (identity verification under duress).
- Government-mandated key escrow.
- Side-channel attacks on the browser.
- Physical compromise of a device with an unlocked wallet.
