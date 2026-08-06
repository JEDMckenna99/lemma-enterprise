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

### Identity-root secrets (network-critical: keep secret)

| Variable                         | What it does                                                          | If missing                                              |
| -------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------- |
| `LEMMA_IDENTITY_ROOT_PEPPER_V1`  | HMAC pepper for `document_root` derivation (>= 32 bytes).            | Dev fallback used; **never acceptable in production.**  |
| `LEMMA_PERSON_ROOT_SALT_V1`      | HKDF salt for `person_root` derivation (>= 32 bytes).               | Dev fallback used; **never acceptable in production.**  |
| `LEMMA_PPID_ROOT_KEY`            | Root key for legacy `wallet_secret`-path PPID derivation.            | Legacy anonymous PPID derivation fails.                 |
| `LEMMA_ACTIVE_ROOT_VERSION`      | Active pepper/salt version for new IDVs (v2 Phase 3.1). Default `V1`.| Defaults to `V1`.                                       |
| `LEMMA_DOCUMENT_ROOT_READ_VERSIONS` | Comma-separated older pepper versions checked when resolving an existing document assignment. | Defaults to `v1` plus the active version. |
| `LEMMA_DOCUMENT_ROOT_READ_PROVIDERS` | Additional legacy provider namespaces checked during IDV-rail migration. | Didit checks `stripe_identity` by default for recovery continuity. |

> Rotation: maintain `_V1`, `_V2`, ... pepper/salt env vars concurrently and
> flip `LEMMA_ACTIVE_ROOT_VERSION`. See Phase 3.1 in
> [V2_DESIGN_IMPROVEMENTS.md](../architecture/V2_DESIGN_IMPROVEMENTS.md).
> **Backup drill:**
> [IDENTITY_ROOT_SECRET_BACKUP_DRILL.md](IDENTITY_ROOT_SECRET_BACKUP_DRILL.md).

### Didit Identity (current IDV rail: Phase 3.2)

Didit is the **default upstream IDV provider** for new verifications. It feeds
the same document-root issuance pipeline as the legacy Stripe rail. Lemma
remains the sole credential issuer; Didit never signs credentials. The rail
activates when `LEMMA_ISHUMAN_DIDIT_ENABLED` is truthy **and** both the API key
and workflow id are present (`is_ishuman_didit_enabled()` in
[api/config.py](../../api/config.py)).

| Variable                          | What it does                                                                       | If missing                                    |
| --------------------------------- | ---------------------------------------------------------------------------------- | --------------------------------------------- |
| `LEMMA_ISHUMAN_DIDIT_ENABLED`     | `"true"` selects didit as a *selectable* provider (still requires key+workflow).   | Didit rail disabled; `provider=didit` -> 400. |
| `DIDIT_API_KEY`                   | `x-api-key` for `POST /v3/session/` (hosted verification session creation).        | `is_ishuman_didit_enabled()` returns false.   |
| `DIDIT_WORKFLOW_ID`               | Didit workflow UUID for proof-of-humanity (ID verification + liveness + face match only). Production value: `668fbf42-cfb7-4774-9ecd-564c297d4a07`. | `is_ishuman_didit_enabled()` returns false.   |
| `DIDIT_WEBHOOK_SECRET`            | HMAC secret for verifying `X-Signature-V2` on `/api/webhooks/didit-identity`.      | Webhook verification fails closed (401).      |
| `DIDIT_API_BASE`                  | Base URL for the didit API. Default `https://verification.didit.me`.               | Defaults to production didit.                 |
| `LEMMA_ISHUMAN_DIDIT_PURGE`       | Delete the upstream didit session after the credential is durably issued (process-and-purge data minimization). Default `"true"`; set `0` to retain sessions (e.g. staging debugging). | Defaults on; best-effort and non-fatal to issuance. |
| `DIDIT_DELETE_PATH_TEMPLATE`      | Override the didit delete route. Default tries `/v3/session/{session_id}/delete/` then legacy `/v3/session/{session_id}/`. | Uses the Management API delete route first. |
| `LEMMA_IDENTITY_ROOT_PEPPER_DIDIT_V1` | Optional per-issuer pepper isolation (Phase 3.2 Option A).                     | Falls back to the shared `LEMMA_IDENTITY_ROOT_PEPPER_V1`. |
| `LEMMA_ISHUMAN_PULL_FALLBACK`         | Status-poll may pull a Didit decision when webhooks are delayed. Default `"true"`. | Disabled when Didit rail is off.              |

> Provider namespacing: `provider` remains part of the signed `document_root`
> claim set. New, previously unseen documents retain provider isolation. During
> recovery, Didit also checks legacy Stripe document-root keys; an existing
> assignment is reused and linked to the current Didit key so a provider
> migration cannot silently replace the assigned person or internal-IAM PPID.

### Stripe Identity (legacy IDV rail: migration only)

Stripe Identity is retained **only for document-root recovery continuity** on
accounts verified before the Didit cutover. Do not provision Stripe as the
primary IDV rail for new environments.

