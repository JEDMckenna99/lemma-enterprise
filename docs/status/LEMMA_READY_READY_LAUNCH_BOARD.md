# Lemma.id Ready-Ready Launch Board

## Current Launch Snapshot (2026-03-04)

- Gate status source: `docs/status/GA_GATE_STATUS.md`
- Ready-now vs in-progress summary: `docs/status/LAUNCH_READY_NOW_VS_IN_PROGRESS.md`
- Formal decision record: `docs/status/GA_DECISION_RECORD_2026-03-04.md`
- Current launch decision: `NO-GO` until all P0 gates are `PASS`

## A) Auth Core Canonicalization (Blocker)

### A1. Single authority source
- [ ] Define canonical admin authority model (one source of truth)
- [ ] Update read paths to use canonical source only
- [ ] Add migration/backfill for existing drifted records
- [ ] Add invariants test: no conflicting admin states

**Acceptance test**
- Same user/site returns identical auth decision across all relevant endpoints.

---

### A2. Issuance/listing consistency
- [ ] Patch self-issue/bootstrap flows to write canonical ownership
- [ ] Ensure `/api/developer/sites` reflects issued admin rights deterministically
- [ ] Add regression for reissue/transfer/recovery edge cases

**Acceptance test**
- Admin self-issue -> site list shows admin access -> protected endpoint allows.

---

### A3. Sensitive endpoint parity
- [ ] Inventory protected routes
- [ ] Enforce required checks on each: subject/site/scope/expiry/revocation
- [ ] Remove/disable fallback bypasses
- [ ] Standardize error codes/reasons

**Acceptance test**
- Conformance suite passes: allow valid, deny missing scope, deny revoked, deny wrong site.

---

## B) Product Modes & Packaging

### B1. Simple Mode (login-first)
- [ ] Define supported features: passkey sign-in + PPID + minimal server check
- [ ] Publish one “10-minute quickstart” (Node)
- [ ] Publish one “10-minute quickstart” (Python)

**Acceptance test**
- Fresh developer can sign in and protect one route within 10 minutes.

---

### B2. Secure Mode (control-plane)
- [ ] Define required controls: scoped claims, revocation, audit log
- [ ] Publish policy mapping examples (RBAC/scopes)
- [ ] Publish protected-action patterns (admin/action routes)

**Acceptance test**
- Fresh project can enforce scoped deny + revoke->deny on protected route.

---

## C) DevEx & Integrations

### C1. Verifier middleware package
- [ ] Stable package/versioning
- [ ] Minimal API surface
- [ ] Typed errors + reason codes
- [ ] Backward compatibility notes

**Acceptance test**
- Example apps use package without custom auth glue code.

---

### C2. Reference demos
- [ ] Demo 1: simple app sign-in + PPID
- [ ] Demo 2: protected action requiring secure mode checks
- [ ] Demo 3: revoke in dashboard -> immediate deny in app

**Acceptance test**
- Public demos run without manual patching and match docs.

---

### C3. Conformance kit
- [ ] CLI or script pack for:
  - [ ] valid allow
  - [ ] missing scope deny
  - [ ] wrong site deny
  - [ ] revoke->deny
- [ ] Output artifact format for support/debug

**Acceptance test**
- Run against prod/staging and archive artifacts per release.

---

## D) Reliability & Security Operations

### D1. Observability
- [ ] Auth decision logs (allow/deny + reason)
- [ ] Correlation IDs across request chain
- [ ] Revocation propagation metrics
- [ ] Dashboard for top deny reasons

**Acceptance test**
- Any auth incident can be traced in <15 min from logs.

---

### D2. Runbooks
- [ ] Key rotation runbook
- [ ] Revocation incident runbook
- [ ] Auth outage/degraded mode runbook
- [ ] Rollback runbook

**Acceptance test**
- Tabletop drill completed for each runbook.

---

### D3. Security baseline
- [ ] SECURITY.md + vulnerability intake process
- [ ] Secret scan/pre-push checks
- [ ] Dependency vulnerability gate
- [ ] Access review for prod credentials

**Acceptance test**
- Security checklist passes before each production release.

---

## E) Docs & Messaging

### E1. Homepage clarity
- [ ] Dev-first copy
- [ ] Explicit local-auth + server-enforcement model
- [ ] Separate Simple vs Secure mode messaging
- [ ] Proof links (tests, architecture, examples)

**Acceptance test**
- New dev can answer “what do I run client vs server?” without asking support.

---

### E2. Docs top-level rewrite
- [ ] Add deployment modes section
- [ ] Replace absolute claims with bounded claims
- [ ] Add sensitive-action checklist
- [ ] Add migration path Simple -> Secure

**Acceptance test**
- Internal reviewer can integrate from docs only.

---

## F) Launch Readiness & GTM

### F1. Release evidence
- [ ] Publish latest conformance artifact
- [ ] Publish known limitations
- [ ] Publish roadmap for next security hardening steps

**Acceptance test**
- Launch post includes evidence links, not just claims.

---

### F2. Channel launch kit
- [ ] HN post draft + first comment + FAQ replies
- [ ] Short demo video (simple + protected action)
- [ ] “What’s ready now vs in progress” page

**Acceptance test**
- Can answer top 10 skeptical questions with links/evidence.

---

## Exit Criteria (Go/No-Go)
- [ ] 0 open P0 auth bugs
- [ ] 14 days stable auth behavior in prod
- [ ] Conformance suite green on latest release
- [ ] Docs + demos match current behavior
- [ ] Incident runbooks tested once
