# Evidence: Operator Drill Record

Date: 2026-02-15

## Drill set

- Revocation drill (`docs/OPENCLAW_REVOCATION_DRILL.md`)
- Key rotation drill (`docs/OPENCLAW_KEY_ROTATION_DRILL.md`)
- Incident/runbook path (`docs/OPENCLAW_OPERATOR_RUNBOOK.md`)

## Recorded outcomes in this session

- Deployment to production target succeeded (`lemma-enterprise`, release `v1717`).
- Core review suites observed full-pass under valid token window.
- Issuance-heavy conformance runs can be blocked by runtime limiter/session state.

## Follow-up operational recommendation

- Run drills during a clean limiter window with a fresh admin token.
- Attach command logs for:
  - issue -> validate -> revoke -> deny timing
  - key rotation overlap/cutoff checks
