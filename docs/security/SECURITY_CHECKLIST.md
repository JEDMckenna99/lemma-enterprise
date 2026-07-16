# Lemma Security Checklist

> Control inventory for **lemma.id production** (one Heroku app, multiple product
> surfaces). For GA gate decisions use
> [`docs/status/GA_GATE_STATUS.md`](../status/GA_GATE_STATUS.md).

## Product scope (read this first)

Lemma.id is **not one product**. This checklist mixes controls for three surfaces
that share `lemma-wallet.js` and passkey infrastructure:

| Surface | What it is | Typical routes / flows | Dedicated docs |
|---------|------------|------------------------|----------------|
| **Platform login & IAM** | Developer/admin login, passkey unlock, permissions, API keys, agent control plane | `/unlock`, `/platform`, `/register`, `developer_access` proofs | [`IAM_ONLY_INTEGRATION_GUIDE.md`](../integration/IAM_ONLY_INTEGRATION_GUIDE.md) |
| **isHuman (proof of humanity)** | IDV + site proofs for relying sites; verifier SDK on customer origins | `/wallet/ishuman-idv`, `/api/ishuman/*`, `ishuman-verifier.js` | [`THREAT_MODEL.md`](THREAT_MODEL.md), [`ISHUMAN_LOCAL_FIRST_IMPLEMENTATION_OUTLINE.md`](ISHUMAN_LOCAL_FIRST_IMPLEMENTATION_OUTLINE.md) |
| **Shared wallet crypto** | IndexedDB, PRF at-rest encryption, revocation bloom, device link | `lemma-wallet.js`, `/link`, `/api/v1/revocation/*` | [`ARCHITECTURE_WALLET_FIRST.md`](../architecture/ARCHITECTURE_WALLET_FIRST.md) |

**What the 2026-06 hardening program mostly targeted**

- **Platform / login:** route-scoped CSP on `/unlock`, admin/developer template XSS, legacy redirect 410s, GA smoke gates.
- **isHuman-specific:** `ishuman_cache` encryption, isHuman API `wallet_secret` rejection, lock-period bundle hardening.
- **Shared:** wallet at-rest crypto, revocation list/bloom, CSP reporting.

**Common confusion:** `scripts/revoke_to_deny_smoke.py` exercises the **platform
control plane** (issue `developer_access` proof → revoke → deny), not a relying-site
isHuman site-proof flow. The `ppid_not_linked` error means the session-link wallet
has not completed **lemma.id platform login/unlock** to bind a network PPID, that is
not the same as a user completing isHuman IDV on a customer site.

For isHuman-only assurance, also run relying-site E2E (verifier SDK + IDV popup +
derive-site-proof) and track separately from platform login sign-off.

## Status Legend

- `PASS`: verified with current production and/or automated test evidence.
- `IN_PROGRESS`: partially verified; operator or E2E evidence still required.
- `UNKNOWN`: not validated with sufficient evidence.
- `FAIL`: validated and not meeting the control requirement.
- `N/A`: control removed or not applicable to current architecture.

## Current Verification Snapshot (2026-06-08)

- **Environment:** production `https://lemma.id` (Heroku app `lemma-enterprise`)
- **Release:** v2186 · commit `78d52f68` (security hardening deploy)
- **Architecture:** popup-first wallet (Phase 2.1, `/wallet/bridge` iframe **removed**)
- **Primary evidence (local, gitignored):**
  - `ops/evidence/launch/2026-06-08-security-hardening-deploy-summary.md`
  - `ops/evidence/launch/2026-06-08-213645-post-deploy-summary.md`
  - `ops/evidence/launch/2026-06-08-incident-drill-csp-alert.md`
  - `ops/evidence/launch/2026-03-18-212437-revoke-to-deny-evidence.md` (historical deny-path PASS)
- **Automated guards:** `tests/test_csp_security.py`, `tests/test_ishuman_cache_encryption.py`,
  `tests/test_xss_wallet_hardening.py`, `tests/test_wallet_bridge_origin_enforcement.py`,
  `.github/workflows/auth-launch-gate.yml`
- **Note:** This snapshot does not replace manual browser E2E, external pentest, or formal sign-off.

### Summary counts (this snapshot)

| Status | Count | Meaning |
|--------|------:|---------|
| PASS | 24 | Code + smoke and/or prod probe verified |
| IN_PROGRESS | 25 | Implemented; needs E2E, matrix, or operator run |
| UNKNOWN | 9 | Not yet tested; evidence not recorded |
| FAIL | 0 | No open validated failures |
| N/A | 2 | Retired or not applicable (bridge era, React N/A) |

