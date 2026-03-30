# Agent Authz V1 Execution Plan

## Goal

Ship a narrow, sellable **agent authorization infrastructure** from the existing Lemma codebase in 2-4 weeks by hardening policy enforcement, standardizing SDK/CLI behavior, and tightening operational reliability.

## Product Scope (V1)

Expose only:

- Agent token issue/list/revoke/validate
- Middleware scope enforcement
- Revocation + audit visibility
- Site-scoped admin/user management
- One quickstart per SDK (Node + Flask)

Defer:

- Broad IAM positioning and non-core identity narratives
- Legacy compatibility auth paths for privileged routes in production
- Non-essential admin/bootstrap surfaces

## Execution Tracker

Status values: `Not Started`, `In Progress`, `Blocked`, `Done`.

| ID | Status | Owner | Target Week | Notes |
|---|---|---|---|---|
| P0-1 | Done | AI + Jed | Week 1 | Runtime policy enforcement active in `api/agent_credentials.py` and validated on live `lemma.id` routes. |
| P0-2 | Done | AI + Jed | Week 1 | Legacy privileged compatibility auth paths are now gated in `auth/decorators.py`; production defaults deny weak edge-header admin paths; validated live (`401` weak paths, `200` strong agent token path). |
| P0-3 | Done | AI + Jed | Week 1 | Unified scope checks/live principal policy checks validated; API key denied where route policy forbids principal type. |
| P0-4 | Done | AI + Jed | Week 1 | Added canonical revocation verifier in `api/revocation_verifier.py` and linked `api/trusted_issuers.py`, `api/permission_verification.py`, and `api/customer_accounts.py`; local regression tests pass and live smoke checks remain green. |
| P1-1 | Done | AI + Jed | Week 2 | Standardized Node + Flask middleware error contracts (`success/error/message`) in `sdk/node/lemma-auth-express/index.js` and `sdk/python/lemma_auth_flask/src/lemma_auth_flask/core.py`; contract tests now validate matching quickstart scenarios in `tests/test_lemma_auth_flask_sdk.py` and `tests/test_lemma_auth_node_sdk.py`. |
| P1-2 | Done | AI + Jed | Week 2 | Added typed Node SDK surfaces in `sdk/node/lemma-auth-express/index.d.ts`, exported via package metadata, and validated by compiling `tests/typescript/lemma-auth-express-smoke.ts` with `npx -p typescript tsc --noEmit`. |
| P1-3 | Done | AI + Jed | Week 2 | Updated `docs/api/AUTH_CONTRACT_V1.md`, `docs/api/DEVELOPER_AUTH_CONTRACT_V1.md`, `docs/integration/INTEGRATION_GUIDE.md`, and `docs/integration/QUICK_START_SIMPLE_LOGIN.md` to match runtime auth precedence/status semantics/error payloads; validated via live `launch_gate_smoke_ci.py` and strict `proof_exchange_contract_check.py` against `lemma.id`. |
| P1-4 | Done | AI + Jed | Week 2 | Added `lemma flow` non-interactive happy-path orchestration in `scripts/lemma_cli.py` (`setup -> login -> site-create -> issue -> validate`) with step-level machine error-code propagation; validated by `tests/test_lemma_cli.py` end-to-end flow coverage. |
| P0-5 | Done | AI + Jed | Week 3 | Redis degradation behavior is now deterministic across `auth/session_manager.py`, `auth/rate_limiter.py`, and `api/rate_limiter.py` with explicit degraded modes and local outage tests; deployed + live smoke verified (`restore-site-access` and admin stats remain `200`). |
| P1-5 | Done | AI + Jed | Week 3 | Replaced simulated health signals with runtime telemetry/dependency probes (`api/health_check.py`, `monitoring/request_telemetry.py`, `api/dashboard_api.py`); live authenticated checks now pass on `lemma.id` for `/api/admin/monitoring-summary` and `/api/health/detailed` using delegated admin token. |
| P1-6 | Done | AI + Jed | Week 3 | Strict launch-gate workflow now enforces Redis-degrade checks via `scripts/redis_degrade_gate_check.py`, `scripts/launch_gate_smoke_ci.py`, and `scripts/post_deploy_launch_gate.ps1`; live dry-run against `lemma.id` produced passing non-500 degraded-health evidence. |

