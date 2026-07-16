# Agent Ops Readiness (Lemma.id)

## Purpose

Define and track the minimum controls required to run proof-first agent authorization in production, with a real operator experience centered on Agent Ops.

This document is a build-and-test tracker: each item should have an owner, status, and evidence link.

---

## Scope note (2026-07-14)

This tracker covers **Agent Ops / proof-first authorization** only. It is
**not** the lemma.id GA launch gate sheet, see
[`docs/status/GA_GATE_STATUS.md`](status/GA_GATE_STATUS.md) for wallet/isHuman
P0 gates.

**Deploy gate of record for production pushes:** [`.github/workflows/auth-launch-gate.yml`](../.github/workflows/auth-launch-gate.yml)
(CSP pytest → auth scope matrix → deploy health → strict post-deploy launch gate
with `LEMMA_PLATFORM_API_KEY`). Agent Ops acceptance tests in this doc
supplement, but do not replace, that workflow.

Reconciled conflicts:

| Topic | Agent Ops stance | GA / isHuman stance |
| ----- | ---------------- | ------------------- |
| Deploy verification | `run_agent_ops_e2e.ps1`, pilot release gates | `auth-launch-gate.yml` on every `main` push |
| Proof enforcement rollout | `LEMMA_ENFORCE_PROOF_REQUIRED=0` default; shadow via `LEMMA_AUTHZ_PROOF_SHADOW=1` | Enable hard enforcement after client proof headers ship |
| IDV / demo scope | Out of scope here | Didit default at `/demo`; Stripe legacy only |
| Network revocation | Agent proof revocation via control plane | isHuman network-revoke retired (HTTP 410); site-block only |

---

## Product Direction (UX)

Move AIM under the Developer Platform and treat Agent Ops as the primary workflow.

- Primary UX: `Developer -> Agent Ops`
- Secondary UX: IAM/login concepts stay available but are not the default operator mental model
- Operator outcomes:
  - Connect runtime
  - Monitor activity
  - Kill/contain runtime or agent
  - Explain decisions and export evidence

### Target IA

- Agent Ops (default landing)
  - Runtimes
  - Live Activity
  - Kill Switches
  - Decision Log
- Policies
- Delegation
- Advanced IAM (secondary)

---

## Status Legend

- `todo`: not started
- `in_progress`: partially implemented or partially tested
- `done`: implemented and acceptance-tested with evidence
- `blocked`: cannot complete until dependency is resolved

---

## 1) Control Plane Readiness

The control plane defines who can run what, under which policy.

### Build Checklist

| Item | Status | Owner | Evidence |
|---|---|---|---|
| Runtime registry (runtime_id, agent_id, workspace, active/killed state) | done | platform | `api/services/wallet_service.py` + `scripts/run_agent_ops_e2e.ps1` (connect/list/kill/reconnect PASS on `https://lemma.id`) |
| Multi-root proof model (`passkey_root`, `workload_root`, `policy_root`) | done | platform | `api/services/wallet_service.py`, `api/authz/verifier.py`, `api/authz_control_plane.py` root-type issuance/verification/revocation support |
| Tenant/environment partitioning (`org_id`, `environment`) | done | platform | `migrations/022_agent_ops_workspace_schema.sql` + tenant-aware runtime/decision/revocation reads in store/service layers |
| Policy profile attachment per runtime | done | platform | Runtime payload includes `policy_profile` (`openclaw_default_v1`) in bootstrap/list responses |
| Policy lifecycle APIs (draft/update/publish/rollback) | done | platform | `GET/POST /api/wallet/runtimes/policies`, `POST /api/wallet/runtimes/policies/<policy_profile_id>/publish`, `POST /api/wallet/runtimes/policies/<policy_profile_id>/rollback` |
| Risk defaults (low/high/critical behavior) | done | platform | Runtime payload includes enforced `risk_defaults`; validated in live connect/list output |
| Kill switch controls (runtime-level and global) | done | platform | `api/services/wallet_service.py` (`/api/wallet/runtimes/<runtime_id>/kill`) + live E2E deny after kill |
| Org-level emergency stop + quota controls | done | platform | `POST /api/wallet/runtimes/admin/controls` updates org controls and runtime stop/quota state |
| Delegation records (delegator PPID, scope, bounds, expiry) | done | platform | `api/agent_ops_store.py` lineage enrichment + `tests/test_agent_ops_store_lineage.py`, `tests/test_agent_ops_enterprise_hardening.py` |
| Revocation registry for lemmas/proofs/tokens | done | platform | `api/authz_control_plane.py` shape mapping + `scripts/revoke_to_deny_evidence.py` (`ops/evidence/launch/2026-03-16-170427-revoke-to-deny-evidence.md`) |
| Decision webhook/SIEM export pipeline | done | platform | `POST /api/wallet/runtimes/decisions/webhook` (optional HMAC signature) |
| Agent Ops UI shows runtimes + kill controls | done | platform | `templates/wallet_simple.html` (OpenClaw runtimes + kill actions), validated in live wallet `/app` flow |

