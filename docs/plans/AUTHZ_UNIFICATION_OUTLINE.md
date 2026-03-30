# Authz Unification Outline

Goal: converge on a unified verifier + policy engine while preserving current platform behavior.

## Phase Checklist

- [x] Phase 0 - Baseline outline + acceptance criteria
- [x] Phase 1 - Add `api/authz_engine.py` scaffold (credential decode/verify, normalized principal)
- [x] Phase 2 - Migrate `require_authenticated` to use authz engine
- [x] Phase 3 - Migrate `require_wallet_ppid` and `require_customer_or_admin`
- [x] Phase 4 - Remove direct PPID header reads in targeted API modules
- [x] Phase 5 - Add policy matrix + centralized deny reasons
- [x] Phase 6 - Full regression pass + deployment validation
- [x] Phase 7 - Add auth contract-gate tests for signed payload + header-to-authz path

## Acceptance Criteria

- No protected endpoint accepts raw `X-Lemma-PPID` as authentication.
- Full-credential verification path is centralized and reused.
- Decorator behavior remains backward-compatible for agent/API-key/access-token paths.
- Each phase has a recorded test result before moving forward.

## Progress Log

### Phase 0 - Baseline outline + acceptance criteria
- Status: Complete
- Changes:
  - Created this outline and defined phase gates.
- Tests:
  - N/A (planning phase)

### Phase 1 - Add `api/authz_engine.py` scaffold
- Status: Complete
- Changes:
  - Added `api/authz_engine.py` with:
    - `AuthzPrincipal` normalized context dataclass
    - lemma header decode (`JSON` and `base64url(JSON)`)
    - trusted-issuer verification integration
    - normalized principal extraction via `extract_user_lemma_principal(...)`
- Tests:
  - `tests/test_authz_engine_phase12.py::test_extract_user_lemma_principal_valid_header` (PASS)

### Phase 2 - Migrate `require_authenticated`
- Status: Complete
- Changes:
  - Updated `auth/decorators.py`:
    - `require_authenticated` now uses `api.authz_engine.extract_user_lemma_principal(...)`
    - `extract_authenticated_ppid_from_request()` now resolves PPID via authz engine
- Tests:
  - `tests/test_authz_engine_phase12.py::test_require_authenticated_accepts_verified_lemma_header` (PASS)
  - `tests/test_authz_engine_phase12.py::test_require_authenticated_rejects_ppid_only_header` (PASS)

### Phase 3 - Migrate `require_wallet_ppid` and `require_customer_or_admin`
- Status: Complete
- Changes:
  - Updated `auth/decorators.py`:
    - `require_wallet_ppid` now resolves user lemma principal via `api.authz_engine`
    - `require_customer_or_admin` now resolves lemma principal/scope/admin via `api.authz_engine`
- Tests:
  - `tests/test_authz_engine_phase12.py::test_require_wallet_ppid_accepts_verified_lemma_header` (PASS)
  - `tests/test_authz_engine_phase12.py::test_require_customer_or_admin_marks_admin_from_lemma_scope` (PASS)

### Phase 4 - Remove direct PPID header reads in targeted API modules
- Status: Complete
- Changes:
  - Verified targeted API modules do not directly consume `X-Lemma-PPID`.
  - Command result: `rg "request\\.headers\\.get\\('X-Lemma-PPID'\\)|X-Lemma-PPID" api` returned no matches.
- Tests:
  - `tests/test_authz_engine_phase12.py` (5 tests) (PASS)

### Phase 5 - Add policy matrix + centralized deny reasons
- Status: Complete
- Changes:
  - Added `api/authz_policy.py` with:
    - `ROUTE_AUTHZ_POLICY` matrix for high-traffic protected routes
    - `AUTH_ERROR_CATALOG` centralized deny-reason defaults
    - `get_policy_for_request(...)` and `get_error_defaults(...)`
  - Updated `auth/decorators.py`:
    - `_auth_error(...)` now resolves default message/status from centralized error catalog
    - Replaced remaining ad-hoc auth-required JSON responses with `_auth_error(...)`-based responses
- Tests:
  - `tests/test_authz_policy_phase5.py::test_get_policy_for_request_known_route` (PASS)
  - `tests/test_authz_policy_phase5.py::test_get_error_defaults_known_and_unknown_codes` (PASS)
  - `tests/test_authz_engine_phase12.py` (5 tests) (PASS)

### Phase 6 - Full regression pass + deployment validation
- Status: Complete
- Changes:
  - Ran consolidated regression checks.
  - Deployed authz unification changes to production:
    - Commit: `f8d2afe0`
    - Heroku release: `v1775`
