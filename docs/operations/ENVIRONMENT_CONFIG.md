# Environment Configuration Contract (isHuman)

> Single source of truth for the environment variables the isHuman identity
> network reads, the values production vs. staging should carry, and what
> breaks if a variable is missing. This is the most important operational
> artifact for the demo/production split (v2 Phase 6).

## 1. The demo / production split

The v2 topology runs **two Heroku apps** off the same codebase:

| App                       | Purpose                     | `ENVIRONMENT` | Demo endpoints / tokens | Real customers |
| ------------------------- | --------------------------- | ------------- | ----------------------- | -------------- |
| `lemma-enterprise`        | Production identity network | `production`  | disabled                | yes            |
| `lemma-staging` (demo)    | Demo + staging              | `staging`     | enabled                 | no             |

The single gate that decides this is `_demo_enabled()` in
[api/ishuman_demo.py](../../api/ishuman_demo.py):

```python
def _demo_enabled() -> bool:
    return os.getenv("ENVIRONMENT", "").strip().lower() != "production"
```

Everything demo-related (popup token rendering in `_demo_page_context`, the
`/api/demo/ishuman/*test*` rails in `_require_demo_test_verify`) routes through
this helper. Production (`ENVIRONMENT=production`) disables them; **any other
value, including `staging` and unset, enables them.**

## 2. Environment variable reference

### Core platform

| Variable           | What it does                                                                 | Production            | Staging / demo       | If missing                                  |
| ------------------ | ---------------------------------------------------------------------------- | --------------------- | -------------------- | ------------------------------------------- |
| `ENVIRONMENT`      | Selects production vs. staging behavior; gates demo affordances.             | `production`          | `staging`            | Treated as non-production -> demo enabled.  |
| `DATABASE_URL`     | SQLAlchemy connection string (Postgres in prod).                             | Postgres URL          | Postgres URL         | App cannot start / persist verifications.   |
| `REDIS_URL`        | Distributed rate-limit + wallet-challenge backend.                           | Redis URL             | Redis URL (optional) | Rate limiter falls back to in-process memory. |
| `LEMMA_ORIGIN`     | Canonical origin the wallet popup + demo subtree apps point at.              | `https://lemma.id`    | `https://demo.lemma.id` | Wallet/demo cross-origin flows misroute.   |

### Identity-root secrets (network-critical — keep secret)

| Variable                         | What it does                                                          | If missing                                              |
| -------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------- |
| `LEMMA_IDENTITY_ROOT_PEPPER_V1`  | HMAC pepper for `document_root` derivation (>= 32 bytes).            | Dev fallback used; **never acceptable in production.**  |
| `LEMMA_PERSON_ROOT_SALT_V1`      | HKDF salt for `person_root` derivation (>= 32 bytes).               | Dev fallback used; **never acceptable in production.**  |
| `LEMMA_PPID_ROOT_KEY`            | Root key for legacy `wallet_secret`-path PPID derivation.            | Legacy anonymous PPID derivation fails.                 |
| `LEMMA_ACTIVE_ROOT_VERSION`      | Active pepper/salt version for new IDVs (v2 Phase 3.1). Default `V1`.| Defaults to `V1`.                                       |

> Rotation: maintain `_V1`, `_V2`, ... pepper/salt env vars concurrently and
> flip `LEMMA_ACTIVE_ROOT_VERSION`. See Phase 3.1 in
> [V2_DESIGN_IMPROVEMENTS.md](../architecture/V2_DESIGN_IMPROVEMENTS.md).

### Stripe Identity (IDV rail)

| Variable                | What it does                                                | Production         | Staging / demo     |
| ----------------------- | ----------------------------------------------------------- | ------------------ | ------------------ |
| `STRIPE_SECRET_KEY`     | Stripe API key. Test-verify rails require an `sk_test_` key.| `sk_live_...`      | `sk_test_...`      |
| `STRIPE_WEBHOOK_SECRET` | Verifies `identity.verification_session.*` webhook signatures.| live secret       | test secret        |

### Didit Identity (second IDV rail — Phase 3.2)

Didit is an optional upstream IDV provider that feeds the *same* document-root
issuance pipeline as Stripe. Lemma remains the sole credential issuer; didit
never signs credentials. The rail is **off by default** and only activates when
both the API key and workflow id are present.