---

## Transport Security

| Check | Status | Notes |
|-------|--------|-------|
| HTTPS enforced for all production traffic | PASS | `http://lemma.id` → 301 HTTPS (2026-02-11 + v2186 smoke) |
| TLS 1.2+ only | PASS | TLS 1.1 fails, TLS 1.2 succeeds (`post_deploy_launch_gate` transport checks) |
| HSTS header enabled | PASS | `Strict-Transport-Security` on production root |
| Certificate pinning (mobile) | UNKNOWN | Optional; no mobile app policy artifact |

---

## Cross-Origin Security (popup-first, no bridge)

| Check | Status | Notes |
|-------|--------|-------|
| Legacy `/wallet/bridge` iframe removed | N/A | Route, template, and audit endpoint removed Phase 2.1; `tests/test_wallet_bridge_origin_enforcement.py` |
| Wallet verification uses popup flow | IN_PROGRESS | Code path popup-only; full cross-browser E2E capture pending |
| postMessage uses exact origin match | PASS | `isLemmaTrustedOrigin()`, no `.includes('lemma.id')` substring bypass |
| `enc_key` omitted from redirect unlock URL | PASS | `unlockWithRedirect` has no enc_key param; regression test pinned |
| Legacy redirect tokens return 410 | PASS | `POST /api/wallet/create-redirect-token` and `exchange-redirect-token` → 410 on prod |
| No sensitive data in URL params | IN_PROGRESS | enc_key removed; device-link QR and other flows need targeted audit capture |

### Verification (current pattern)

```javascript
// Exact origin, do NOT use origin.includes('lemma.id')
window.addEventListener('message', (event) => {
    if (!isLemmaTrustedOrigin(event.origin)) {
        return;
    }
    // Process message...
});
```

---

## XSS on lemma.id (primary wallet threat)

| Check | Status | Notes |
|-------|--------|-------|
| Route-scoped CSP (strict default) | PASS | `/` = self+nonce only; `/unlock` + Stripe/Turnstile; `/link` + unpkg; prod curl v2186 |
| CSP blocks inline scripts without nonce | PASS | No `unsafe-inline`/`unsafe-eval` in `script-src`; `tests/test_csp_security.py` |
| CSP violation reporting | PASS | `report-uri` + `POST /api/security/csp-report` → 204; drill `2026-06-08-incident-drill-csp-alert.md` |
| Daily unlock bundle TTL capped at 10h | PASS | `DEFAULT_SESSION_HOURS = MAX_SESSION_HOURS = 10`; `tests/test_xss_wallet_hardening.py` |
| Bundle fail-closed on wrap failure | PASS | `_persistIsHumanLockBundle`, no plaintext `walletSecret` fallback |
| `ishuman_cache` encrypted at rest (**isHuman**) | PASS | `SENSITIVE_STORES` + `WALLET_DB_VERSION = 7`; `tests/test_ishuman_cache_encryption.py`; bundle v2545 prod |
| Wallet auto-init scoped to app routes | PASS | Public index empty block; developer/admin/wallet routes opt in; `tests/test_xss_wallet_hardening.py` |
| Debug panel gated in production | PASS | `LEMMA_WALLET_DEBUG` server flag required |
| Compromise response documented | PASS | `docs/security/WALLET_COMPROMISE_RESPONSE.md` (thresholds + escalation) |
| Residual XSS during unlock window | IN_PROGRESS | Same-origin JS during 10h unlock can read `session.walletSecret`; documented accepted risk |

---

## Credential Storage

| Check | Status | Notes |
|-------|--------|-------|
| Credentials stored in IndexedDB | PASS | `LemmaWallet` DB; envelope encryption for sensitive stores |
| PRF-derived at-rest key for sensitive stores | PASS | `wallet-at-rest-crypto.js`; migration via `_migratePlaintextStores` |
| Wallet secret never exposed to server (design) | IN_PROGRESS | Server paths reject `wallet_secret` on isHuman APIs (410); full network trace audit pending |
| Session expiry enforced | IN_PROGRESS | API guardrails present; full client lifecycle E2E pending |
| Passkey required for unlock | IN_PROGRESS | Endpoints live; browser matrix evidence pending |

---

## Passkey Security