### Current Sprint Focus

- Primary Goal: Completed - Week 3 evidence bundle finalized and strict post-deploy launch gate executed with key-required checks.
- Secondary Goal: Completed - revoke-to-deny propagation hard evidence captured for signoff package.
- Launch Blockers This Week: No authz execution-plan blockers remain; operational Redis volatility is mitigated by validated degraded-mode behavior.

## Readiness Verdict (Current)

**Verdict: Ready for pilot and paid design-partner rollout; not yet 10/10 self-serve GA UX.**

Why this is ready now:

- Runtime policy enforcement, revocation, and launch-gate checks are passing.
- Delegation attribution is now first-class (`delegated_by/acting_for/requested_by` with PPID + customer refs).
- Signed decision receipts are attached to auth allow/deny paths for auditable incident trails.

What still limits full self-serve GA UX:

- Issuance still depends on wallet unlock state (`wallet_unlock_required`) for strict delegation flows.
- Non-interactive self-issue is constrained in strict PPID mode (`invalid_ppid` for email-derived identity paths).
- Integrator docs should consistently present PPID as internal and `*_user_ref` as external business identity.

Recommended launch framing:

- **Now**: sell and run as secure agent-authorization control plane for serious teams (pilot + guided onboarding).
- **Next**: remove remaining UX friction with fully guided unlock/authorize flows and broader self-serve docs.

## Self-Serve 10/10 Outline (Live Tracker)

Status values: `Not Started`, `In Progress`, `Done`.

| ID | Initiative | Status | Current Progress | Next Concrete Step |
|---|---|---|---|---|
| SS-1 | First-class unlock session UX (`session start/status`) | Done | Added dedicated `lemma session start` and `lemma session status` commands, including browser launch support, lock/unlock detection, and unlock-time fields (`unlocked_at`, `expires_at`, `time_remaining`) when available. | Track real-world operator feedback for wording and optional polling ergonomics. |
| SS-2 | Identity surface split (PPID internal, user refs external) | Done | Delegation paths now carry both PPID and `*_user_ref` fields across CLI, issuance, validate, and audit outputs. | Add dashboard defaults to show `*_user_ref` first and PPID in advanced views. |
| SS-3 | Branch-complete guided remediation for auth failures | Done | Added one-command remediation shortcuts via `lemma doctor --fix` for top denial classes (`wallet_unlock_required`, `invalid_ppid`, `auth required/invalid`) with optional dry-run artifacts. | Track operator telemetry to prioritize the next remediation classes. |
| SS-4 | OpenClaw zero-ambiguity self-serve onboarding | Done | Added `lemma setup-openclaw` wrapper command to run verify -> authorize -> validate -> conformance (including dry-run and skip controls). | Collect operator feedback on default conformance command/timeouts and add one-shot troubleshooting mode. |
| SS-5 | Trust layer exports (decision receipts + incident bundle) | Done | Added `lemma incident-bundle` one-command export that captures timeline events, auth/session probes, and decision receipt headers from allow/deny probes into JSON + markdown artifacts. | Gather operator feedback on default probe set and retention/packaging format. |
| SS-6 | Near-zero authz latency path + evidence gate | Done | Added response-level authz latency headers (`X-Lemma-Authz-Latency-Ms`, `Server-Timing`), token fast-path cache (`LEMMA_AGENT_AUTH_FAST_PATH_TTL_MS`), Redis-backed operation quota counters (removing per-request DB writes), and async audit log write-behind. Live evidence on `v1886` shows `authz_p95_ms=1.52` and budget pass (<=5ms) on `/api/developer/sites`; evidence file: `ops/evidence/launch/2026-03-11-authz-latency-v1886.json`. | Enforce both authz and end-to-end spend budgets in CI via `lemma authz-latency --budget-p95-ms <authz_ms> --e2e-budget-p95-ms <e2e_ms>` and monitor p99 outliers. |

