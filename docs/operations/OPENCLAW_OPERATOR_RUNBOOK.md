# OpenClaw Operator Runbook

## Purpose

Operate OpenClaw + Lemma.id delegation safely in production with deterministic auth outcomes.

## Platform Requirements

- Core onboarding commands are cross-platform Python CLI:
  - `lemma setup-openclaw --api-base https://lemma.id`
  - `python scripts/lemma_cli.py runtime-onboard ...`
- Validation steps 3-5 in this runbook currently require PowerShell scripts.
- Use Windows PowerShell or PowerShell Core (`pwsh`) on macOS/Linux for those checks.

## Self-Serve Operator Path (default)

This runbook is designed to be executable without manual support escalation:

1. Run setup:
   - `lemma setup-openclaw --api-base https://lemma.id`
2. Connect runtime:
   - `python scripts/lemma_cli.py runtime-onboard --api-base https://lemma.id --runtime-id openclaw-default --agent-id main --workspace-id default --json`
3. Validate proof + latency + auth:
   - `powershell -ExecutionPolicy Bypass -File scripts\run_openclaw_review.ps1 -LemmaUrl https://lemma.id`
4. Validate containment:
   - `powershell -ExecutionPolicy Bypass -File scripts\run_agent_ops_e2e.ps1 -LemmaUrl https://lemma.id`
5. Validate deny/revocation alert posture:
   - `powershell -ExecutionPolicy Bypass -File scripts\run_agent_ops_alerts_check.ps1 -LemmaUrl https://lemma.id -RuntimeId openclaw-default`

If any step fails, use the **Incident Triage** and **Escalation Data to Capture** sections before escalation.

## Mental Model (Operator)

- **Security identity (internal)**: PPID (`did:lemma:ppid_*`) is the enforcement key.
- **Business identity (external)**: customer-facing refs (`*_user_ref`) are for dashboards/audit/compliance.
- **Delegation**: human approves once, agent runs within scope/site/path bounds, runtime enforces every request.
- **Decision receipts**: allow/deny decisions include signed decision headers and decision metadata in audit trails.
- **Prompt injection containment**: runtime trust is dynamic; hot input downgrades trust and requires step-up for privileged actions.

## Prompt Injection Containment Ontology (Operator View)

Treat prompt injection as a runtime trust downgrade.

- Authorization inputs must include:
  - `subject` (PPID/runtime/agent)
  - `requested_action` (fs/shell/api/secrets class)
  - `trust_state` + `taint_epoch`

Recommended trust states:

- `clean_internal`
- `mixed_context`
- `tainted_external`
- `privileged_reauth_required`

Hot inputs/events (web/user paste/docs/unallowlisted APIs/mixed internal content) bump `taint_epoch`.

Critical rule:

- Proof minted at `taint_epoch=N` must not authorize privileged action once runtime is at `taint_epoch=N+1`.

Operationally, this means previously trusted context does not carry privileged authority after contamination.

Reference:

- `docs/security/AGENT_PROOF_ONTOLOGY_PROMPT_INJECTION.md`

## Preflight

- Confirm wallet unlock is active for issuance workflows.
- Confirm proof exchange works (`POST /api/auth/exchange-proof` with `X-Lemma-Credential`).
- Confirm OpenClaw runtime has:
  - `LEMMA_BASE_URL=https://lemma.id`
  - `LEMMA_PROOF_FILE=<path to proof json>`

## OpenClaw Quickstart (Proof-First Recommended)

1. Bootstrap proof path in seconds (wallet/browser-first):
   - `lemma setup-openclaw --api-base https://lemma.id`
   - (Optional) pass `-CredentialFile <proof.json>` if you already have one.
2. Connect OpenClaw runtime to wallet controls:
   - `python scripts/lemma_cli.py runtime-onboard --api-base https://lemma.id --runtime-id openclaw-default --agent-id main --workspace-id default --json`
3. Run proof-first review checks:
   - `powershell -ExecutionPolicy Bypass -File scripts\run_openclaw_review.ps1 -LemmaUrl https://lemma.id`
4. Confirm authz/audit signals:
   - `POST /api/auth/exchange-proof` succeeds.
   - AIM ingest (`/api/agent/monitor/log-external`) accepts `X-Lemma-Credential`.
