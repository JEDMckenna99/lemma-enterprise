# What Lemma Adds Beyond OpenClaw

OpenClaw runs the agent. Lemma governs and contains its authority.

## OpenClaw By Itself

OpenClaw is the runtime that executes agent work. It can provide prompts, tools, wrappers, and local execution behavior.

Those controls are useful, but they do not fully answer:

- what the agent is actually allowed to do right now
- how that authority is revoked quickly
- how to stop a runtime and prove it is denied
- how to explain why a protected action was allowed or denied
- how to scale the same controls into enterprise governance

## What Lemma Adds

### 1. Bounded authority

Lemma gives the runtime a signed, time-bounded authority object instead of relying only on prompts or prior approval state.

### 2. Per-action authorization

Protected actions are re-checked at action boundaries. The runtime is not trusted forever just because it was started earlier.

### 3. Runtime kill and containment

Lemma adds runtime registration plus a kill switch so privileged actions can be denied after the runtime is killed.

### 4. Revocation and freshness

Lemma can invalidate authority based on revocation, expiry, and runtime trust changes.

### 5. Decision visibility

Lemma records allow and deny decisions and can explain or export them for debugging, incident response, and audit.

### 6. Enterprise controls

Lemma adds org-wide controls like policy lifecycle, emergency stop, quotas, exports, and webhook delivery.

## Short Version

OpenClaw runs the agent.

Lemma answers:

- Is this runtime still allowed?
- Is this action still allowed?
- Can I revoke or kill it now?
- Can I explain what happened later?
