# Incident Drill Runbook

This runbook defines repeatable production-readiness drills for Lemma.id.

## Purpose

- Validate incident detection, escalation, mitigation, and communication.
- Produce measurable evidence for launch readiness.
- Confirm that auth-critical paths can be restored within target timelines.

## Frequency

- Run monthly, and before public launch.
- Re-run after major auth, billing, or deployment pipeline changes.

## Roles

- Incident Commander (IC): owns timeline and decisions.
- Operator: executes technical mitigation.
- Communications Lead: drafts stakeholder/customer updates.
- Observer: records timestamps and evidence.

## On-call escalation ladder

| Level | Condition | Who | Target response |
|---|---|---|---|
| L1 | `/health` down or single dyno crash | Primary on-call | 15 minutes |
| L2 | `/ready` failing or auth error spike | Primary + IC | 10 minutes |
| L3 | Data loss risk, KMS compromise, cross-tenant leak | IC + Security Lead | Immediate |
| L4 | Sustained customer-visible outage | IC + Communications Lead | Customer notice within 30 minutes |

Escalation contacts live in the secure operator roster (not in git). Alert routing rules: [`ALERT_CATALOG.md`](ALERT_CATALOG.md).

## Customer incident notification

When L2+ impact is customer-visible:

1. Communications Lead posts to `https://status.lemma.id` (investigating → identified → monitoring → resolved).
2. Email template in [`ALERT_CATALOG.md`](ALERT_CATALOG.md) for affected enterprise customers when contractually required.
3. Record customer impact class (`NONE` / `LOW` / `MEDIUM` / `HIGH`) in drill evidence.

Do not disclose exploit details or tenant-specific data in public status updates.

## Required Inputs

- Production base URL: `https://lemma.id`
- Access to GitHub Actions run history
- Access to Heroku logs and release history
- Current platform API key in secure operator context

## Evidence Artifacts

- Timeline log with UTC timestamps
- Detection source (alert/log/manual) and alert payload
- Mitigation actions performed
- Recovery verification outputs
- Final incident summary and follow-up actions

Store evidence under `ops/evidence/launch/` with a timestamped prefix.

---

## Scenario A: Auth Control-Plane Outage Drill

### Goal

Simulate and recover from an auth control-plane failure affecting access-token lifecycle checks.

### Trigger Condition (Simulated)

Pick one safe simulation method:

1. Temporarily use an invalid control-plane key in a staging-equivalent check command.
2. Temporarily block a dependency path used by token introspection/revocation in a controlled test window.
3. Simulate downstream timeout behavior in a non-destructive way (preferred for production drills).

Do not intentionally break production user auth flows. Use controlled blast radius.

### Execution Steps

1. Start drill timer and assign IC.
2. Confirm normal baseline:
   - Run strict auth gate checks.
   - Record baseline success outputs.
3. Introduce simulation trigger.
4. Validate detection:
   - Confirm alert fires (or monitoring detects condition).
   - Record detection timestamp.
5. Execute mitigation:
   - Revert simulated failure.
   - Verify token lifecycle path (`exchange`, `refresh`, `introspect`, `revoke`) returns expected responses.
6. Confirm recovery:
   - Re-run `Auth Launch Gate` workflow or equivalent post-deploy gate script.
   - Verify all auth checks pass.
7. End drill and produce summary.

### Pass Criteria

- Detection time (MTTD) <= 5 minutes
- Mitigation time (MTTR) <= 20 minutes
- Auth gate returns PASS after mitigation
- No unresolved regression remains

---

## Scenario B: Billing/Protected Endpoint Degradation Drill

### Goal

Simulate degraded behavior on protected billing/admin routes and verify enforcement plus recovery.

### Execution Steps

1. Start drill timer and assign IC.
2. Confirm baseline behavior:
   - `user_token -> /api/billing/usage/cus_test => 200`
   - `user_token -> /api/admin/platform-stats => 403`
   - `admin_token -> /api/admin/platform-stats => 200`
3. Introduce controlled degradation signal (non-destructive), such as dependency timeout simulation.
4. Validate alerting and error classification:
   - Confirm whether errors are auth failures, service failures, or upstream failures.
5. Perform mitigation and rollback simulation.
6. Re-run scope and contract checks.
7. Confirm final state equals baseline.

### Pass Criteria

- Access control boundaries remain intact during degradation.
- Degradation is detected and classified correctly.
- Recovery restores baseline behavior within 20 minutes.

---

## Drill Execution Template

Use this template per run:

- Drill ID: __________________
- Date/Time (UTC): __________________
- Scenario: `A` / `B`
- IC: __________________
- Operator: __________________
- Observer: __________________
- Detection Source: __________________
- MTTD: __________________
- MTTR: __________________
- Customer Impact: `NONE` / `LOW` / `MEDIUM` / `HIGH`
- Gate Re-run Result: `PASS` / `FAIL`
- Follow-up Actions:
  - __________________
  - __________________

## Post-Drill Required Actions

- File follow-up issues for gaps found.
- Assign owner and due date for each action.
- Update `docs/status/GA_LAUNCH_READINESS_CHECKLIST.md` P0-7 evidence with drill result.

## Automation Option

For the auth control-plane scenario, use:

- `scripts/run_incident_drill_auth.ps1`

This script runs baseline -> simulated failure -> recovery and writes a timestamped evidence file under `ops/evidence/launch/`.

For alert routing verification, use:

- `scripts/run_sentry_alert_routing_drill.py`
- `scripts/run_sentry_alert_routing_drill.ps1`

Required env vars for Sentry API polling:

- `SENTRY_DSN`
- `SENTRY_AUTH_TOKEN`
- `SENTRY_ORG`
- `SENTRY_PROJECT`

The PowerShell wrapper auto-reads `SENTRY_DSN` from Heroku (`lemma-enterprise` by default) and forwards credentials to the Python drill script.