### Acceptance Tests

1. Create runtime -> runtime appears in list with expected policy profile.
2. Kill runtime -> new protected actions from that runtime are denied.
3. Re-enable or recreate runtime -> actions resume with policy defaults applied.

---

## 2) Data Plane Enforcement Readiness

The data plane enforces authorization on every protected request.

### Build Checklist

| Item | Status | Owner | Evidence |
|---|---|---|---|
| Proof required by default on sensitive routes | done | platform | `api/authz/mode_policy.py`, `scripts/lemma_firewall.py` (`AUTH_PROOF_REQUIRED` enforced) |
| Uniform verification middleware on protected endpoints | done | platform | `scripts/lemma_firewall.py` proof-first gateway path with runtime authorize gating |
| Signature validity checks | done | platform | `api/authz/replay.py` Ed25519 PoP verification + key binding |
| Subject binding (PPID) checks | done | platform | `api/services/wallet_service.py` (`_extract_ppid_from_lemma_header`, runtime authorize) deployed on `lemma.id` |
| Audience/site/resource binding checks | done | platform | `api/authz/verifier.py` (`aud` + resource bounds subset checks) |
| Scope/permission checks | done | platform | `api/authz/verifier.py`, `scripts/lemma_firewall.py` |
| Expiry/freshness checks | done | platform | `api/authz/verifier.py` time checks + freshness sync gates in firewall |
| Revocation checks | done | platform | `api/authz_control_plane.py` + firewall local cache (`proof_id`, `root_grant_id`, epoch) |
| Deny-by-default for ambiguous/missing context | done | platform | Deterministic deny codes in verifier/replay/mode policy |
| Legacy token path explicitly policy-gated and marked legacy | done | platform | Compat fallback only under mode policy + explicit gateway controls |

### Acceptance Tests

1. Valid proof + matching scope/site -> `ALLOW`.
2. Missing required scope -> `DENY` with reason code.
3. Wrong site/audience -> `DENY` with reason code.
4. Revoked proof/token -> `DENY` after propagation.

---

## 3) Revocation & Kill-Switch SLA

### Build Checklist

| Item | Status | Owner | Evidence |
|---|---|---|---|
| Defined revocation propagation SLA (`<1s` target, `<5s` hard max) | done | platform | `scripts/run_agent_ops_alerts_check.ps1` on `https://lemma.id` (`target_seconds=1.0`, `hard_max_seconds=5.0`, severity `ok`) |
| Deterministic revocation handling in request path | done | platform | `scripts/revoke_to_deny_evidence.py` proof-first drill PASS (`ops/evidence/launch/2026-03-14-210301-revoke-to-deny-evidence.md`) |
| Kill switch check before privileged execution | done | platform | `scripts/lemma_firewall.py` -> `/api/wallet/runtimes/<runtime_id>/authorize`, live PASS (`allow -> deny -> allow`) |
| SLA dashboard for revoke->deny and kill->deny | done | platform | `GET /api/wallet/runtimes/alerts/summary` + `scripts/run_agent_ops_alerts_check.ps1` live on `https://lemma.id` |

### Acceptance Tests

1. Start repeated protected calls at fixed interval.
2. Revoke proof/token while calls are in progress.
3. Confirm subsequent calls flip to deny within SLA.
4. Trigger runtime kill switch and confirm immediate deny.

---

## 4) Audit & Explainability Readiness

### Required Decision Log Fields

- timestamp
- runtime_id / agent_id
- delegator_ppid
- credential_ref (lemma/proof ID or hash)
- route/action
- decision (`allow` / `deny`)
- reason_code (machine-readable)
- policy_profile / policy_version
- request_correlation_id

### Build Checklist

| Item | Status | Owner | Evidence |
|---|---|---|---|
| Query decisions for runtime | done | platform | `GET /api/wallet/runtimes/decisions?runtime_id=...` (wallet-authenticated) |
| Query decisions for delegator PPID | done | platform | `GET /api/wallet/runtimes/decisions?delegator_ppid=...` constrained to caller PPID |
| Explain single decision from logs + policy snapshot | done | platform | `GET /api/wallet/runtimes/decisions/<decision_id>/explain` |
| Agent Ops UI displays runtime activity feed | done | platform | `templates/developer/platform.html` wires `GET /api/wallet/runtimes/decisions` + explain flow in Monitor & Controls |
| Exportable audit bundle for incident/review | done | platform | `GET /api/wallet/runtimes/decisions/export?format=json|csv` (`api/services/wallet_service.py`) + UI export actions |

