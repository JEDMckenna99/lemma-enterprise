# OpenClaw Product Hardening - 5 Item Execution With Evidence

Date: 2026-02-15  
Environment: Production (`https://lemma.id`)  
Deployment target: Heroku app `lemma-enterprise`

## 1) Principal-aware issuance limiter

Implemented:
- `auth/rate_limiter.py`
  - Added `get_issuance_identifier()` (principal-first keying, IP fallback)
  - Added differentiated issuance limits:
    - authenticated principal: `CREDENTIAL_ISSUE_LIMIT_AUTHENTICATED` (default `120 per hour`)
    - anonymous/IP fallback: `CREDENTIAL_ISSUE_LIMIT_ANONYMOUS` (default `20 per hour`)
  - Added `limit_scope` in 429 responses (`principal` or `ip`)
- `api/agent_credentials.py`
  - Applied keying to issuance endpoints:
    - `/api/agent/credentials/issue`
    - `/api/agent/auto-issue`

Evidence artifacts:
- `docs/launch-evidence/2026-02-15-rate-limiter-config-and-contract.md`
- `docs/launch-evidence/2026-02-15-rate-limiter-live-check.txt`

## 2) Auth contract consistency

Implemented:
- `api/agent_credentials.py`
  - deterministic validation path via `validate_agent_token_with_reason()`
  - machine-readable error codes surfaced by `/api/agent/validate`
- `mcp-server/index.js`
  - centralized `authorizeThenExecute` gate with explicit deny codes

Evidence artifacts:
- `docs/launch-evidence/2026-02-15-openclaw-conformance-run.txt`
- `docs/launch-evidence/2026-02-15-auth-contract-checklist.md`

## 3) SLO definitions + baseline capture

Implemented:
- SLO policy and thresholds for:
  - Auth availability
  - Revocation deny latency p95
  - Validation latency p95
- Baseline capture instructions and latest measured run references

Evidence artifacts:
- `docs/launch-evidence/2026-02-15-openclaw-slo-baseline.md`

## 4) 10-minute go-live path

Implemented:
- `scripts/openclaw_go_live_10min.ps1`
  - setup
  - token validation
  - review suite run
  - conformance run

Evidence artifacts:
- `docs/launch-evidence/2026-02-15-openclaw-go-live-flow.md`

## 5) Operator trust pack

Implemented:
- `docs/OPENCLAW_OPERATOR_RUNBOOK.md`
- `docs/OPENCLAW_REVOCATION_DRILL.md`
- `docs/OPENCLAW_KEY_ROTATION_DRILL.md`

Evidence artifacts:
- `docs/launch-evidence/2026-02-15-operator-drill-record.md`

## Notes

- Some live test runs remain dependent on runtime conditions:
  - valid admin token (`/api/agent/validate`)
  - wallet unlock state
  - issuance limiter windows
- Artifacts record observed outcomes and blockers with timestamps.