## Local-First Authz Refactor Outline

### Objective

Refactor to a hybrid model where the agent/runtime performs local authorization decisions on the hot path, while the Lemma control plane provides issuance, revocation/kill switch, policy freshness, and audit ingestion.

### Target architecture

- Data plane (hot path):
  - Local signature verification + claim checks (`scope`, `allowed_paths`, `allowed_sites`, `aud`, `exp`).
  - No per-request control-plane probe.
- Control plane:
  - Token issuance/rotation and key distribution (`jwks`).
  - Revocation and kill switch (`jti`/epoch-based invalidation).
  - Policy snapshot/version distribution.
  - Audit sink and incident evidence export.
- Freshness model:
  - Background revocation/policy sync (poll and optional push invalidation).
  - Risk-tier stale handling: low-risk local-only; high-risk requires recent freshness window.

### Minimum probing policy

- Per request: none (local-only).
- Background revocation delta: every 15-60s (default 30s).
- Policy/JWKS refresh: every 5-15m.
- High-risk route guardrail: deny or force refresh if freshness age exceeds threshold (for example 120s).

### Workstreams and code movement

1. Token + verifier contract

- Add capability token contract fields:
  - `jti`, `sub`, `aud`, `scope`, `allowed_paths`, `allowed_sites`, `exp`, `policy_version`, `rev_epoch`.
- Extract verifier into dedicated modules:
  - `api/authz/verifier.py` (server-side reference implementation)
  - SDK/runtime local verifier helpers for Node + Python.

2. Revocation/policy freshness services

- Add control-plane endpoints:
  - `GET /api/authz/jwks`
  - `GET /api/authz/revocation/delta?since=<cursor>`
  - `GET /api/authz/policy/snapshot?version=<v>`
- Add runtime freshness client:
  - Periodic pull + optional push invalidation channel.

3. Audit path hardening

- Keep async write-behind in server hot path.
- Add optional external batch ingest endpoint:
  - `POST /api/authz/decision-events/batch`
- Support idempotent retries for at-least-once delivery.

4. Route-risk policy split

- Classify routes into `low`/`medium`/`high`.
- Enforce freshness age checks only where required by risk.

### Migration plan

Phase 1 - Shadow parity

- Run local verifier in parallel with current path.
- Log and review decision diffs until parity threshold reached.

Phase 2 - Low-risk cutover

- Enable local-only decisions for read/list/lookup routes.
- Keep control-plane probes in background only.

Phase 3 - High-risk guarded cutover

- Enable local decisions for high-risk routes with strict freshness max-age.
- Keep one-shot live override for stale state.

Phase 4 - Decommission legacy hot-path dependencies

- Remove per-request DB introspection/writes from authz decision path.
- Keep emergency kill-switch override paths.

### Acceptance criteria

- Authz hot-path p95 <= 5ms on production target routes.
- Decision parity in shadow mode >= 99.99% before cutover.
- Revoke-to-deny SLA met (target <= 60s with background/push freshness).
- Dual spend gates pass in launch checks:
  - authz budget (`authz_p95_ms`)
  - end-to-end budget (`p95_ms`)
- Artifacts generated automatically in `ops/evidence/launch`.

## V2 Proof-Rooted Delegation Architecture

### Why this exists

V1 proves there is demand for delegated agent authorization and that the runtime hot path can be made fast and operationally reliable.

V2 should move the product back onto Lemma's stronger foundation: passkey-rooted user authority, signed proofs, local verification, revocation propagation, and explicit delegation bounds between nodes.

The goal is to stop treating agent access primarily as a database-backed bearer token problem and instead treat it as a delegated proof problem with optional compatibility tokens during migration.

### Product statement

Target product framing:

- **Passkey-rooted delegated authorization for agents**
- User-held root proof establishes authority window.
- Agent-held delegated proof narrows that authority for concrete actions.
- Runtime verifies proof chain locally for low-risk actions.
- Control plane handles issuance, revocation, policy freshness, audit ingestion, and step-up approval for high-risk actions.

