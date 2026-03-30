# Agent Proof Ontology for Prompt-Injection Containment

## Purpose

Define a proof-native authorization model that treats prompt injection as a runtime trust downgrade.

Core principle:

- Authorization is not only "who is the agent" (`subject`), but also "what did it touch recently" (`trust_state`, `taint_epoch`).

This document is designed for self-serve operators implementing closed-loop automations (daily jobs, fixed workflows) and interactive agents.

---

## Decision Inputs (Required)

Every protected authorization decision MUST evaluate:

1. `subject`
   - PPID, runtime identity, agent identity.
2. `requested_action`
   - e.g., `fs.write`, `shell.exec`, `api.internal.admin`, `secrets.read`.
3. `trust_state`
   - Current contamination/risk state of runtime execution context.

---

## Trust States

Recommended trust-state ontology:

- `clean_internal`
  - Runtime has only touched trusted internal sources since last proof refresh.
- `mixed_context`
  - Runtime has touched both trusted and untrusted sources.
- `tainted_external`
  - Runtime has consumed untrusted web/docs/email/user/tool output.
- `privileged_reauth_required`
  - High-risk action attempted from tainted context; step-up required.

---

## Proof Claims (Required Fields)

Include these claims in proof payloads or runtime auth context:

- `scope`
  - Fine-grained permissions, e.g. `fs.read`, `fs.write`, `shell.exec`, `api.internal.read`, `api.internal.admin`.
- `resource_bounds`
  - Path/hostname/route/tool bounds for each scope.
- `trust_state`
- `taint_epoch`
  - Monotonic integer incremented when runtime consumes "hot" sources.
- `max_risk`
  - `low`, `high`, `critical`.
- `proof_ttl_s`
  - Keep short for privileged actions.
- `step_up_required`
  - Boolean gate for privileged actions after trust downgrade.
- `delegator_ppid`
- `runtime_id`

Critical anti-stale rule:

- A proof minted at `taint_epoch = N` MUST NOT authorize privileged actions once runtime state is at `taint_epoch = N+1`.

---

## State Transitions

### Hot events (downgrade triggers)

Any of these SHOULD bump trust state and increment `taint_epoch`:

- Arbitrary web fetch/read.
- Email/chat/user paste ingestion.
- Uploaded document parsing.
- Calls to non-allowlisted external APIs.
- Calls to internal "hot" endpoints returning mixed/untrusted content.
- Shell execution with arbitrary text output from external sources.

### Transition model

- `clean_internal` -> `mixed_context`
  - Trigger: low-risk external/user content enters context.
- `mixed_context` -> `tainted_external`
  - Trigger: arbitrary external content/instructions/tool output.
- `tainted_external` -> `privileged_reauth_required`
  - Trigger: runtime attempts high-risk action.
- `privileged_reauth_required` -> `clean_internal`
  - Trigger: fresh step-up proof OR isolated runtime reset/new execution context.

---

## Enforcement Rules

### 1) Default

- Deny privileged actions unless a current proof explicitly authorizes:
  - requested scope,
  - requested resource,
  - current `trust_state`,
  - current `taint_epoch`.

### 2) Filesystem

When `clean_internal`:

- Allow `fs.read` only on approved workspace paths.
- Allow `fs.write` only on approved project paths.
- Deny sensitive system/secret locations by default.

When `tainted_external`:

- Keep `fs.read` narrow.
- Downgrade writes to explicit path-scoped subsets.
- Deny write/delete/chmod/script-mutation unless step-up proof exists.

Suggested deny defaults:

- `%USERPROFILE%\\.ssh`
- `%APPDATA%`
- `.aws`
- `.npmrc`
- `.pypirc`
- browser profile/storage directories
- system folders
- deployment credentials and CI secrets

### 3) Shell

When `clean_internal`:

- Allow low-risk commands only if explicitly scoped.

When `tainted_external`:

- Deny generic shell exec by default.
- Allow only fixed wrappers/parameterized safe commands.
- Block network/process/package/archive/script-interpreter classes unless step-up.

### 4) Internal APIs

Separate internal scopes:

- `api.internal.read`
- `api.internal.write`
- `api.internal.admin`
- `api.internal.identity`
- `api.internal.secrets`

After hot exposure:

- `read` can remain available with strict resource bounds.
- `write/admin/secrets` require fresh step-up proof.

### 5) Secrets

- Never inherit `secrets.read` from normal content-read context.
- Always require step-up or very short TTL.
- Bind secret access to exact secret class and consuming tool.

---

## Scope Schema (Example)

```json
{
  "scope": [
    "fs.read",
    "fs.write",
    "api.internal.read"
  ],
  "resource_bounds": {
    "fs.read": ["/workspace/project/**"],
    "fs.write": ["/workspace/project/docs/**"],
    "api.internal.read": ["/api/wallet/runtimes/*"]
  },
  "trust_state": "clean_internal",
  "taint_epoch": 4,
  "max_risk": "low",
  "proof_ttl_s": 120,
  "step_up_required": false
}
```

Post-hot-event constrained proof:

```json
{
  "scope": [
    "fs.read",
    "api.internal.read"
  ],
  "resource_bounds": {
    "fs.read": ["/workspace/project/docs/**"],
    "api.internal.read": ["/api/wallet/runtimes/decisions/*"]
  },
  "trust_state": "tainted_external",
  "taint_epoch": 5,
  "max_risk": "high",
  "proof_ttl_s": 30,
  "step_up_required": true
}
```

---

## Hot Endpoint and Tool Policy

Label endpoints/tools:

- `cold`: trusted static metadata/config.
- `warm`: normal internal business data.
- `hot`: arbitrary/mixed/user-controlled/external content.

Rules:

- Any `hot` touch increments `taint_epoch`.
- High-risk scopes MUST re-check current `taint_epoch` and `trust_state` before execution.
- Proofs minted before the current epoch cannot authorize privileged actions.

---

## Decision Logic (Reference Flow)

1. Identify `runtime_id`, `delegator_ppid`, requested action, and target resource.
2. Load current runtime `trust_state` + `taint_epoch`.
3. Verify proof signature, expiry, PPID binding, audience/site/resource binding.
4. Verify proof epoch equals runtime epoch for privileged actions.
5. Verify scope includes requested action.
6. Verify resource is inside `resource_bounds`.
7. Apply risk policy:
   - If tainted and action is high-risk, require step-up.
8. Emit decision with machine-readable reason code.
9. Allow/deny.

---

## Reason Codes (Recommended)

- `deny_missing_scope`
- `deny_resource_out_of_bounds`
- `deny_taint_epoch_stale`
- `deny_trust_state_step_up_required`
- `deny_hot_context_fs_write_blocked`
- `deny_hot_context_admin_api_blocked`
- `deny_secret_access_requires_reauth`
- `deny_ambiguous_origin`
- `deny_runtime_killed`

---

## Operational Pattern

Preferred runtime pattern:

- Keep runtime process alive for normal operations.
- Mutate `trust_state` + `taint_epoch` on hot input.
- Require reauthorization for privileged actions.
- Optionally execute privileged step-up actions in isolated fresh context.

This pattern provides strong containment against prompt-injection carryover.

---

## Minimum High-Value Policy (MVP)

Implement these 5 rules first:

1. Any hot input marks runtime `tainted_external`.
2. Once tainted, old proofs cannot authorize `fs.write`, `shell.exec`, `secrets.read`, or `api.internal.admin`.
3. Privileged actions require fresh short-lived proof bound to current `taint_epoch`.
4. Filesystem stays path-scoped and blocks sensitive directories by default.
5. All denies log machine-readable reason codes + taint source.