| Variable                | What it does                                                | Production         | Staging / demo     |
| ----------------------- | ----------------------------------------------------------- | ------------------ | ------------------ |
| `STRIPE_SECRET_KEY`     | Legacy Stripe API key. Test-verify rails require `sk_test_`. | live (if needed)   | `sk_test_...`      |
| `STRIPE_WEBHOOK_SECRET` | Verifies `identity.verification_session.*` webhook signatures.| live secret       | test secret        |

Webhook endpoint (legacy): `/api/webhooks/stripe-identity`

### Demo / test rails (only meaningful when `ENVIRONMENT != production`)

| Variable                            | What it does                                                       |
| ----------------------------------- | ----------------------------------------------------------------- |
| `LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY` | `"true"` enables `/api/demo/ishuman/*test*` bypass rails.       |
| `LEMMA_ISHUMAN_DEMO_TEST_TOKEN`     | Shared secret required in `X-Demo-Test-Token` header.             |
| `LEMMA_ISHUMAN_SKELETON_IDV_ENABLED`| Default on non-production; Didit-free `/api/demo/ishuman/skeleton-idv-*`. |
| `LEMMA_ISHUMAN_SKELETON_CREDENTIAL_TTL_SECONDS` | Short-lived skeleton master TTL (default `3600`).          |
| `LEMMA_ISHUMAN_DEMO_QR_CREDENTIAL_TTL_SECONDS` | QR demo on `/demo/ishuman` master TTL (default `900` / 15 min). |
| `LEMMA_ISHUMAN_DEMO_QR_IDV_ENABLED` | `"true"` enables the public QR shell demo (safe on production; short-lived, no Didit). |
| `LEMMA_IDV_HANDOFF_TTL_SECONDS`     | Mobile handoff relay TTL (default `300`).                         |
| `LEMMA_IDV_HANDOFF_STRICT_CLAIM`    | Default `1`; set `0` for legacy session-only handoff claim.         |
| `LEMMA_ISHUMAN_DEMO_API_KEY_<SITE>` | Stable API key for a seeded demo relying site.                    |

### Federated signing service (Option C custody)

Separate Heroku app `lemma-signing` runs `signing_app.py` (`Procfile.signing`). Only
that app should hold federated issuer seed decrypt; the public web app calls it
when `LEMMA_SIGNING_SERVICE_URL` is set.

| Variable | App | What it does |
| -------- | --- | ------------ |
| `LEMMA_SIGNING_SERVICE_URL` | web (`lemma-enterprise`) | Base URL of the private signing app (e.g. `https://lemma-signing.herokuapp.com`). When set, web dynos refuse `get_federated_issuer()` seed load. |
| `LEMMA_SIGNING_SERVICE_TOKEN` | web + signing | Shared bearer secret for `/internal/*` routes. Required when URL is set. |
| `LEMMA_SIGNING_SERVICE` | signing only | Set `1` on the signing app so it uses local seed signing. |

Deploy: create Heroku app `lemma-signing`, same build slug, `heroku ps:scale web=1 -a lemma-signing`,
set `Procfile` via `heroku buildpacks` or deploy with `Procfile.signing` renamed / `heroku config
set PROCFILE=Procfile.signing`. Grant **only** the signing app IAM `kms:Decrypt` for the
federated issuer ciphertext; remove federated decrypt from the web dyno role when cut over.

### Trust bundle mirror failover

| Variable | What it does |
| -------- | ------------ |
| `LEMMA_TRUST_BUNDLE_URLS` | Comma-separated bloom/trust-list bundle URLs tried in order by backend verifiers. Default: lemma.id primary + GitHub Pages mirror (see [TRUST_BUNDLE_MIRROR.md](TRUST_BUNDLE_MIRROR.md)). |

### isHuman v2 feature flags