5. Confirm audit attribution:
   - `GET /api/agent/credentials/audit` includes delegation identity (`delegated_by_ppid`) and external user refs (`*_user_ref`) when supplied.

## Standard Validation Flow (Proof-First)

1. Run:
   - `powershell -ExecutionPolicy Bypass -File scripts\setup_lemma_firewall_authz_seconds.ps1 -LemmaUrl https://lemma.id -CredentialFile <proof.json>`
   - `python scripts/lemma_cli.py runtime-onboard --api-base https://lemma.id --runtime-id openclaw-default --agent-id main --workspace-id default --json`
   - `powershell -ExecutionPolicy Bypass -File scripts\run_openclaw_review.ps1 -LemmaUrl https://lemma.id -CredentialFile <proof.json>`
2. Confirm:
   - Proof exchange succeeds.
   - `lemma_cli.py authz-latency --auth-mode proof` gate passes.
   - `lemma_cli.py login` and `lemma_cli.py auth-status` pass.

## Incident Triage

- `invalid_lemma_credential` on preflight:
  - re-run `lemma setup-openclaw --api-base https://lemma.id` to refresh proof file.
  - verify proof format and issuer trust chain.
- `wallet_unlock_required` on issue:
  - complete wallet unlock flow once and retry `authorize-agent`
- `rate_limit_exceeded` on issue:
  - inspect `retry_after` and `limit_scope`
  - wait for window or reduce issuance churn
- `invalid_ppid` on non-interactive self-issue:
  - use trusted wallet-issued credential flow (`--credential-file` / browser approval)
  - do not rely on email-only identity issuance in strict PPID mode
- `deny_taint_epoch_stale` / step-up deny:
  - runtime trust was downgraded after hot input
  - refresh proof with current taint epoch, or run privileged action in isolated fresh runtime context
- `deny_hot_context_fs_write_blocked` / `deny_hot_context_admin_api_blocked`:
  - action class is blocked in tainted context
  - reduce requested scope/resource, or obtain step-up proof
- break-glass root recovery flow needed:
  - use `scripts\setup_lemma_firewall_authz_seconds.ps1 -UseBreakGlassSelfIssue -PlatformApiKey <lemma_api_...> -UserEmail <admin@site>`
  - keep this path for emergency admin lemma recovery only, not day-to-day OpenClaw onboarding

## Escalation Data to Capture

- Proof ID (`proof_id`) and/or decision receipt (`X-Lemma-Decision-Id`)
- Request path and method
- Error code
- `retry_after` and `limit_scope` (if rate-limited)
- Timestamp and environment
- Decision receipt headers (`X-Lemma-Decision-Id`, `X-Lemma-Decision-Signature`)
- Delegation tuple:
  - `delegated_by_ppid`, `acting_for_ppid`, `requested_by_ppid`
  - `delegated_by_user_ref`, `acting_for_user_ref`, `requested_by_user_ref`

## Legacy Compatibility (Token/MCP)

- `X-Agent-Token` and MCP-based wiring are compatibility-only paths.
- Use only for break-glass or existing deployments that have not migrated.
- If needed, legacy checks remain available via:
  - `powershell -ExecutionPolicy Bypass -File scripts\run_openclaw_review.ps1 -UseLegacyToken`

## Secure Mode Flags (recommended for production)

- `LEMMA_WALLET_SECURE_MODE=1`
  - Tightens wallet-side defaults (session revocation degraded mode defaults to fail-closed).
  - Reduces allowed wallet transfer payload size unless explicitly overridden.
- `LEMMA_WALLET_TRANSFER_PLAINTEXT_ALLOWED=0`
  - Blocks transfer payloads containing sensitive wallet keys (`wallet_secret`, `secret`, etc.).
- `LEMMA_WALLET_TRANSFER_MAX_BYTES=131072`
  - Caps transfer payload size to reduce accidental over-sharing risk.

## Fast Demo Sequence (3PM-ready)

- `powershell -ExecutionPolicy Bypass -File scripts\run_agent_authz_demo_3pm.ps1 -LemmaUrl https://lemma.id`
- This executes: wallet link -> runtime connect -> runtime list -> runtime kill -> post-kill verification.