### Acceptance Tests

1. Pick a denied request and reconstruct exact deny reason from logs.
2. Pick an allowed request and show policy/scope that allowed it.

---

## 5) Reliability & Runbooks

### Build Checklist

| Item | Status | Owner | Evidence |
|---|---|---|---|
| Authz latency SLO (p50/p95) | done | platform | `ops/evidence/launch/2026-03-13-161637-post-deploy-authz-latency.json` (`authz_p95_ms=0.445`) |
| Alerting on deny spikes and revocation lag | done | platform | `GET /api/wallet/runtimes/alerts/summary` (severity + thresholds), validated with `scripts/run_agent_ops_alerts_check.ps1` |
| Key rotation runbook | done | platform | `docs/operations/OPENCLAW_KEY_ROTATION_DRILL.md` exercised with conformance evidence (`docs/launch-evidence/2026-03-15-112500-p0-9-runbook-drills.md`) |
| False deny incident runbook | done | platform | `scripts/run_incident_drill_auth.ps1` PASS (`ops/evidence/launch/2026-03-15-112208-incident-drill-auth-control-plane.md`) |
| Revocation incident runbook | done | platform | `scripts/revoke_to_deny_evidence.py` PASS (`ops/evidence/launch/2026-03-15-152322-revoke-to-deny-evidence.md`) |
| Runtime kill/containment runbook | done | platform | `scripts/run_agent_ops_e2e.ps1`, `scripts/run_openclaw_local_first_e2e.ps1` |
| Rollback runbook | done | platform | Feature flags documented in firewall health + startup profiles |
| One-command onboarding reliability test (no proof file preexisting) | done | platform | isolated clean-state repeatability PASS (`docs/launch-evidence/2026-03-15-113600-clean-state-d-setup.txt`, `docs/launch-evidence/2026-03-15-113700-clean-state-e-setup.txt`) |
| Canonical runtime onboarding path (`runtime-onboard` alias) with tenant/root defaults | done | platform | `scripts/lemma_cli.py` (`firewall-connect` alias `runtime-onboard`) + env-backed defaults (`LEMMA_ORG_ID`, `LEMMA_ENVIRONMENT`, `LEMMA_ROOT_TYPE`) |
| Repeatable customer PoV loops with deterministic artifacts | done | platform | `scripts/run_agent_ops_pov_loops.py` -> `docs/launch-evidence/*-agent-ops-pov-loops.{json,md}` |
| Pilot release gates combining local tests + live drills | done | platform | `scripts/run_pilot_release_gates.ps1` (pytest matrix + e2e + alerts + PoV loops) |

### Acceptance Tests

1. Tabletop drill for each runbook completed.
2. Operator can resolve a simulated incident using docs only.

---

## 6) Security Boundaries (Explicit)

### Required Statements

- Local-first proof verification is used for performance/privacy where applicable.
- Sensitive operations are server-enforced.
- `wallet_id` is infrastructure-internal; relying parties should use PPID/claims, not global wallet identifiers.
- Legacy compatibility paths are policy-gated and monitored.

### Build Checklist

| Item | Status | Owner | Evidence |
|---|---|---|---|
| Public docs include boundary statements | done | platform | `docs/operations/OPENCLAW_OPERATOR_RUNBOOK.md` + this readiness tracker boundary section |
| Customer-facing APIs avoid leaking internal identifiers by default | done | platform | `api/services/wallet_service.py` OpenClaw runtime/decision responses omit `wallet_id` + `tests/test_agent_ops_enterprise_hardening.py` |
| PPID-first identity in Agent Ops/runtime responses | done | platform | `api/services/wallet_service.py` returns `ppid` across OpenClaw runtime/decision APIs |

### Acceptance Tests

1. Public docs include these boundary statements.
2. No public customer API leaks internal-only identifiers by default.

---

## 6.1) Prompt Injection Containment Ontology

Use trust-state-aware authorization for every privileged action.

### Required Runtime Fields

- `trust_state` (`clean_internal`, `mixed_context`, `tainted_external`, `privileged_reauth_required`)
- `taint_epoch` (monotonic)
- `step_up_required`
- `max_risk` (`low`, `high`, `critical`)

### Required Proof Claims

