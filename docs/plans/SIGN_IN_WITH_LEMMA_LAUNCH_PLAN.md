# Launch plan: free "Sign in with lemma.id" (passkey tier)

Status: **Agent implementation complete — operator launch pending** (2026-07-28)
Audience: Coding agent executing launch prep
Date: 2026-07-28

## Execution summary

Code, docs, and automated tests for Phases 1–5 are landed. **Phase 6 deploy,
flag enablement, and browser E2E remain operator actions.**

| Phase | Agent status | Notes |
|-------|--------------|-------|
| 1 | Done (code/tests) | Staging flags + manual E2E still human |
| 2 | Done | |
| 3 | Done (core) | Optional re-show via `count_active_wallet_devices` not implemented |
| 4 | Done | Auth.js provider stretch skipped (optional) |
| 5 | Done (design + safe harden) | Key custody implementation blocked on human approval |
| 6 | Partial | Regression green; deploy/flags/smoke human |
| 7 | Done | Sign-in parity backlog (button, test helpers, docs, SDK outcomes) |

**Regression:** `python scripts/ci_regression_suite.py` passed (1268 tests) after implementation.

**Key deliverables:** `api/ishuman_demo.py`, `templates/wallet_ishuman_idv.html`,
`api/ishuman.py` (rate limits), `billing/billing_access.py`, quickstart docs,
session examples (Flask/Express/FastAPI/Next.js), `@lemma.id/proof-verifier@1.4.1`
with `index.d.ts`, developer hub + domain-verify UI, `docs/security/ISSUER_KEY_CUSTODY.md`.

---

## Product definition

Free passwordless login for relying sites. The developer adds the browser SDK,
requests `requiredAssurance: 'passkey'`, verifies the signed presentation on
their backend, and uses the per-site `ppid` as the stable login identifier.
No IDV, no usernames/passwords, no site registration, no API key for the basic
flow. isHuman remains the paid step-up tier on the same PPID.

The runtime path is already implemented end to end. This plan enables it,
hardens it, and packages it for adoption. Work through phases in order;
tasks inside a phase are independent unless noted.

## Read first (mandatory)

- `AGENTS.md` (repo root) — hard rules. Especially: `siteId` = canonical
  hostname; fail closed; never trust a bare client `ppid`; verify signed
  presentations server-side.
- `docs/integration/ISHUMAN_AGENT_INTEGRATION.md` — the canonical current
  integration contract. This is the source of truth; the quickstart docs this
  plan rewrites are legacy.
- `docs/product/PASSKEY_STAMP_INPUT_BURN.md` — one-PPID assurance-tier
  contract (`passkey` vs `ishuman`, same PPID).
- `.cursor/rules/github-devops.mdc` — deploy targets and the Auth Launch Gate
  workflow.

## Guardrails for every phase

- Baseline before touching anything: run `python scripts/ci_regression_suite.py`
  (tests run against in-memory SQLite with the CI env from
  `.github/workflows/ci-regression.yml`). Re-run after each phase. No new
  failures.
- Do not change the credential envelope, signature format, PPID derivation, or
  the `derive-site-proof` response shape. Relying-site verifiers in the wild
  (`@lemma.id/proof-verifier@1.4.1` on npm) must keep verifying.
- Do not weaken any fail-closed behavior (trust-bundle staleness, plaintext
  persistence refusal, assurance gating).
- The isHuman (IDV) flow must keep working unchanged — it shares the popup,
  `derive-site-proof`, and the SDK with this product.
- Feature-flag anything user-visible where a regression would break live
  logins.

---

## Phase 1 — Turn the product on, honestly

### 1.1 Stage the assurance-flag rollout

The passkey tier is fully built but disabled. `passkey_assurance_enabled()` in
`api/config.py` requires BOTH `LEMMA_ONE_PPID_ASSURANCE_MODEL=1` and
`LEMMA_PASSKEY_ASSURANCE_ENABLED=1`; both default off. Without them,
`POST /api/ishuman/derive-site-proof` returns 403 `wallet_not_verified` for
never-IDV'd wallets and `passkey_assurance_disabled` for verified ones
(`api/ishuman.py`, no-master branch ~2395–2466 and minimum-disclosure branch
~2535).

- [x] Verify test coverage passes with flags on:
      `tests/test_one_ppid_assurance_model.py`,
      `tests/test_minimum_disclosure_assurance.py`.
- [ ] Enable both flags on staging (Heroku config vars — **HUMAN ACTION**).
      Keep `LEMMA_BILLING_ENFORCEMENT` unset/0: when it is 1,
      `billing/billing_access.py` blocks issuance for unregistered hostnames,
      which contradicts this product's no-registration model.
- [ ] Manual staging E2E with a fresh browser profile (no existing wallet):
      relying page → `verifyForBackend({ autoProvision: true,
      requiredAssurance: 'passkey' })` → popup creates wallet inline →
      presentation returns with `assurance: 'passkey'` → backend verifier
      (`packages/proof-verifier-py/lemma_proof_verifier.py` with
      `required_assurance='passkey'`) accepts it. (**HUMAN ACTION**)