| Variable                          | What it does                                                                       | If missing                                    |
| --------------------------------- | ---------------------------------------------------------------------------------- | --------------------------------------------- |
| `LEMMA_ISHUMAN_DIDIT_ENABLED`     | `"true"` selects didit as a *selectable* provider (still requires key+workflow).   | Didit rail disabled; `provider=didit` -> 400. |
| `DIDIT_API_KEY`                   | `x-api-key` for `POST /v3/session/` (hosted verification session creation).        | `is_ishuman_didit_enabled()` returns false.   |
| `DIDIT_WORKFLOW_ID`               | Didit workflow UUID for proof-of-humanity (ID verification + liveness + face match only). Production value: `668fbf42-cfb7-4774-9ecd-564c297d4a07`. | `is_ishuman_didit_enabled()` returns false.   |
| `DIDIT_WEBHOOK_SECRET`            | HMAC secret for verifying `X-Signature-V2` on `/api/webhooks/didit-identity`.      | Webhook verification fails closed (401).      |
| `DIDIT_API_BASE`                  | Base URL for the didit API. Default `https://verification.didit.me`.               | Defaults to production didit.                 |
| `LEMMA_ISHUMAN_DIDIT_PURGE`       | Delete the upstream didit session after the credential is durably issued (process-and-purge data minimization). Default `"true"`; set `0` to retain sessions (e.g. staging debugging). | Defaults on; best-effort and non-fatal to issuance. |
| `DIDIT_DELETE_PATH_TEMPLATE`      | Override the didit delete route. Default `/v3/session/{session_id}/` per didit's data-retention docs. Set to `/v3/session/{session_id}/delete/` if your tenant uses that route. | Uses the documented default path. |
| `LEMMA_IDENTITY_ROOT_PEPPER_DIDIT_V1` | Optional per-issuer pepper isolation (Phase 3.2 Option A).                     | Falls back to the shared `LEMMA_IDENTITY_ROOT_PEPPER_V1`. |

> Provider namespacing: `provider` is part of the signed `document_root` claim
> set, so the same physical document verified through didit derives a *distinct*
> person_root/PPID from the Stripe rail. This is intentional isolation, not a
> bug. Because the didit rail ships flag-off with no prior users, the optional
> per-issuer pepper can be provisioned at any time before first didit issuance
> without a migration.

### Demo / test rails (only meaningful when `ENVIRONMENT != production`)

| Variable                            | What it does                                                       |
| ----------------------------------- | ----------------------------------------------------------------- |
| `LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY` | `"true"` enables `/api/demo/ishuman/*test*` bypass rails.       |
| `LEMMA_ISHUMAN_DEMO_TEST_TOKEN`     | Shared secret required in `X-Demo-Test-Token` header.             |
| `LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN`    | Shared secret required in `X-Demo-Admin-Token` (network revoke).  |
| `LEMMA_ISHUMAN_DEMO_API_KEY_<SITE>` | Stable API key for a seeded demo relying site.                    |

### isHuman v2 feature flags

| Variable                              | Default | What it does                                                                  |
| ------------------------------------- | ------- | ----------------------------------------------------------------------------- |
| `ISHUMAN_CREDENTIAL_TTL_DAYS`         | `365`   | Lifetime of issued isHuman credentials.                                       |
| `LEMMA_ISHUMAN_REISSUE_LIMIT_PER_DAY` | `5`     | Per-wallet/day cap on `/api/ishuman/reissue-master` (Phase 1.3).              |
| `LEMMA_DISABLE_BRIDGE_IFRAME`         | unset   | When `"true"`, verifier SDK uses popup-only flow, skips bridge iframe (Phase 2). |
| `LEMMA_ISHUMAN_USE_PERSON_ROOT_SEEDS` | unset   | When `"true"`, post-IDV wallets use `wallet_local_seed`/`person_root_proxy` derivation (Phase 1.1). |
| `LEMMA_API_RATE_LIMIT_DEGRADED_MODE`  | `memory`| Behavior when Redis limiter is unavailable: `memory` or `fail_open`.          |

## 3. Provisioning runbook (operator-run)

> These steps require Heroku CLI access and DNS control. Run them manually;
> they cannot be executed from the coding environment.

```bash
# 1. Create the staging/demo app
heroku create lemma-staging --remote lemma-staging

# 2. Copy LEMMA_*, STRIPE_*, DATABASE_URL config from production
heroku config -a lemma-enterprise --json \
  | jq 'with_entries(select(.key | test("LEMMA|STRIPE|DATABASE_URL")))' \
  | jq -r 'to_entries | map("\(.key)=\(.value)") | join("\n")' \
  | xargs -L 1 heroku config:set --app lemma-staging

# 3. Override environment + enable demo rails on staging
heroku config:set -a lemma-staging \
  ENVIRONMENT=staging \
  LEMMA_ORIGIN=https://demo.lemma.id \
  LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=true \
  STRIPE_SECRET_KEY=sk_test_...

# 4. Point demo.lemma.id at the staging app (Heroku domains + DNS CNAME)
heroku domains:add demo.lemma.id -a lemma-staging

# 5. Repoint the demo subtree apps at the staging origin
heroku config:set -a lemma-demo-tickets LEMMA_ORIGIN=https://demo.lemma.id
heroku config:set -a lemma-demo-trials  LEMMA_ORIGIN=https://demo.lemma.id
```

### Post-provision verification

```bash
# Production must REFUSE demo test-verify
curl -s -X POST https://lemma.id/api/demo/ishuman/verify-once-test-mode \
  -H "Content-Type: application/json" -d '{"wallet_id":"wallet_x"}' | jq .error
# Expected: "prod_test_verify_forbidden"

# Staging must ALLOW it (with token configured)
curl -s -X POST https://demo.lemma.id/api/demo/ishuman/verify-once-test-mode \
  -H "Content-Type: application/json" -d '{"wallet_id":"wallet_x"}' | jq .error
# Expected: "demo_test_token_required" (gate passed, token check reached)
```

## 4. Rollback

Phase 6 is reverted purely by env config: leave `lemma-enterprise` on
`ENVIRONMENT=production`. No code rollback required — `_demo_enabled()`
preserves the prior behavior (production disables demo) exactly.
