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
- Network-trusted issuer DIDs are pinned in clients via the signed trust list.

## 3. Adversary capabilities and guarantees

### 3.1 Network observer (sees TLS-decrypted lemma.id traffic)
- Can see: PPIDs in transit, credential bodies, revocation events.
- Cannot see: `wallet_secret`, `person_root` (server-side only, never leaves), browser passkey.

### 3.2 Compromised relying site (RP backend has every byte it receives)
- Can see: the per-site VC + PPID for users at that site.
- Cannot see: PPIDs at other sites, pairwise unlinkability via
  `HMAC(person_root, "lemma.id/site-ppid/v1" + canonical_site)`
  (pinned in `test_ppid_derivation_is_deterministic_and_byte_pinned`).
- Cannot forge VCs (issuer Ed25519 signature required, verified locally).
- Cannot revoke (Lemma controls the Bloom snapshot).

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

## 5. Things this design does NOT protect against

- Coerced IDV (identity verification under duress).
- Government-mandated key escrow.
- Side-channel attacks on the browser.
- Physical compromise of a device with an unlocked wallet.