| Check | Status | Notes |
|-------|--------|-------|
| `userVerification: 'required'` for unlock | IN_PROGRESS | Enforced in server challenge options; Chrome/Firefox/Safari matrix pending |
| `userVerification: 'discouraged'` for extend | IN_PROGRESS | Documented session model; runtime capture pending |
| Credential bound to RP ID `lemma.id` | PASS | `rpId` in passkey challenge responses (smoke + code) |
| No passkey export capability | UNKNOWN | Authenticator/platform dependent; policy evidence not captured |

---

## Signature Verification

| Check | Status | Notes |
|-------|--------|-------|
| Ed25519 verification enabled | IN_PROGRESS | WASM + `lemma-keys.js` async signing; black-box negative tests pending |
| Issuer public key validated | IN_PROGRESS | Trust list + verifier paths exist; dedicated artifact pending |
| Signature checked before trust | IN_PROGRESS | Verification-first in SDK; E2E negative test capture pending |
| Expired credentials rejected | UNKNOWN | Dedicated expiry test evidence not recorded |

---

## Revocation Checking

| Check | Status | Notes |
|-------|--------|-------|
| Revocation list endpoint healthy | PASS | `GET /api/v1/revocation/list` 200 on v2186 smoke |
| Bloom filter endpoint healthy | PASS | `GET /api/revocation/bloom-filter` 200 on v2186 smoke |
| Revoke → deny propagation | IN_PROGRESS | Historical PASS `2026-03-18-212437-revoke-to-deny-evidence.md`; v2186 list/bloom smoke blocked `ppid_not_linked` |
| Bloom sync on site revoke | PASS | Unit coverage `tests/test_wallet_site_revocation.py` |
| Stale revocation data flagged | UNKNOWN | Stale-cache scenario test not recorded |
| Bloom verifier fail-open at startup | IN_PROGRESS | Documented in `api/revocation_verifier.py`; no startup gate yet |

---

## Session Management

| Check | Status | Notes |
|-------|--------|-------|
| Session stored in IndexedDB (encrypted) | PASS | `session` in `SENSITIVE_STORES` |
| Session bound to wallet | IN_PROGRESS | APIs require authenticated context; full proof path pending |
| Max extension limit (7) | IN_PROGRESS | Documented; runtime validation pending |
| Extension requires user presence | IN_PROGRESS | Design enforces presence; passkey prompt evidence pending |

---

## Privacy Protection

| Check | Status | Notes |
|-------|--------|-------|
| PPID used for user identification | PASS | Architecture + server enforcement; see `PRIVACY_ARCHITECTURE.md` |
| No cross-site tracking possible | UNKNOWN | Adversarial correlation test not recorded |
| Wallet secret not sent to server (runtime proof) | IN_PROGRESS | Legacy paths removed/410; HAR/trace across all flows pending |
| Credentials filtered by site | IN_PROGRESS | Site-scoped controls in code; cross-site denial E2E pending |

---

## Content Security Policy (lemma.id route profiles)

Implemented in `app.py` → `build_content_security_policy()`. See
[`THIRD_PARTY_SCRIPTS.md`](THIRD_PARTY_SCRIPTS.md).

| Profile | Routes | Extra `script-src` |
|---------|--------|-------------------|
| `strict` | Default (e.g. `/`, `/dashboard`) | none |
| `unlock_idv` | `/unlock`, `/wallet/unlock` (**platform login**); `/wallet/popup`, `/wallet/ishuman-idv` (**isHuman**) | Stripe, Cloudflare Turnstile |
| `link_qr` | `/link`, `/wallet/link` | above + `unpkg.com` (html5-qrcode) |

Removed from global policy: `static.cloudflareinsights.com`, `cdn.jsdelivr.net` (unused in layouts).

---

## Service Worker Security

| Check | Status | Notes |
|-------|--------|-------|
| SW only registered on lemma.id | IN_PROGRESS | `static/sw.js` exists; production registration artifact pending |
| Cache-first for static assets | IN_PROGRESS | SW present; full mode test pending |
| Network-first for sensitive data | UNKNOWN | Explicit request policy verification pending |
| SW scope properly restricted | UNKNOWN | Header/scope validation artifact pending |

---

## Error Handling

| Check | Status | Notes |
|-------|--------|-------|
| No sensitive data in error messages | IN_PROGRESS | Basic API responses reviewed; full corpus audit pending |
| Auth failures don't reveal user existence | IN_PROGRESS | Generic denial on unauthenticated paths |
| Console logs disabled in production | UNKNOWN | Built artifact + runtime console audit pending |
| Error boundaries in React | N/A | Lemma.id is server-rendered templates, not a React SPA |

---

## Input Validation & Template XSS

| Check | Status | Notes |
|-------|--------|-------|
| Credential data validated before use | IN_PROGRESS | Key API paths validated; comprehensive coverage pending |
| Origin validated on credentialed CORS | IN_PROGRESS | Disallowed origin POST has no ACAO; preflight review pending |
| High-risk innerHTML surfaces escaped | PASS | `register.html`, `admin/health.html`, admin/dev layout toasts (v2186) |
| Remaining innerHTML in admin/developer | IN_PROGRESS | `developer/platform.html` and others not fully audited |
| Claims sanitized before display | UNKNOWN | UI rendering audit pending |

---

## Device Linking (residual exposure)

| Check | Status | Notes |
|-------|--------|-------|
| QR device link minimizes secret exposure | IN_PROGRESS | Encrypted payload in QR (not plaintext); server-relay migration backlog, see `DEVICE_LINKING_REVIEW.md` |

---

## Security Contact

Report security vulnerabilities to: **security@lemma.id**

We follow responsible disclosure and will work with you to resolve issues.

---

## Audit History

| Date | Auditor | Scope | Result |
|------|---------|-------|--------|
| 2026-02-11 | Internal | Launch gate v1676 smoke/transport | Partial, baseline |
| 2026-03-04 | Internal | GA decision record | NO-GO, P0 gaps documented |
| 2026-03-18 | Internal | Revoke→deny evidence script | PASS deny-path (pre list/bloom steps) |
| 2026-06-08 | Internal | Security hardening v2186 deploy | Code PASS; assurance gaps remain, see sign-off section below |

---

## Compliance Notes

- **GDPR**: Lemma is a data-minimized **controller** (likely joint controller with the IDV provider for the verification step). Relying sites receive only a site-private PPID and a boolean claim. Lemma does **not** store raw documents, face/selfie images, or legal name, but **does** store derived, re-identifiable pseudonymous data (document/person root hashes, PPIDs, wallet↔person bindings, revocation state) and logs IP/UA on some paths. Pseudonymous data is still personal data (GDPR Recital 26). Erasure is implemented via `POST /api/ishuman/erase`. See [`docs/architecture/PRIVACY_ARCHITECTURE.md`](../architecture/PRIVACY_ARCHITECTURE.md). Do **not** claim "no personal data on Lemma servers."
- **CCPA**: No sale of personal information.
- **SOC 2**: In progress (server infrastructure only).
- **PCI DSS**: Not applicable, Stripe.js loads on wallet routes only; card data handled by Stripe.

---

## Sign-Off Blockers (operator actions)

These items block **P0-1 Security Controls Sign-off** and **GA GO**. Code/deploy work from the 2026-06 hardening program is complete.

| # | Action | Closes | Artifact to attach |
|---|--------|--------|-------------------|
| 1 | **Platform:** log in on lemma.id, then run `python scripts/revoke_to_deny_smoke.py` | P0-4 (control plane) | `ops/evidence/launch/*-revoke-to-deny-evidence.md` with list+bloom PASS |
| 2 | **Platform login:** passkey matrix on `/unlock` + `/platform` | P0-5 | `ops/evidence/launch/2026-06-08-passkey-browser-matrix.md` + screenshots |
| 3 | **Platform + isHuman:** manual E2E, lemma.id unlock *and* relying-site isHuman verify/IDV | P0-2 | Signed `docs/status/SOLO_GA_TEST_EXECUTION_SHEET.md` |
| 4 | Commission scoped external pentest | P0-6 | Report + remediation tracker per `2026-06-08-external-pentest-scope.md` |
| 5 | Confirm Sentry `security=csp` event from drill POST | P0-7 | Event id in `2026-06-08-incident-drill-csp-alert.md` |
| 6 | Security Lead reviews this checklist and marks remaining IN_PROGRESS/UNKNOWN rows PASS or accepted risk | P0-1 | Updated rows + approver name/date in `GA_GATE_STATUS.md` |
| 7 | Revoke/rotate any test admin/agent tokens used during QA | Token hygiene | Note in SOLO sheet |

**GA rule:** All P0 gates in `GA_GATE_STATUS.md` must be `PASS` before public GA claim.