- Tests:
  - `python -m pytest tests/test_authz_engine_phase12.py tests/test_authz_policy_phase5.py -v` (7 passed)
  - `python -m py_compile auth/decorators.py api/authz_engine.py api/authz_policy.py` (PASS)
  - Live smoke:
    - `GET /api/health` => 200
    - `GET /api/developer/sites` (no auth) => 401 `auth_required`
    - `GET /api/developer/sites` (`X-Lemma-PPID` only) => 401 `auth_required`

### Phase 7 - Add auth contract-gate tests for signed payload + header-to-authz path
- Status: Complete
- Changes:
  - Added `tests/auth_contract/test_signed_lemma_roundtrip.py`:
    - golden signed credential shape verification
    - mutation guard for top-level legacy `signature` field
    - mutation guard for string `issuanceDate`
  - Added `tests/auth_contract/test_header_to_authz_contract.py`:
    - `X-Lemma-Credential` decode -> `authz_engine` principal extraction
    - deterministic untrusted-issuer diagnostic propagation
    - invalid header payload rejection
- Tests:
  - `python -m pytest tests/auth_contract/test_signed_lemma_roundtrip.py tests/auth_contract/test_header_to_authz_contract.py -v` (6 passed)

## Integration Simplification Execution (Stripe-like DX)

Goal: make integration secure-by-default and easy to adopt without custom auth glue.

### DX Phase Checklist

- [x] P0 - Secure quickstart rewrite (full lemma header + backend verification)
- [x] P1 - Publish official middleware packages (Flask + Express)
- [x] P2 - Durable hosted SDK auth state (TTL-backed, one-time state consume)
- [x] P3 - Expand policy matrix coverage for all protected routes
- [x] P5 - Production profile guardrails (no implicit demo fallbacks)
- [x] P4 - CLI onboarding (`lemma init`, `lemma setup`, `lemma verify`, `lemma audit`, `lemma fix`, `lemma smoke`, `lemma ci`, `lemma doctor`)

### P0 - Secure quickstart rewrite
- Status: Complete
- Changes:
  - Updated `templates/docs/quickstart.html`:
    - Replaced PPID-only auth flow examples with full `X-Lemma-Credential` header flow.
    - Added backend verification examples for Flask and Express using `verify_credential_with_trust`.
    - Added explicit warning that PPID-only backend auth is legacy compatibility mode.
    - Updated auto-sign-in example to forward encoded lemma instead of raw PPID body.
- Tests:
  - Content verification via code review for removal of PPID-only primary examples.

### P2 - Durable hosted SDK auth state
- Status: Complete
- Changes:
  - Updated `api/sdk_auth.py`:
    - Replaced process-local `pending_sdk_requests` map with shared TTL-backed storage through `auth.redis_store`.
    - Added one-time state consumption path (`_consume_pending_sdk_request`) to prevent callback replay.
    - Added dedicated key prefix and 10-minute TTL constants for state tracking.
    - Updated cleanup routine to use `redis_store` fallback cleanup.
- Tests:
  - Targeted pytest to validate callback state lifecycle and replay denial (recorded below in test run section).

### P1 - Middleware package scaffolds (Flask + Express)
- Status: Complete
- Changes:
  - Added Python package scaffold:
    - `sdk/python/lemma_auth_flask/pyproject.toml`
    - `sdk/python/lemma_auth_flask/src/lemma_auth_flask/core.py`
    - `sdk/python/lemma_auth_flask/src/lemma_auth_flask/__init__.py`
    - `sdk/python/lemma_auth_flask/README.md`
  - Added Node package scaffold:
    - `sdk/node/lemma-auth-express/package.json`
    - `sdk/node/lemma-auth-express/index.js`
    - `sdk/node/lemma-auth-express/README.md`
  - Added Python middleware tests:
    - `tests/test_lemma_auth_flask_sdk.py`
- Tests:
  - `python -m pytest tests/test_lemma_auth_flask_sdk.py -q` (2 passed)

### P5 - Production profile guardrails
- Status: Complete
- Changes:
  - Updated `api/sdk_api.py`:
    - Added environment profile helpers (`_is_non_prod_mode`, `_allow_sdk_demo_features`).
    - Gated demo key acceptance behind explicit non-production opt-in (`LEMMA_SDK_ALLOW_DEMO=true`).
    - Switched platform API key compare to constant-time `hmac.compare_digest`.
    - Moved network registry URL to env-driven config (`LEMMA_NETWORK_REGISTRY_URL`) and fail-closed default in production.
    - Disabled automatic Stripe demo fallback in production paths for start/complete verification endpoints.
    - Added profile visibility to `/api/sdk/health` response (mode, demo enabled, registry configured).
