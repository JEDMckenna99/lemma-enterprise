# Human-Backed Authenticator Production Readiness

Execution checklist for preparing lemma.id to be sold as a production-grade,
human-backed authentication and account-continuity service.

This checklist complements:

- `docs/status/GA_GATE_STATUS.md`
- `docs/status/GA_LAUNCH_READINESS_CHECKLIST.md`
- `docs/security/SECURITY_CHECKLIST.md`
- `docs/security/HUMAN_AUTH_SECURITY_CONTRACT.md`
- `docs/integration/ISHUMAN_AGENT_INTEGRATION.md`
- `docs/status/P0_HUMAN_AUTH_FEATURE_FREEZE.md`

It does not replace those launch controls. The canonical relying-site contract
remains `docs/integration/ISHUMAN_AGENT_INTEGRATION.md`.

## How to use this document

- Use `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, or `PASS` for each section.
- A section is `PASS` only when every required item is complete and its exit
  criteria have reproducible evidence.
- Evidence should link to test output, a commit SHA, deployment result,
  screenshot, drill report, audit report, or dashboard.
- Do not approve production launch while any P0 item is incomplete.
- Update product claims to describe deployed behavior, not planned behavior.

## Product contract

The intended product is:

> Accounts rooted in a verified human, represented by site-private PPIDs,
> authenticated daily through passkeys, and recoverable through fresh human
> verification.

The assurance boundaries must remain explicit:

- A passkey proves control of an authorized wallet; it does not prove unique
  humanity by itself.
- `isHuman` is the IDV-backed assurance tier used when one verified human per
  account is required.
- A PPID is an opaque, site-private continuity identifier; it is not a legal
  identity or an authentication secret.
- Signup and account creation require server verification of a signed
  presentation. A bare client PPID is never sufficient.
- Fresh-passkey proof establishes current credential control for a sensitive
  action. It does not guarantee that an account can never be shared.

## Progress overview

| Workstream | Priority | Status | Owner | Evidence |
|---|---|---|---|---|
| 1. Security contract and threat model | P0 | `BLOCKED` | Security + Platform | Independent reviewer sign-off pending |
| 2. Wallet authority boundaries | P0 | `IN_PROGRESS` | Auth | Ceremonies shipped; browser matrix evidence remains for Section 2 PASS |
| 3. Tenant and site ownership | P0 | `PASS` | Platform | `api/site_access.py`, `api/domain_ownership.py`, `api/domain_transfers.py`, `migrations/042_section3_tenant_ownership.sql`, `tests/test_tenant_isolation_section3.py` |
| 4. Cryptographic trust chain | P0 | `NOT_STARTED` |  |  |
| 5. Revocation and replay protection | P0 | `NOT_STARTED` |  |  |
| 6. Human recovery | P0 | `NOT_STARTED` |  |  |
| 7. Secrets and API keys | P0 | `NOT_STARTED` |  |  |
| 8. Billing integrity | P0 | `NOT_STARTED` |  |  |
| 9. Operational reliability | P0 | `NOT_STARTED` |  |  |
| 10. SDK and integration productization | P1 | `NOT_STARTED` |  |  |
| 11. Independent assurance and compliance | P0 | `NOT_STARTED` |  |  |
| 12. Controlled launch | P0 | `NOT_STARTED` |  |  |

---

## 1. Freeze the security contract

- Priority: `P0`
- Status: `BLOCKED`
- Owner: Security + Platform
- Evidence:
  - `docs/status/P0_HUMAN_AUTH_FEATURE_FREEZE.md`
  - `docs/security/HUMAN_AUTH_SECURITY_CONTRACT.md`
  - `docs/api/AUTHORITY_OPERATIONS_V1.json`
  - `docs/security/THREAT_MODEL.md`
  - `docs/security/HUMAN_AUTH_THREAT_MODEL_SIGNOFF.md`
  - `docs/protocol/ISHUMAN_PROTOCOL_VERSIONS.json`
  - `docs/protocol/ISHUMAN_PROTOCOL_MIGRATION_POLICY.md`
  - `scripts/check_authority_operations.py`
  - `scripts/check_ishuman_protocol_registry.py`
  - `tests/test_authority_operations_contract.py`
  - `tests/test_ishuman_protocol_registry.py`
  - `tests/test_cryptographic_invariants.py`

- [x] Freeze nonessential product features until the P0 trust-boundary work is
      complete.
- [x] Document what passkey, isHuman, PPID, session, action stamp, and recovery
      proofs each establish.
- [x] Inventory every operation that creates or changes wallet, identity,
      tenant, billing, or recovery authority.
- [x] Assign a required authentication method and authorization policy to each
      operation.
- [x] Publish a threat model covering:
  - [x] Leaked wallet identifiers
  - [x] Lost or stolen devices
  - [x] Compromised passkeys
  - [x] Malicious relying sites
  - [x] Account sharing
  - [x] Cross-tenant attacks
  - [x] Replay and race conditions
  - [x] Database, Redis, KMS, IDV, and network outages
  - [x] Issuer and root-key compromise
- [x] Version every signed credential, presentation, convergence, revocation,
      and fresh-passkey protocol.
- [x] Define backward compatibility and credential migration rules before
      changing signed formats.

Exit criteria:

- [x] Every inventoried human-auth authority route has an explicit current and
      required authentication and authorization policy.
- [ ] Threat-model reviewers have signed off.
- [x] Protocol migration behavior is documented and contract-tested.

Validation baseline:

- `check_authority_operations.py`: PASS, 34 operations / 47 routes / 10
  declared implementation gaps.
- `check_ishuman_protocol_registry.py`: PASS, 14 registered artifacts.
- Contract tests: PASS, 11 tests.
- Cryptographic invariants: PASS, 8 tests.
- Strict generated scope review: PASS after classifying the action-sign
  redirect deposit and one-time claim as in-handler ceremony routes. Their
  current and required policies remain explicit in the authority inventory.
- Full non-live CI Regression: PASS locally, 1,113 passed and 4 skipped. The
  native `lemma_crypto` package builds and loads with Rust 1.97.1.

Blocking approval:

- `docs/security/HUMAN_AUTH_THREAT_MODEL_SIGNOFF.md` requires a named,
  independent reviewer and an `APPROVED` decision. Section 1 must not be marked
  `PASS` before that record is complete.

---

## 2. Rebuild wallet authority boundaries

- Priority: `P0`
- Status: `IN_PROGRESS`
- Owner: Auth
- Evidence:
  - `api/wallet_session_sync.py`
  - `api/wallet_authn.py`
  - `auth/redis_store.py`
  - `static/js/lemma-wallet.js` 2.76.0
  - `docs/security/WALLET_COOKIE_SAMESITE.md`
  - `tests/test_wallet_session_sync_security.py`
  - `tests/test_wallet_authn.py`
  - `tests/test_wallet_sync_device.py`
  - `tests/test_wallet_link_receive.py`

- [x] Remove wallet-ID-only authorization from `init-first-session` and
      `signal-unlock`, or disable those routes until secure replacements exist.
- [x] Require verified WebAuthn before creating the first trusted wallet
      session.
- [x] Require an existing authorized device signature, verified WebAuthn
      ceremony, or completed human-recovery ceremony before enrolling another
      signing key.
- [x] Never treat `wallet_id`, a client timestamp, or an `Origin` header as
      proof of wallet control.
- [x] Define separate, auditable ceremonies for:
  - [x] First-device enrollment
  - [x] Daily passkey unlock
  - [x] Additional-device enrollment
  - [x] Device revocation
  - [x] Lost-device recovery
- [x] Bind every challenge to wallet, device, origin, purpose, nonce, and
      expiration.
- [x] Prevent attacker-enrolled devices from satisfying multi-device recovery
      or master-reissue policy.
- [x] Correct hostname suffix checks so only the exact domain or a real
      subdomain is accepted.
- [x] Require CSRF protection on cookie-authenticated wallet mutations.
- [x] Review and minimize `SameSite=None` cookies.
- [x] Add negative tests for forged Origin, known wallet ID, unapproved device,
      replayed challenge, and cross-site mutation attempts.

Exit criteria:

- [x] Knowing a wallet ID cannot create a session, enroll a device, reissue a
      master credential, derive a site proof, or revoke credentials.
- [x] First-device, additional-device, and recovery ceremonies pass adversarial
      tests.
- [x] No wallet mutation relies solely on ambient cookies without CSRF defense.

Validation baseline:

- Adversarial wallet authority suite: PASS with first-device enroll,
  cross-device revoke, and lost-device recovery coverage.
- Wallet SDK 2.76.0 / cache 2687 and CDN mirror synchronized.
- Authority contract includes `wallet.device.lost_device_recovery`.
- Strict generated scope review: PASS after classifying recovery routes.
- Full non-live CI Regression: PASS, 1,124 tests with 4 skips.

Remaining blockers:

- Staging deploy + browser matrix evidence:
  `docs/status/SECTION2_STAGING_BROWSER_MATRIX.md`
  and `scripts/run_section2_staging_matrix.py`.
- Section 6 still owns broader IDV binding, notification, and emergency
  suspension hardening beyond the wallet recovery ceremony.
- Auth owner marks Section 2 `PASS` after browser matrix evidence is attached.
  Keep Section 1 `BLOCKED` until independent threat-model sign-off.

---

## 3. Enforce tenant and site ownership

- Priority: `P0`
- Status: `PASS`
- Owner: Platform
- Evidence:
  - `api/site_access.py` (`authorize_site_access`)
  - `api/domain_ownership.py`
  - `api/domain_transfers.py`
  - `api/audit_api.py`
  - `api/stripe_usage_billing.py`
  - `api/customer_accounts.py`
  - `api/permission_type_api.py`
  - `migrations/042_section3_tenant_ownership.sql`
  - `tests/test_tenant_isolation_section3.py`
  - `tests/test_site_access_enforcement.py`

- [x] Create one authoritative site-ownership authorization function.
- [x] Apply it to audit, billing, site-user, block, doubt, revocation, API-key,
      and site-management operations.
- [x] Bind requested `site_id` values to the authenticated principal instead
      of trusting request parameters.
- [x] Add database-level tenant isolation to the tables containing customer or
      site data.
- [x] Set and clear tenant database context safely for every connection.
- [x] Require DNS or `/.well-known/` domain ownership verification.
- [x] Prevent site registration from overwriting an existing customer's
      hostname, administrator, API key, issuer, or billing association.
- [x] Implement an explicit, audited domain-transfer process.
- [x] Add tests proving tenant A cannot read, export, modify, block, revoke, or
      administer tenant B.

Exit criteria:

- [x] Every site-scoped operation is bound to verified site ownership.
- [x] Cross-tenant negative tests cover both application authorization and
      database isolation.
- [x] Existing-domain registration returns a conflict unless an approved
      transfer is in progress.

Validation baseline:

- `tests/test_tenant_isolation_section3.py`: PASS (audit, billing, API keys,
  register-site conflict, domain verification gate, API-key site binding).
- `authorize_site_access` wired to audit, billing checkout, customer API keys,
  permission APIs; isHuman block/doubt remain API-key-bound via shared resolver.
- Domain verification + transfer REST: `/api/customer/domain-verification/start`,
  `/api/customer/domain-transfers` (+ accept/cancel).
- RLS policies on `sites`, `site_admins`, `site_users`, `site_blocks`,
  `site_doubts` via `SET LOCAL app.current_site_id` (`api/database.py`).

---

## 4. Stabilize the cryptographic trust chain

- Priority: `P0`
- Status: `NOT_STARTED`
- Owner:
- Evidence:

- [ ] Establish an offline or independently controlled network root key.
- [ ] Pin the root public key in Browser, Python, and Node verifiers.
- [ ] Define normal rotation, overlapping trust, emergency rollover, and
      compromise response.
- [ ] Include the revocation identifier in the signed credential message.
- [ ] Require credential ID, issuer, subject, site binding, issuance time,
      expiration, assurance, and proof fields.
- [ ] Define canonical bytes for every signed artifact.
- [ ] Repair Node trust-list parsing and signature verification.
- [ ] Repair Node Bloom content hashing, signature message construction, and
      signature decoding.
- [ ] Repair Node PPID-convergence trusted-key iteration.
- [ ] Make assurance ordering identical across Browser, Python, and Node.
- [ ] Generate shared positive and negative protocol test vectors.
- [ ] Verify real server-generated artifacts with every supported verifier.
- [ ] Define immutable protocol fixtures so wire-format drift fails CI.

Exit criteria:

- [ ] Browser, Python, and Node produce identical decisions for every shared
      test vector.
- [ ] Replacing a trust-list response with an attacker self-signed list fails.
- [ ] A modified credential identifier, site binding, subject, expiry, or
      assurance fails verification.
- [ ] Root rotation succeeds under documented overlap and emergency scenarios.

---

## 5. Make revocation and replay protection fail closed

- Priority: `P0`
- Status: `NOT_STARTED`
- Owner:
- Evidence:

- [ ] Return an unavailable response when revocation data cannot be read.
- [ ] Never sign an empty fallback snapshot after a database or hashing error.
- [ ] Remove plaintext-ID fallback from revocation snapshot generation.
- [ ] Check signed credential, PPID, and wallet revocation candidates
      consistently in every verifier.
- [ ] Reject stale, malformed, untrusted, or unavailable revocation data.
- [ ] Make service readiness depend on initialized, fresh revocation state.
- [ ] Validate all action signatures and bindings before consuming their nonce.
- [ ] Make distributed nonce consumption atomic.
- [ ] Await asynchronous Redis operations in Node.
- [ ] Require a durable distributed nonce store for production mutations.
- [ ] Test replay across processes, workers, restarts, and regions.
- [ ] Test database, Redis, and network failures for fail-closed behavior.

Exit criteria:

- [ ] Revoked credentials, PPIDs, and wallets are rejected by every supported
      verifier.
- [ ] A valid action can succeed once and only once.
- [ ] Revocation infrastructure failure cannot produce a fresh valid
      "nothing revoked" assertion.

---

## 6. Harden human recovery

- Priority: `P0`
- Status: `NOT_STARTED`
- Owner:
- Evidence:

- [ ] Bind IDV completion to the initiating wallet, site, API key, user, and
      one-time server record.
- [ ] Atomically consume recovery tokens before credential issuance.
- [ ] Require proof of control of the replacement passkey.
- [ ] Bind recovered identity to the canonical person root.
- [ ] Update only the exact intended account and administrator record.
- [ ] Remove fallback behavior that updates the first matching owner or admin.
- [ ] Define recovery behavior when document schema, document renewal,
      identity provider, or root-key versions change.
- [ ] Preserve the same canonical PPID when the same person recovers for the
      same site.
- [ ] Verify and transact PPID convergence when a provisional identity becomes
      canonical.
- [ ] Notify users and site administrators of recovery events.
- [ ] Provide an emergency suspension path for disputed recovery.
- [ ] Test concurrent token use, stolen links, compromised email, disclosed
      session IDs, malicious devices, and provider callback replay.

Exit criteria:

- [ ] A verified person can recover the correct account on a new device.
- [ ] Email access, a wallet ID, or a copied IDV session identifier alone
      cannot complete recovery.
- [ ] Concurrent recovery attempts issue at most one replacement authority.

---

## 7. Consolidate secrets and API keys

- Priority: `P0`
- Status: `NOT_STARTED`
- Owner:
- Evidence:

- [ ] Replace overlapping key stores with one authoritative API-key system.
- [ ] Store verification-only API keys as hashes.
- [ ] Encrypt secrets that must be recovered using KMS.
- [ ] Remove plaintext `Site.api_key` and OAuth client-secret storage.
- [ ] Stop copying validated customer keys into plaintext compatibility fields.
- [ ] Remove API-key query-parameter authentication.
- [ ] Ensure key revocation is authoritative across every endpoint.
- [ ] Support controlled overlap during key rotation.
- [ ] Migrate and rotate all existing production keys after cutover.
- [ ] Fail production startup when required secrets are missing or weak.
- [ ] Require distinct Flask, wallet-session, billing, pepper, root, and signing
      secrets.
- [ ] Verify KMS key policies, encryption contexts, rotation, and audit logs.

Exit criteria:

- [ ] A database dump does not expose reusable customer authentication
      credentials.
- [ ] A revoked API key fails every authentication path immediately.
- [ ] Production cannot start with development fallback secrets.

---

## 8. Make billing financially reliable

- Priority: `P0`
- Status: `NOT_STARTED`
- Owner:
- Evidence:

- [ ] Require registered, ownership-verified production sites.
- [ ] Require an active billing entitlement before production issuance.
- [ ] Keep demos and sandbox exemptions explicit and isolated.
- [ ] Never mark dry-run or skipped billing events as reported.
- [ ] Make Stripe meter events idempotent.
- [ ] Resolve the Stripe customer at retry time or permanently reject
      unresolvable events.
- [ ] Deploy a durable outbox worker.
- [ ] Add bounded retries, backoff, dead-letter state, and queue-age alerts.
- [ ] Persist Stripe webhook event IDs transactionally.
- [ ] Reconcile internal aggregates, outbox rows, Stripe events, and invoices.
- [ ] Provide customer-visible usage and entitlement status.
- [ ] Test missing key, Stripe outage, duplicate webhook, worker crash, and
      late registration scenarios.

Exit criteria:

- [ ] Every billable issuance is either reported exactly once or remains
      visibly pending for remediation.
- [ ] No unregistered production site can consume unmetered issuance.
- [ ] Reconciliation detects both missing and duplicate usage.

---

## 9. Build operational reliability

- Priority: `P0`
- Status: `NOT_STARTED`
- Owner:
- Evidence:

- [ ] Add an atomic, advisory-locked production migration process.
- [ ] Fail migrations on checksum drift.
- [ ] Run migrations as an explicit release step.
- [ ] Configure automated database backups and point-in-time recovery.
- [ ] Define recovery point and recovery time objectives.
- [ ] Complete and record database and critical-state restore drills.
- [ ] Add centralized metrics, logs, traces, and durable audit records.
- [ ] Alert on authentication, issuance, IDV, recovery, revocation, KMS,
      database, Redis, and billing failures.
- [ ] Monitor queue age and revocation freshness.
- [ ] Separate liveness from dependency-aware readiness.
- [ ] Load-test verification, issuance, IDV callbacks, recovery, revocation,
      and site administration.
- [ ] Define behavior for dependency and regional/provider outages.
- [ ] Publish a customer-facing status page.
- [ ] Establish on-call escalation and customer incident notification.
- [ ] Automate all promised data-retention and deletion jobs.

Exit criteria:

- [ ] A measured restore drill meets the documented objectives.
- [ ] Dependency-failure exercises produce the intended fail-closed or
      degraded behavior.
- [ ] Alerts reach the responsible operator and link to a tested runbook.
- [ ] SLA claims match measured capabilities.

---

## 10. Productize SDKs and integrations

- Priority: `P1`
- Status: `NOT_STARTED`
- Owner:
- Evidence:

- [ ] Publish tested npm and PyPI verifier packages.
- [ ] Provide immutable, versioned browser and backend SDK URLs.
- [ ] Publish integrity hashes for browser assets.
- [ ] Establish one version source of truth.
- [ ] Publish a compatibility matrix and deprecation policy.
- [ ] Support Next.js/Express and Flask/FastAPI integrations first.
- [ ] Ensure framework adapters consume verifier results without unsafe
      placeholder callbacks.
- [ ] Publish accurate OpenAPI contracts for relying-site APIs.
- [ ] Provide production examples using durable policy and nonce stores.
- [ ] Remove stale demos, unsafe in-memory production patterns, and conflicting
      version numbers.
- [ ] Automate package publication and release notes.

Exit criteria:

- [ ] A new relying site can install a supported package and complete T2 signup
      without copying internal code.
- [ ] Published examples fail closed and pass integration tests.
- [ ] SDK versions and protocol compatibility are unambiguous.

---

## 11. Complete independent assurance and compliance

- Priority: `P0`
- Status: `NOT_STARTED`
- Owner:
- Evidence:

- [ ] Complete an independent cryptographic architecture review.
- [ ] Complete an external penetration test covering wallet, passkeys,
      recovery, tenants, presentations, revocation, site controls, and billing.
- [ ] Close and retest all critical and high findings.
- [ ] Record risk acceptance and remediation plans for remaining medium
      findings.
- [ ] Complete Chrome, Safari, Firefox, Android, and iOS passkey matrices.
- [ ] Add dependency scanning, secret scanning, SAST, coverage thresholds, and
      release provenance to required CI.
- [ ] Establish a vulnerability disclosure or bug-bounty program.
- [ ] Complete data-flow and data-retention inventories.
- [ ] Publish a DPA, subprocessor list, deletion/export procedures, and incident
      notification commitments.
- [ ] Gather SOC 2 or equivalent control evidence required by target buyers.
- [ ] Review every privacy, zero-knowledge, uniqueness, recovery, and uptime
      claim for technical accuracy.

Exit criteria:

- [ ] Independent reviewers approve the deployed implementation.
- [ ] No unresolved critical or high security finding remains.
- [ ] Procurement and privacy artifacts accurately describe actual data
      handling.

---

## 12. Launch progressively

- Priority: `P0`
- Status: `NOT_STARTED`
- Owner:
- Evidence:

Complete these stages in order:

1. [ ] Internal adversarial testing
2. [ ] Human-assurance add-on alongside existing customer authentication
3. [ ] Controlled paid pilots
4. [ ] Human-backed enrollment and PPID continuity pilots
5. [ ] Primary authentication and recovery pilots
6. [ ] General availability

Pilot controls:

- [ ] Named relying parties only
- [ ] Explicit beta terms and rollback plan
- [ ] Existing customer authentication retained until primary-auth approval
- [ ] Immediate incident and revocation contacts
- [ ] Monitored issuance, verification, recovery, and billing
- [ ] No unresolved critical or high security findings

Pilot measurements:

- [ ] Duplicate accounts prevented
- [ ] False rejection rate
- [ ] Signup completion rate
- [ ] Passkey enrollment and authentication success
- [ ] Recovery completion and dispute rate
- [ ] Revocation propagation
- [ ] Verification and issuance availability and latency
- [ ] Support volume and incident severity

Exit criteria:

- [ ] Pilot results satisfy documented acceptance thresholds.
- [ ] Rollback and incident procedures have been exercised.
- [ ] Primary authentication is enabled only after the human-assurance pilot is
      stable and independently reviewed.

---

## Final production gate

Production-grade approval requires every item below:

- [ ] All P0 sections in this checklist are `PASS`.
- [ ] All P0 gates in `docs/status/GA_GATE_STATUS.md` are `PASS`.
- [ ] Auth Launch Gate, CI Regression, issuance, and cross-language conformance
      checks are green on the release commit.
- [ ] No unresolved critical or high security findings remain.
- [ ] Independent cryptographic review and penetration testing are complete.
- [ ] Browser and device compatibility evidence is approved.
- [ ] Backup restoration and dependency-failure drills have passed.
- [ ] Revocation and replay-denial evidence covers every supported verifier.
- [ ] Billing reconciliation has passed.
- [ ] Incident response and customer notification have been exercised.
- [ ] Product claims distinguish verified-human enrollment from routine
      passkey authentication.

- Decision: `GO` / `NO-GO`
- Release commit:
- Deployment:
- Approved by:
- Evidence bundle:
- Notes:
