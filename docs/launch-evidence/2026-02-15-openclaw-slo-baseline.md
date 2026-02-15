# Evidence: OpenClaw SLO Baseline

Date: 2026-02-15  
Target: `https://lemma.id`

## SLO definitions

1. **Auth availability**  
   Successful auth preflight responses over total auth preflight attempts.

2. **Revocation deny latency p95**  
   Time from revoke accepted to validate deny observed (critical path).

3. **Validation latency p95**  
   `/api/agent/validate` response latency under representative load.

## Baseline capture method

- `scripts/run_openclaw_review.ps1`
- `mcp-server/run-openclaw-conformance.js`
- targeted validate and revoke path checks

## Baseline notes (current session)

- Core review suites can pass fully with a valid token and non-throttled window.
- Conformance outcomes become issuance-window-dependent when repeated rapidly.
- Immediate operational action: keep issuance load below policy limits and prefer principal-scoped limiter keys.