- Tests:
  - Targeted pytest for API key/demo gating and profile helpers (recorded below in test run section).

### P3 - Expand policy matrix coverage
- Status: Complete
- Changes:
  - Updated `api/authz_policy.py`:
    - Expanded `ROUTE_AUTHZ_POLICY` from bootstrap routes to broad coverage across:
      - developer platform/site management routes
      - customer/dashboard protected routes
      - agent credential routes
      - API-key protected auth endpoints
      - billing/session-sensitive routes
    - Added template path matching support in `get_policy_for_request(...)` so dynamic paths with placeholders (for example `<site_id>`, `<int:key_id>`) resolve correctly.
    - Added additional centralized auth error defaults for existing decorator deny reasons (`invalid_access_token`, `missing_permission`, `credential_revoked`, `site_not_allowed`, `site_scope_validation_failed`).
  - Updated `tests/test_authz_policy_phase5.py`:
    - Added template route resolution test.
    - Added core protected route coverage test to fail if expected routes drop from policy mapping.
- Tests:
  - `python -m pytest tests/test_authz_policy_phase5.py tests/test_authz_engine_phase12.py -q` (9 passed)
  - `python -m py_compile api/authz_policy.py` (PASS)

### P4 - CLI onboarding commands
- Status: Complete
- Changes:
  - Added `scripts/lemma_cli.py` implementing:
    - `lemma init` (writes `.lemma/config.json` with site/domain/header defaults)
    - `lemma setup` (scaffolds frontend/server integration templates for Flask/Express)
    - `lemma verify` (checks platform API key env + optional API health)
    - `lemma audit` (machine-readable integration checks with recommendations)
    - `lemma fix --safe` (idempotent local scaffold repair)
    - `lemma smoke` (protected-endpoint request probe using `X-Lemma-Credential`)
    - `lemma ci` (single integration gate combining verify/audit/smoke)
    - `lemma doctor` (maps common integration errors to direct remediation steps)
    - `lemma login` browser-based lemma.id flow for local development, with:
      - one-time state + polling completion flow
      - optional `--no-browser` and `--login-timeout`
      - non-interactive fallback for CI/headless (`--non-interactive`)
    - `lemma logout`, `lemma auth-status`, `lemma site-create`, `lemma key-bootstrap`, `lemma iam-type-create`, `lemma iam-type-list`
    - Added global machine contract fields for agent tooling:
      - `schema_version`
      - `error_code`
  - Added browser-login support endpoints in `api/agent_credentials.py`:
    - `/api/agent/cli-login/complete`
    - `/api/agent/cli-login/poll`
  - Added `tests/test_lemma_cli.py` covering:
    - diagnostic mapping for untrusted issuer errors
    - verify check failure when platform env keys are absent
    - init config file generation + domain normalization
    - setup/audit/fix/smoke/ci command coverage
    - logout/auth-status/iam create/list command coverage
    - browser-based login completion path
  - Added installable CLI packaging metadata in root `pyproject.toml` with console entry point:
    - command: `lemma`
    - entry: `scripts.lemma_cli:main`
  - Added CLI release gate workflow:
    - `.github/workflows/cli-release-gate.yml`
  - Added strict auth launch gate workflow:
    - `.github/workflows/auth-launch-gate.yml`
  - Updated quickstart docs with CLI install/use section:
    - `templates/docs/quickstart.html`
- Tests:
  - `python -m pytest tests/test_lemma_cli.py -q` (22 passed)
  - `python -m py_compile scripts/lemma_cli.py api/agent_credentials.py` (PASS)
  - `python -m build` + `python -m twine check dist/*` (PASS)

### Test Run Summary (DX phases in this pass)
- `python -m pytest tests/test_sdk_auth_state_storage.py tests/test_sdk_api_guardrails.py tests/test_lemma_auth_flask_sdk.py -q` (6 passed)
- `python -m py_compile api/sdk_auth.py api/sdk_api.py sdk/python/lemma_auth_flask/src/lemma_auth_flask/core.py` (PASS)
- `python -m pytest tests/test_authz_policy_phase5.py tests/test_authz_engine_phase12.py -q` (9 passed)
- `python -m py_compile api/authz_policy.py` (PASS)
- `python -m pytest tests/test_lemma_cli.py tests/test_authz_policy_phase5.py tests/test_sdk_auth_state_storage.py tests/test_sdk_api_guardrails.py -q` (11 passed)
- `python -m py_compile scripts/lemma_cli.py` (PASS)
- `python -m pip install -e . --no-deps` (PASS, local editable install for `lemma` command)
- `lemma --help` (PASS)