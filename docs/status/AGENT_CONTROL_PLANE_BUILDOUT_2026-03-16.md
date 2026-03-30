# Agent Control Plane Buildout Status (2026-03-16)

## Scope delivered

This release completes the multi-phase Agent Control Plane buildout with compatibility preserved for existing runtime/openclaw paths.

Delivered capabilities:

- Typed root modes: `passkey_root`, `workload_root`, `policy_root`
- Tenant/environment partitioning: `org_id`, `environment`
- Policy profile lifecycle: create/update, publish, rollback, runtime version binding
- Runtime SDK hardening: freshness fail-closed checks (Node + Python)
- Runtime bootstrap hardening: root-mode and tenant targeting in CLI and firewall
- Canonical onboarding command path: `lemma runtime-onboard` (alias of `firewall-connect`) with env-backed tenant/root defaults
- Enterprise controls: org emergency stop/quota controls and decision webhook export
- Customer PoV loop runner with deterministic evidence output (`scripts/run_agent_ops_pov_loops.py`)
- Pilot release gate runner that combines local isolation tests and live drills (`scripts/run_pilot_release_gates.ps1`)
- Conformance and live-gate validation runbook coverage

## Key API surfaces

- Runtime bootstrap/list/kill/authorize
  - `/api/wallet/runtimes/bootstrap`
  - `/api/wallet/runtimes`
  - `/api/wallet/runtimes/<runtime_id>/kill`
  - `/api/wallet/runtimes/<runtime_id>/authorize`
- Policy lifecycle
  - `/api/wallet/runtimes/policies` (`GET`, `POST`)
  - `/api/wallet/runtimes/policies/<policy_profile_id>/publish` (`POST`)
  - `/api/wallet/runtimes/policies/<policy_profile_id>/rollback` (`POST`)
- Enterprise controls and export
  - `/api/wallet/runtimes/admin/controls` (`POST`)
  - `/api/wallet/runtimes/decisions/webhook` (`POST`)
- Freshness/revocation control plane
  - `/api/authz/revocation/delta`
  - `/api/authz/policy/snapshot`
  - `/api/authz/jwks`

## Validation summary

- Local/unit validations:
  - `tests/test_agent_control_plane_buildout.py`
  - `tests/test_agent_ops_enterprise_hardening.py`
  - `tests/test_authz_v2_controls.py`
- Live validation gates:
  - `scripts/run_agent_ops_e2e.ps1`
  - `scripts/run_agent_ops_alerts_check.ps1`
  - `scripts/revoke_to_deny_evidence.py`
  - `scripts/run_agent_ops_pov_loops.py`
  - `scripts/run_pilot_release_gates.ps1`
  - `scripts/post_deploy_launch_gate.ps1`

All above checks passed in the release run for this buildout.

## Post-deploy acceptance rerun (2026-03-17)

- Production deploy advanced to Heroku release `v1976` (commit `b101985d`).
- Practical acceptance gate re-run against `https://lemma.id` returned full PASS:
  - `docs/launch-evidence/2026-03-16-205726-pilot-release-gates.md`
  - `docs/launch-evidence/2026-03-16-205726-pilot-release-gates.json`
- PoV loops now pass end-to-end, including containment revoke-to-deny:
  - `docs/launch-evidence/2026-03-17-005738-agent-ops-pov-loops.md`
  - `docs/launch-evidence/2026-03-17-005738-agent-ops-pov-loops.json`