### Core model

- Root authority:
  - User unlocks/authenticates with passkey on trusted Lemma wallet/session surface.
  - Lemma issues a root delegation proof bound to user PPID, device/session, site context, and validity window.
- Delegation:
  - Root proof can issue narrower child proofs to agents or runtimes.
  - Each child proof carries less or equal authority than its parent.
- Runtime enforcement:
  - Low-risk requests verify locally from proof chain + cached trust material.
  - High-risk requests require recent freshness or explicit step-up.
- Revocation:
  - Revoking any parent proof invalidates downstream delegated authority.
- Replay resistance:
  - Agent must prove possession of the bound key, not just present a copied artifact.

### Canonical artifacts

1. Root proof

- Issuer: `lemma.id` or explicitly trusted root issuer class
- Subject: user PPID / user node
- Purpose: establish delegated authority window after passkey approval
- Binds:
  - `root_grant_id`
  - `issuer`
  - `subject_ppid`
  - `device_key_id` or wallet/session binding
  - `site_binding`
  - `issued_at`
  - `expires_at`
  - `risk_ceiling`
  - `revocation_epoch`

2. Agent delegated proof

- Issuer: parent node in the chain
- Subject: agent node / agent key
- Purpose: authorize bounded agent action under user authority
- Binds:
  - `proof_id`
  - `parent_proof_id`
  - `root_grant_id`
  - `agent_id`
  - `agent_key_id`
  - `acting_for_ppid`
  - `requested_by_ppid`
  - `scope`
  - `allowed_sites`
  - `aud`
  - `risk_tier`
  - `issued_at`
  - `expires_at`
  - `delegation_depth`
  - optional `resource_actions`
  - optional `allowed_paths` as defense-in-depth compatibility

3. Request proof-of-possession envelope

- Sent with each agent request.
- Includes:
  - delegated proof or chain reference
  - request hash / nonce / timestamp
  - signature by the bound agent key
- Verifier checks that:
  - the presented proof is valid
  - the request is signed by the key bound in the proof
  - the request target/action is within the delegated bounds

### Verification contract

Runtime verifier must validate all of the following:

1. Root issuer trust:
   - chain begins at an allowed trust root for this product mode.
2. Signature validity:
   - each proof signature verifies against the issuer key.
3. Chain continuity:
   - parent subject equals child issuer or matches the defined delegation continuity rule.
4. Time validity:
   - all links are currently valid.
5. Revocation:
   - no proof in the chain is revoked.
6. Scope narrowing:
   - child scopes/resources are subsets of parent authority.
7. Site binding:
   - request site/domain matches bound site constraints.
8. Audience and action binding:
   - request target matches `aud` and authorized action set.
9. Delegation depth:
   - chain depth stays under configured hard limit.
10. Proof-of-possession:
   - request signer matches the bound agent key.

### Compatibility modes

To preserve adoption velocity, support explicit modes during migration:

- `compat_bearer`
  - current DB-backed `X-Agent-Token` flow
- `compat_proof_wrapped`
  - bearer token references a stored delegated proof record
- `proof_native`
  - runtime verifies delegated proof chain directly

The system should expose mode in audit and diagnostics so operators know whether a request was authorized under legacy bearer compatibility or proof-native enforcement.

### Risk-tier enforcement model

- `low`
  - local verification only
  - no per-request control-plane callback
  - ideal for read/list/search/inspection actions
- `high`
  - local verification plus freshness max-age
  - deny or refresh when revocation/policy state is stale
- `critical`
  - online freshness and/or explicit user step-up
  - required for destructive, irreversible, or externally visible actions

### Suggested claim shape

Illustrative delegated proof payload:

```json
{
  "version": "v2",
  "type": "delegation",
  "proof_id": "prf_123",
  "parent_proof_id": "prf_root_456",
  "root_grant_id": "grt_789",
  "issuer": "did:lemma:...",
  "subject": "did:lemma:agent:...",
  "subject_ppid": "did:lemma:ppid_...",
  "agent_id": "agent_openclaw_prod",
  "agent_key_id": "key_abc",
  "acting_for_ppid": "did:lemma:ppid_...",
  "requested_by_ppid": "did:lemma:ppid_...",
  "scope": ["sites:read", "sites:update"],
  "resource_actions": ["site.read", "site.update"],
  "allowed_sites": ["lemma.id"],
  "aud": "lemma.id",
  "risk_tier": "high",
  "delegation_depth": 1,
  "issued_at": 0,
  "expires_at": 0,
  "revocation_epoch": 1,
  "proof": {
    "alg": "Ed25519",
    "sig": "..."
  }
}
```

### Workstreams

1. Proof schema and verifier

- Extend trust-core verifier to support chain validation and proof-of-possession.
- Add canonical chain failure codes:
  - `AUTH_CHAIN_BROKEN`
  - `AUTH_PARENT_REVOKED`
  - `AUTH_PROOF_OF_POSSESSION_FAILED`
  - `AUTH_DELEGATION_DEPTH_EXCEEDED`
  - `AUTH_RISK_STEP_UP_REQUIRED`

2. Issuance surfaces

- Add root proof issuance after passkey approval.
- Add delegated proof issuance from root proof or approved parent proof.
- Keep current agent token issue path only as compatibility mode.

3. Runtime SDK/CDN parity

- Make server, Node, Python, and CDN verifier enforce the same trust contract.
- Eliminate trust drift between browser verifier and server verifier.

4. Revocation model

- Support revocation by `proof_id`, `root_grant_id`, and revocation epoch.
- Ensure child proofs are denied when any upstream ancestor is revoked.

5. CLI and browser flows

- Update CLI/browser login so they request delegated proofs, not only bearer tokens.
- Add clear operator visibility into proof mode, trust root, and step-up requirement.

### Rollout phases

Phase A - Proof shadow mode

- Keep current agent bearer token enforcement.
- Generate proof-native artifacts in parallel.
- Compare proof-native decisions against current runtime decisions.

Phase B - Proof-wrapped compatibility

- Issue current bearer tokens with attached proof references and proof metadata.
- Audit whether every bearer decision could be reconstructed from proof-native validation.

Phase C - Low-risk proof-native cutover

- Authorize low-risk requests from proof-native validation first.
- Keep bearer token as transport convenience only, not source of truth.

Phase D - High-risk and critical controls

- Require freshness and step-up on higher-risk routes.
- Deprecate legacy agent issuance paths that bypass passkey-rooted proof issuance.

Phase E - Bearer minimization

- Retain compatibility only where necessary for older integrations.
- Treat proof-native enforcement as the default product contract.

### Acceptance criteria

- Delegated requests can be traced to a root user authority grant.
- A copied proof artifact without the bound key fails request authorization.
- Parent revocation denies child authority within target propagation SLA.
- Server, CLI, SDK, and CDN verification produce the same allow/deny result for golden proof-chain fixtures.
- Low-risk proof-native authz remains within hot-path latency budget.
- High-risk and critical routes enforce freshness or step-up requirements deterministically.

### Protocol mode enforcement (anti-downgrade)

To prevent downgrade attacks during compatibility phases, the following are mandatory:

- Route mode is explicit and versioned:
  - `proof_required`
  - `compat_proof_wrapped`
  - `compat_bearer` (time-boxed only)
- `proof_required` routes:
  - Reject requests lacking valid proof + proof-of-possession (PoP) with `AUTH_PROOF_REQUIRED`.
  - If both bearer and proof are present, proof path is authoritative.
  - If proof fails, do not fallback to bearer (`AUTH_MODE_DOWNGRADE`).
- `compat_bearer` routes:
  - Allowed only on explicit route + tenant allowlist with a hard sunset date.
  - Requests after sunset are denied (`AUTH_COMPAT_MODE_EXPIRED`).
- Token/proof mode floor:
  - Include mode floor claim (`min_mode` or equivalent policy floor).
  - Any request evaluated below floor is denied (`AUTH_MODE_DOWNGRADE`).