| Variable                              | Default | What it does                                                                  |
| ------------------------------------- | ------- | ----------------------------------------------------------------------------- |
| `ISHUMAN_CREDENTIAL_TTL_DAYS`         | `365`   | Master credential fallback lifetime when document expiry is unavailable.               |
| `ISHUMAN_SITE_CREDENTIAL_TTL_DAYS`    | `30`    | Site credential lifetime; keep at 30 days for bounded compromise exposure.              |
| `LEMMA_PERSON_ROOT_SOURCE`             | `assigned_v1` | Permanent assigned-person root; document-derived mode is legacy-only.               |
| `LEMMA_ISHUMAN_REISSUE_LIMIT_PER_DAY` | `5`     | Per-wallet/day cap on `/api/ishuman/reissue-master` (Phase 1.3).              |
| `LEMMA_DISABLE_BRIDGE_IFRAME`         | unset   | When `"true"`, verifier SDK uses popup-only flow, skips bridge iframe (Phase 2). |
| `LEMMA_ISHUMAN_USE_PERSON_ROOT_SEEDS` | unset   | When `"true"`, post-IDV wallets use `wallet_local_seed`/`person_root_proxy` derivation (Phase 1.1). |
| `LEMMA_API_RATE_LIMIT_DEGRADED_MODE`  | `memory`| Behavior when Redis limiter is unavailable: `memory` or `fail_open`.          |
| `LEMMA_REDIS_MAX_CONNECTIONS`         | `8`     | Shared Redis pool size per worker (also honors legacy `LEMMA_DB_REDIS_MAX_CONNECTIONS` / `LEMMA_AUTH_REDIS_MAX_CONNECTIONS`). Keep total under Heroku Mini (~20) across workers + Flask-Limiter. |
| `LEMMA_PG_POOL_MAX` / `LEMMA_PG_POOL_MIN` | `5` / `1` | Raw psycopg2 pool for IAM/revocation SQL (`get_db_connection`). |
| `LEMMA_SQLALCHEMY_POOL_SIZE` / `MAX_OVERFLOW` / `POOL_RECYCLE` | `3` / `2` / `280` | SQLAlchemy engine pool tuning. |
| `LEMMA_REVOCATION_FILTER_CACHE_TTL_SECONDS` | `60` | In-process + HTTP `max-age` for bloom filter. |
| `LEMMA_REVOCATION_FILTER_SWR_SECONDS` | `300` | `stale-while-revalidate` for bloom HTTP cache. |
| `LEMMA_DIDIT_CIRCUIT_FAILURES` / `LEMMA_DIDIT_CIRCUIT_RECOVERY_SECONDS` | `5` / `60` | Didit outbound circuit breaker. |
| `LEMMA_BILLING_ENFORCEMENT`           | unset   | When `"1"`, blocks **isHuman** / paid-tier issuance (`derive-site-proof` with `required_assurance=ishuman`) for sites without active billing. Free passkey Sign in with lemma.id is never gated. |

### PPID assurance and authz proof flags

Defaults match [api/config.py](../../api/config.py) and
[api/authz/mode_policy.py](../../api/authz/mode_policy.py).

| Variable                              | Default | What it does                                                                  |
| ------------------------------------- | ------- | ----------------------------------------------------------------------------- |
| `LEMMA_ONE_PPID_ASSURANCE_MODEL`      | `false` | Provisional person root at wallet bind; `isHuman` escalates assurance without changing PPID. |
| `LEMMA_PASSKEY_ASSURANCE_ENABLED`     | `false` | Issue passkey-assurance site credentials before IDV (requires one-PPID model). |
| `LEMMA_PPID_CONVERGENCE_ENABLED`      | `false` | Issue signed convergence artifacts on provisional→known person rebind (requires one-PPID model). |
| `LEMMA_PPID_REQUIRE_PERSON_ROOT`      | `true`  | Fail closed on authoritative server-side PPID derivation instead of legacy wallet-secret fallback. Set `0` only for emergency rollback. |
| `LEMMA_ENFORCE_PROOF_REQUIRED`        | `false` | Hard-enforce `proof_required` auth mode on high-risk Agent Ops mutations. Set `1` after client proof headers ship (`static/js/lemma-auth-headers.js`). |
| `LEMMA_AUTHZ_PROOF_SHADOW`            | `1`     | Evaluate proof chains in shadow mode (log mismatches without blocking). Set `0` only for emergency rollback once hard enforcement is on. |

### Network revocation (retired)

Network-wide isHuman revocation is **permanently retired**
(`is_ishuman_network_revocation_enabled()` always returns `false` in
[api/config.py](../../api/config.py)). Customer, admin, trust-queue, and demo
network-revoke endpoints return HTTP **410** with `network_revocation_retired`.
Use **site-block** (`/api/ishuman/site-block`) for persistent site-scoped
enforcement.

### Platform owner (lemma.id admin sole-control)

| Variable                    | What it does |
| --------------------------- | ------------ |
| `LEMMA_PLATFORM_OWNER_PPID` | Person-root PPID allowed platform admin on `lemma.id`. When set, other PPIDs cannot receive platform admin credentials. |
| `LEMMA_ADMIN_EMAIL`         | Email for platform admin self-issue bootstrap. |

Bootstrap: `python scripts/bootstrap_platform_owner.py --owner-ppid did:lemma:ppid_...`

## 3. Provisioning runbook (operator-run)

> These steps require Heroku CLI access and DNS control. Run them manually;
> they cannot be executed from the coding environment.

```bash
# 1. Create the staging/demo app
heroku create lemma-staging --remote lemma-staging

# 2. Copy LEMMA_*, DIDIT_*, DATABASE_URL config from production
heroku config -a lemma-enterprise --json \
  | jq 'with_entries(select(.key | test("LEMMA|DIDIT|DATABASE_URL")))' \
  | jq -r 'to_entries | map("\(.key)=\(.value)") | join("\n")' \
  | xargs -L 1 heroku config:set --app lemma-staging

# 3. Override environment + enable demo rails on staging
heroku config:set -a lemma-staging \
  ENVIRONMENT=staging \
  LEMMA_ORIGIN=https://demo.lemma.id \
  LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=true \
  LEMMA_ISHUMAN_DIDIT_ENABLED=true \
  DIDIT_API_KEY=... \
  DIDIT_WORKFLOW_ID=...

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
`ENVIRONMENT=production`. No code rollback required, `_demo_enabled()`
preserves the prior behavior (production disables demo) exactly.