- [ ] Production enable is the final step of this plan (Phase 6), not now.

### 1.2 Make the popup fail honestly when the tier is disabled

- [x] Align `api/ishuman_demo.py` so the data attribute mirrors
      `passkey_assurance_enabled()` exactly.
- [x] In the popup, when `issue_mode=site_proof` + `required_assurance=passkey`
      and the attribute is false, render a clear "passkey sign-in is not
      available yet" state instead of the Continue flow.
- [x] Add/extend a template test:
      `tests/test_ishuman_demo.py` (`test_ishuman_idv_passkey_flag_off_by_default`,
      `test_ishuman_idv_passkey_flag_on_when_both_env_vars_set`).

### 1.3 First-run popup copy

- [x] Detect the no-wallet state in `prepareSiteProofUi` and switch button /
      helper copy to creation framing: "Create your lemma.id" with a one-line
      explanation (passkey, no email or password).
- [x] Keep returning-user copy as unlock framing.
- [x] Copy and state detection only — no flow logic changes.

## Phase 2 — Abuse control (required before public launch)

### 2.1 Rate-limit `derive-site-proof`

- [x] Add limits keyed by wallet id AND by (client IP, site hostname):
      10/min per wallet, 60/min per IP+host (`api/ishuman.py`).
- [x] Respect degraded mode when Redis is unavailable (`api/rate_limiter.py`).
- [x] Return 429 with stable error code `derive_site_proof_rate_limited`
      (`docs/ERROR_CODES.md`).
- [x] Tests: `tests/test_derive_site_proof_rate_limit.py` (under-limit, 429,
      fail_open degraded mode). Test isolation via `reset_memory_rate_limit_counters`
      in `tests/conftest.py`.

## Phase 3 — Recovery UX (the trust landmine)

### 3.1 Second-device nudge after first sign-in

- [x] After successful first issuance (wallet created this session), show one
      dismissible screen before close: "Add a second device…", linking to `/link`
      (`templates/wallet_ishuman_idv.html`: `finishSiteProofWithOptionalNudge`).
- [x] Skippable in one tap; sign-in `postMessage` completes on skip or after
      "Add another device". Returning users skip.
- [x] Persist `secondDeviceNudgeShown` in wallet meta (at most once).
- [ ] Optional: re-show after N sign-ins if still single-device via
      `count_active_wallet_devices` (`api/wallet_authn.py`) — **not implemented**.

## Phase 4 — Developer experience

### 4.1 Rewrite the login quickstarts

- [x] Rewrite `docs/integration/QUICK_START_SIMPLE_LOGIN.md` and
      `docs/integration/SIMPLE_INTEGRATION_GUIDE.md` on the current
      `ProofVerifier` + passkey contract.
- [x] Document localhost workflow, recovery honesty, step-up to isHuman.
- [x] Cross-checked against `static/js/ishuman-verifier.js` and
      `docs/integration/ISHUMAN_AGENT_INTEGRATION.md`.

### 4.2 Session layer: complete the examples into real logins

- [x] Flask, Express, FastAPI: full login with HttpOnly session cookie,
      auth guard, `/logout`; default `requiredAssurance: 'passkey'`.
- [x] Next.js runnable App Router app under `examples/nextjs_ishuman_signup/`.
- [ ] Optional stretch: Auth.js/NextAuth provider — **skipped** (optional per plan).

### 4.3 Package hygiene

- [x] TypeScript types: `packages/proof-verifier-js/index.d.ts`; bumped to **1.4.1**
      in `package.json`, `docs/sdk/ISHUMAN_SDK_VERSIONS.json`, `static/js/proof-verifier.mjs`.
- [ ] npm publish `@lemma.id/proof-verifier@1.4.1` — **HUMAN ACTION**
      (`npm pack` in `packages/proof-verifier-js/` when ready).
- [x] PyPI README updated for drop-in install until token exists.
- [ ] `python -m build` + PyPI upload — **HUMAN ACTION** (`PYPI_API_TOKEN`).

### 4.4 Fix the one live registration UI

- [x] Domain verification wired via `/api/customer/domain-verification/start`
      in `templates/developer/external_api_keys.html`.
- [x] Copy clarifies keys are for abuse APIs only, not basic login.

### 4.5 Developer hub cleanup

- [x] Orphan `/developer/sites*` links repaired in
      `templates/developer/overview.html` → `/developer/external-api-keys`.
- [x] "Your sites" section on `templates/developer/ishuman_platform.html`
      via `GET /api/customer/sites` with integration snippet.

## Phase 5 — Security hardening (before driving adoption)

### 5.1 Issuer key custody

