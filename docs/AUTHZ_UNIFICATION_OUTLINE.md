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