- `scope`
- `resource_bounds`
- `trust_state`
- `taint_epoch`
- `proof_ttl_s`
- `delegator_ppid`
- `runtime_id`

### Build Checklist

| Item | Status | Owner | Evidence |
|---|---|---|---|
| Trust-state transitions (`clean` -> `mixed` -> `tainted` -> `reauth`) defined and enforced | done | platform | Runtime trust-state checks enforced in `/api/wallet/runtimes/<runtime_id>/authorize` (`api/services/wallet_service.py`) |
| Hot-source events increment runtime `taint_epoch` | done | platform | Runtime taint epoch persisted in runtime schema and evaluated in authorize gate (`migrations/022_agent_ops_workspace_schema.sql`, `api/services/wallet_service.py`) |
| Privileged actions reject stale epoch proofs (`deny_taint_epoch_stale`) | done | platform | `api/services/wallet_service.py` + regression `tests/test_agent_ops_enterprise_hardening.py` |
| Tainted-context policy blocks high-risk scopes by default | done | platform | Privileged action checks enforce stale-epoch/step-up deny in tainted states (`api/services/wallet_service.py`) |
| Step-up proof flow for privileged action from tainted state | done | platform | `deny_trust_state_step_up_required` enforcement in runtime authorize gate + tests |
| Deny reason codes include trust/taint causes | done | platform | Decision logs include reason codes/taint metadata via `record_decision_logs` (`api/services/wallet_service.py`, `api/agent_ops_store.py`) |

### Acceptance Tests

1. Runtime consumes hot input -> `taint_epoch` increments.
2. Proof minted before epoch increment attempts privileged action -> `DENY` with stale-epoch reason.
3. Fresh step-up proof at current epoch allows explicitly bounded privileged action.
4. Decision logs include reason code, runtime_id, and taint metadata for denied requests.

---

## 7) Deployment Gate (Go/No-Go)

Declare production-ready only when all are true:

- [x] Proof-first path is default on protected routes
- [x] Conformance suite green (`allow_valid`, `deny_missing_scope`, `deny_wrong_site`, `revoke_to_deny`)
- [x] Revocation SLA demonstrated and documented
- [x] Kill switch validated on live runtime and visible in Agent Ops UI
- [x] Decision logs complete and queryable
- [x] Runbooks exercised at least once
- [x] Public docs match actual enforcement behavior
- [x] One-command onboarding works from clean machine state

---

## 8) Minimal Weekly Ops Cadence

- Daily: review deny reason distribution + authz errors
- Weekly: run conformance + revoke/kill drill
- Monthly: policy profile review + compatibility-path reduction

---

## 9) MVP vs Full Operational

### MVP Operational (minimum sellable)

- proof-first enforcement on core protected routes
- revoke->deny working
- runtime kill switch working
- decision logs with reason codes
- visual Agent Ops runtime control/monitor path works live

### Full Operational (enterprise-grade)

- complete endpoint parity
- strict legacy-path minimization
- formal SLOs + alerting
- repeatable incident drills and audit exports

---

## 10) Current Sprint Focus (fill each week)

| Priority | Task | Status | Owner | Evidence |
|---|---|---|---|---|
| P0 | Stabilize one-command wallet-first OpenClaw onboarding | done | platform | clean-state repeatability evidence + latency-smoke retry hardening in `scripts/setup_openclaw_authz_seconds.ps1` |
| P0 | Runtime control + monitor UI parity in `/app` Agent Ops | done | platform | `templates/wallet_simple.html` + live decision APIs (`/api/wallet/runtimes/decisions`, `/explain`) |
| P0 | E2E test: setup -> connect -> activity -> kill -> verify deny | done | platform | `scripts/run_agent_ops_e2e.ps1` PASS against `https://lemma.id` with live `/api/wallet/runtimes/<runtime_id>/authorize` gate |
| P1 | Alerts and SLA dashboard for revocation/deny spikes | done | platform | `scripts/run_agent_ops_alerts_check.ps1` PASS on `https://lemma.id` (release `v1915`) |
| P1 | Incident drill baseline/failure/recovery evidence | done | platform | `scripts/run_incident_drill_auth.ps1` PASS (`ops/evidence/launch/2026-03-14-180322-incident-drill-auth-control-plane.md`) |
| P0 | Practical acceptance gate rerun after production fix rollout | done | platform | `docs/launch-evidence/2026-03-16-205726-pilot-release-gates.md` (`Overall: PASS`), PoV loops `docs/launch-evidence/2026-03-17-005738-agent-ops-pov-loops.md` (`Loop A PASS`, `Loop B PASS`) |