- [x] Design note: `docs/security/ISSUER_KEY_CUSTODY.md`.
- [ ] Implement after human approval — **HUMAN DECISION**.

### 5.2 Wallet unlock-window hardening

- [x] Re-gate sensitive local backup on fresh passkey (`_backupWalletData`);
      added `exportWalletSecret()` requiring fresh passkey. Device-link send
      paths already used `_requireFreshPasskeyAuth`.
- [x] Tightened `postMessage` in `templates/wallet_popup.html` to explicit
      `origin` param instead of `'*'`.
- [x] Unlock bundle lifetime unchanged (human signoff required to shorten).

## Phase 6 — Launch checklist

- [x] Full regression: `python scripts/ci_regression_suite.py` green.
- [ ] Staging E2E (Phase 1.1 script): new user, returning user, popup-blocked
      redirect fallback, mobile redirect, second-device nudge, rate-limit 429.
      (**HUMAN ACTION**)
- [ ] Verify isHuman demo flow still works in staging after flag enable.
      (**HUMAN ACTION**)
- [ ] Deploy: `git push github HEAD:main` then `git push production HEAD:main`;
      Auth Launch Gate must pass. (**HUMAN ACTION**)
- [ ] Enable `LEMMA_ONE_PPID_ASSURANCE_MODEL=1` and
      `LEMMA_PASSKEY_ASSURANCE_ENABLED=1` in production. (**HUMAN ACTION**)
- [x] Code comment at billing gate noting free-tier SIWL dependency
      (`billing/billing_access.py`). Confirm `LEMMA_BILLING_ENFORCEMENT` stays off
      at deploy time. (**HUMAN ACTION** to verify config)
- [ ] Smoke-test production with fresh wallet on external hostname + localhost.
      (**HUMAN ACTION**)
- [ ] Publish rewritten quickstarts at lemma.id/docs (deploy docs). (**HUMAN ACTION**)

## Phase 7 — Sign-in parity backlog (post-launch, ordered)

What developers expect from a sign-in product that lemma does not yet provide.
Do these after Phase 6; the first three are the highest-leverage.

### 7.1 Drop-in sign-in button

- [x] Ship `<lemma-signin>` web component (`static/js/lemma-signin.js`) + React wrapper
      (`examples/nextjs_ishuman_signup/components/LemmaSignIn.tsx`); served at
      `/sdk/lemma-signin.js`. Default path in quickstarts.

### 7.2 Test mode / test credentials

- [x] Python: `packages/proof-verifier-py/lemma_proof_verifier_testing.py`
      (`mint_test_presentation`, `create_offline_test_context`).
- [x] Node: `packages/proof-verifier-js/testing.mjs` export + `/sdk/proof-verifier-testing.mjs`.
- [x] Documented in quickstart ("Testing your integration").

### 7.3 Profile-data expectation (docs pattern)

- [x] Quickstart + integration guide sections: first-login display name keyed to PPID;
      "you own profile, lemma owns proof."

### 7.4 Popup copy for login

- [x] Passkey site-proof intro: "Sign in to {site} with your lemma.id"
      (`ishuman-idv-preview-scenes.js`). Headline: "Sign in to continue".
      isHuman copy unchanged.

### 7.5 Browser support matrix + SDK error codes

- [x] `docs/integration/BROWSER_SUPPORT.md` — browser/PRF matrix.
- [x] SDK stable outcomes in `verifyForBackend()`: `passkey_unsupported`,
      `popup_blocked`, `user_cancelled`, `rate_limited`.
- [x] `docs/ERROR_CODES.md` updated.

### 7.6 Account-linking recipe (docs only)

- [x] Section 10 in `SIMPLE_INTEGRATION_GUIDE.md`.

### 7.7 Sign-out semantics (docs only)

- [x] Section 11 in `SIMPLE_INTEGRATION_GUIDE.md`.

### 7.8 Explicit non-features (docs only)

- [x] Section 12 in `SIMPLE_INTEGRATION_GUIDE.md`.

## Explicitly out of scope for this launch

- Credential envelope cleanup (single canonicalization, VC `type`, claim
  dedup) — pre-growth debt, separate plan; do not mix with launch changes.
- `did:web` publication, BitstringStatusList, FedCM/Digital Credentials API,
  selective disclosure — interop roadmap, not launch.
- Open-sourcing the SDK/verifiers, status page, ToS/privacy-policy updates —
  trust roadmap items owned by the operator, not this agent.
- Any billing/free-allowance implementation.

## Known human-action items (operator)

1. Heroku config vars: staging + production passkey flags; keep billing enforcement off.
2. npm publish `@lemma.id/proof-verifier@1.4.1`.
3. `PYPI_API_TOKEN` provisioning + PyPI upload (or continue drop-in path).
4. Key-custody approach decision (`docs/security/ISSUER_KEY_CUSTODY.md`).
5. Staging/production browser E2E and smoke tests.
6. Deploy + Auth Launch Gate + prod flag flip.
