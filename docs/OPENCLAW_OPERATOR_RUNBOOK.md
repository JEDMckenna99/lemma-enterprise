# OpenClaw Operator Runbook

## Purpose

Operate OpenClaw + Lemma.id delegation safely in production with deterministic auth outcomes.

## Preflight

- Confirm `LEMMA_AGENT_TOKEN` is valid (`/api/agent/validate` -> `valid: true`).
- Confirm `OPENCLAW_REQUIRED_AUDIENCE=openclaw` is set in runtime.
- Confirm wallet unlock is active for issuance workflows.

## Standard Validation Flow

1. Run:
   - `powershell -ExecutionPolicy Bypass -File scripts\openclaw_go_live_10min.ps1 -Token <lm_agent_...>`
2. Confirm:
   - `run-tests.js` passes.
   - `run-interaction-tests.js` passes.
   - Conformance matrix reports expected deny codes.

## Incident Triage

- `invalid_token` on preflight:
  - rotate/regenerate token from `https://lemma.id/developer`
  - rerun `setup_openclaw.ps1`
- `wallet_unlock_required` on issue:
  - complete wallet unlock flow once and retry
- `rate_limit_exceeded` on issue:
  - inspect `retry_after` and `limit_scope`
  - wait for window or reduce issuance churn

## Escalation Data to Capture

- Token ID (`jti`/token_id)
- Request path and method
- Error code
- `retry_after` and `limit_scope` (if rate-limited)
- Timestamp and environment
