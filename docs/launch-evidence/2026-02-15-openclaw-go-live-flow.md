# Evidence: 10-Minute Go-Live Flow

Date: 2026-02-15

## Script delivered

- `scripts/openclaw_go_live_10min.ps1`

## Flow steps

1. Configure token + MCP (`setup_openclaw.ps1`).
2. Validate token against `/api/agent/validate`.
3. Run OpenClaw review suites (`run_openclaw_review.ps1`).
4. Run standalone conformance pass (optional).

## Operator result expectation

- If token/session state is valid and not rate-limited, flow completes end-to-end in one command.
- If blocked, failure point is explicit (`invalid_token`, `wallet_unlock_required`, `rate_limit_exceeded`).
