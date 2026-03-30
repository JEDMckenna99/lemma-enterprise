# Lemma.id Launch Status: Ready Now vs In Progress

Last updated: 2026-03-04

## Ready Now

- Production launch-gate smoke checks pass against `https://lemma.id`.
- Post-deploy launch gate bundle passes for smoke, scope policy review, baseline proof-exchange checks, transport checks, and origin checks.
- Auth incident drill executed with measurable SLO evidence:
  - MTTD: 6s
  - MTTR: 10s
- CLI supports browser-based lemma.id login for local developer auth flows.
- Strict auth launch gate workflow added:
  - `.github/workflows/auth-launch-gate.yml`
- CLI release gate workflow added with Python version matrix:
  - `.github/workflows/cli-release-gate.yml`

## In Progress (GA Blockers)

- P0-1 Security controls sign-off:
  - formal security owner sign-off still required for non-PASS controls.
- P0-2 Manual critical auth flows:
  - browser/manual critical scenarios still need final evidence attachment.
- P0-4 Revocation deny-path in supported client matrix:
  - revoke -> sync -> deny evidence needs completion for all supported contexts.
- P0-5 Passkey algorithm/browser matrix:
  - compatibility matrix report pending.
- P0-6 Independent external security assessment:
  - report and remediation tracker pending.
- P0-7 Live alert-path escalation proof:
  - routing/escalation evidence for on-call path still needed.

## Evidence Index (Latest Run Set)

- `ops/evidence/launch/2026-03-04-114217-ga-launch-gate-smoke.txt`
- `ops/evidence/launch/2026-03-04-114520-post-deploy-summary.md`
- `ops/evidence/launch/2026-03-04-114534-incident-drill-auth-control-plane.md`

## Current Decision

- Current status: `NO-GO` for public GA declaration.
- Condition to switch to `GO`: all P0 gates in `docs/status/GA_GATE_STATUS.md` are marked `PASS` with attached evidence.