- Audit visibility:
  - Emit `auth_mode_effective` and `auth_mode_expected` in every decision/audit event.

Required tests:

- Bearer-only call to `proof_required` route fails.
- Corrupt proof + valid bearer on `proof_required` route fails (no fallback).
- Compat route passes before sunset and fails after sunset.

### PoP replay contract

PoP envelope is required for proof-native authorization and must include:

- `nonce`
- `iat` and `exp` (or bounded timestamp fields)
- `method`, `path`, `body_hash`
- `aud`
- `proof_id`
- `agent_key_id`

Rules:

- Signature covers all PoP fields under canonical serialization.
- Default PoP TTL: 60s.
- Default clock-skew tolerance: +/-30s.
- Replay uniqueness scope: `(proof_id, nonce)` globally.
- Nonce store must be shared across verifier nodes (Redis or equivalent) using atomic `SETNX` + TTL.
- On nonce collision: deny (`AUTH_REPLAY_DETECTED`).
- On nonce-store outage:
  - `critical`/`high`: fail closed.
  - `low`: configurable short fail-open window with mandatory alert/event emission.

Required tests:

- Same signed request replayed twice -> second denied.
- Same nonce reused with changed path/body -> denied.
- Replay across two nodes in the fleet -> denied.

### Cross-runtime conformance contract

To eliminate trust drift across server/CLI/SDK/CDN verifiers, enforce a single versioned verification profile:

- Canonical profile: `authz_profile_v2` with:
  - claim schema
  - chain continuity algorithm
  - subset/narrowing rules
  - freshness rules by risk tier
  - deterministic error-code mapping
- Decision contract parity:
  - Every runtime emits the same result shape and reason codes:
    - `allow|deny`
    - `reason_code`
    - `proof_id`
    - `root_grant_id`
    - `policy_version`
- Parser strictness:
  - Unknown critical claims -> deny.
  - Duplicate claim keys -> deny.
  - Unsupported profile version -> deny.
- Golden fixture suite:
  - Positive and negative proof-chain fixtures must match exactly across all runtimes.
  - CI blocks release on any conformance drift.

Required tests:

- Same fixture across server, CLI, Node SDK, Python SDK, CDN verifier -> identical allow/deny + reason.
- Broken chain, parent revoked, stale freshness, PoP failure -> identical deny codes across runtimes.

### Baseline defaults (initial)

- PoP TTL: 60s
- Clock skew tolerance: +/-30s
- Freshness max-age by tier:
  - `low`: 120s
  - `high`: 30s
  - `critical`: <=10s + explicit step-up
- Compatibility bearer sunset:
  - Required explicit date + CI check that fails once expired.

## Competitive Positioning

### Where this model is stronger

Compared with typical agent auth/OAuth/MCP products, this model is stronger on:

- passkey-rooted user authority
- cryptographic delegation provenance
- local verification economics for low-risk actions
- PPID-style privacy boundaries
- replay resistance when proof-of-possession is enforced

### Where competitors are currently stronger

Current competitors are usually stronger on:

- standardized OAuth/OIDC/MCP packaging
- enterprise admin and consent UX
- mature external policy-engine integrations
- simpler centralized deployment stories

### Product implication

Lemma should not position this as only "agent token auth".

The stronger positioning is:

- **passkey-rooted delegated authorization for agents**
- **local-first proof verification with centralized issuance and revocation**
- **human authority preserved across agent action chains**

## Week 1 - P0 Security and Policy Lock

### P0-1 Centralize runtime policy enforcement

- Files:
  - `api/authz_engine.py`
  - `api/authz_policy.py`
  - `auth/decorators.py`
- Change:
  - Enforce `required_scope`, principal type, and site-binding in one runtime policy gate.
- Acceptance:
  - All protected routes enforce the policy map with no bypass-only decorator path.

### P0-2 Gate weak compatibility auth paths

- Files:
  - `auth/decorators.py`
- Change:
  - Put edge-trust admin compatibility paths behind explicit non-prod flag, default off in prod.
- Acceptance:
  - Privileged endpoints reject unsigned/compat header paths in production mode.

### P0-3 Scope consistency for all auth mechanisms

- Files:
  - `api/agent_credentials.py`
  - `auth/decorators.py`
- Change:
  - Apply `required_scope` consistently across agent token, lemma principal, and API key branches.
- Acceptance:
  - Auth matrix tests pass with identical allow/deny semantics by scope.

### P0-4 Canonical revocation verifier linkage

- Files:
  - `api/trusted_issuers.py`
  - `api/permission_verification.py`
  - `api/customer_accounts.py`
- Change:
  - Route all revocation checks through one canonical helper/verifier.
- Acceptance:
  - Revoked credentials are denied consistently across all auth entry points.

## Week 2 - P1 Integration and DX Stabilization

### P1-1 Golden-path SDK contracts

- Files:
  - `sdk/node/lemma-auth-express/index.js`
  - `sdk/python/lemma_auth_flask/src/lemma_auth_flask/core.py`
- Change:
  - Standardize one middleware flow and canonical error payloads.
- Acceptance:
  - Node and Flask quickstarts pass the same contract test scenarios.

### P1-2 Typed SDK surfaces

- Files:
  - `sdk/node/lemma-auth-express/index.d.ts` (new)
  - SDK package metadata/docs
- Change:
  - Publish typed option/result/error interfaces.
- Acceptance:
  - Example TypeScript app compiles without ad-hoc `any`.

### P1-3 Docs-runtime parity pass

- Files:
  - `docs/api/AUTH_CONTRACT_V1.md`
  - `docs/api/DEVELOPER_AUTH_CONTRACT_V1.md`
  - `docs/integration/INTEGRATION_GUIDE.md`
  - `docs/integration/QUICK_START_SIMPLE_LOGIN.md`
- Change:
  - Align status codes, auth precedence, and error code payloads with runtime.
- Acceptance:
  - Contract checks validate docs examples without drift.

### P1-4 CLI happy-path simplification

- Files:
  - `scripts/lemma_cli.py`
  - `tests/test_lemma_cli.py`
- Change:
  - Promote one flow (`setup -> login -> site-create -> issue -> validate`) and preserve upstream machine error codes.
- Acceptance:
  - Non-interactive CI CLI script works end-to-end.

## Week 3 - Reliability and Launch Gate

### P0-5 Redis degradation hardening

- Files:
  - `auth/session_manager.py`
  - `auth/rate_limiter.py`
  - `api/rate_limiter.py`
  - relevant app init paths
- Change:
  - Make degraded-mode behavior explicit and deterministic; avoid auth-route 500 spikes.
- Acceptance:
  - Redis outage test yields predictable auth behavior without cascading failures.

### P1-5 Truthful health and SLO metrics

- Files:
  - `api/health_check.py`
  - `api/dashboard_api.py`
  - `monitoring/request_telemetry.py`
- Change:
  - Replace simulated health checks with real dependency probes and production SLO counters.
- Acceptance:
  - Health/monitoring reflects actual DB/Redis/auth state.

### P1-6 Final launch gate strictness

- Files:
  - `.github/workflows/auth-launch-gate.yml`
  - `scripts/post_deploy_launch_gate.ps1`
  - auth matrix scripts
- Change:
  - Require strict auth matrix, docs parity, and Redis-degrade checks before release.
- Acceptance:
  - Pass/fail artifacts auto-generated and required for deployment approval.

## Exit Criteria (Ready to Charge)

- Zero critical policy bypasses on protected endpoints.
- Zero docs-runtime mismatch on primary integration path.
- Redis degradation does not trigger auth-route 500 spikes.
- 15-minute integration success path for Node and Flask.
- Revoke-to-deny behavior proven with evidence artifacts.

## Suggested PR Order

1. **PR1 Security Hardening**: P0-1, P0-2, P0-3, P0-4
2. **PR2 SDK/CLI DX**: P1-1, P1-2, P1-3, P1-4
3. **PR3 Reliability + Gates**: P0-5, P1-5, P1-6

