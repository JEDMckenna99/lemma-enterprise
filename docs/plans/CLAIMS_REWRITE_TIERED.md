# Lemma.id Claim Rewrite (Tiered, Defensible)

This page provides production-ready copy that keeps Lemma's differentiation while avoiding overstatement.  
Use this for homepage, docs intro, and security model sections.

---

## Tiering Model

- **Tier A - Hard claims (prove now):** cryptographic and architectural facts that should hold across environments.
- **Tier B - Qualified claims (state assumptions):** performance/privacy outcomes that depend on integration choices or runtime conditions.
- **Tier C - Roadmap claims (not yet universal):** capabilities in progress or planned.

If a claim cannot be placed in a tier, do not publish it.

---

## Homepage Hero (Recommended Copy)

### Headline
Privacy-first passkey authentication for participating sites.

### Subheadline
Lemma.id provides local-first credential verification with backend session binding and real-time revocation support.

### Supporting bullets
- Passwordless sign-in with hardware-backed passkeys.
- Site-specific pseudonymous identifiers (PPIDs) to reduce cross-site linkability.
- Local verification hot path for return visits, with optional server-enforced checks.
- SSE/Redis-driven revocation and session invalidation for fast propagation.

### CTA line
Integrate with one SDK and a backend verification endpoint, then tune policy for your risk model.

---

## Product Claims by Tier

### Tier A (Hard claims)
- Lemma credentials are signed and verified using Ed25519.
- PPIDs are site-specific and derived from normalized site identity inputs.
- Return-visit verification can run locally when issuer keys and revocation artifacts are already synced.
- Backend session binding is supported for server-enforced authorization flows.

### Tier B (Qualified claims)
- Local verification can reduce issuer round-trips on return visits.
- PPID design helps reduce cross-site linkability when sites avoid sharing extra identifiers.
- Fast revocation propagation is supported via online channels (for example SSE/Redis), with timing dependent on client connectivity and infrastructure health.
- Typical verification latency is low in measured environments; end-to-end login latency still includes backend/session/application work.

### Tier C (Roadmap / maturity-qualified)
- Enterprise federation and provisioning (for example SCIM/SAML) are planned or partial, not full parity across all enterprise IAM use cases.
- Broader IAM governance workflows are expanding and should be presented with capability-level detail, not umbrella claims.

---

## Security Page Rewrite (Drop-in Section)

### Security Model (Suggested)
Lemma uses signed credentials and passkey-backed wallet access to support local-first authentication flows.  
Credential verification can run locally, while issuance, revocation distribution, and some session workflows remain online system functions.

### Threat Model Boundaries (Suggested)
- If a relying party runtime is compromised (for example XSS/malicious script), local storage protections alone do not eliminate credential misuse risk.
- Replay resistance depends on verifier policy (for example nonce/challenge freshness, timestamp windows, and one-time use semantics).
- Revocation effectiveness depends on distribution freshness and client connectivity.
- Privacy outcomes depend on integration behavior; additional identifiers collected/shared by sites can reintroduce linkability.

### Recommended wording for storage safety
Use: "Origin-scoped browser storage reduces cross-site exposure risk."  
Do not use: "Credentials can't be stolen."

---

## OAuth / IAM Positioning

### Use this
Lemma replaces password-centric sign-in flows in supported integrations and can complement OAuth/OIDC ecosystems.

### Avoid this
Lemma replaces OAuth entirely.

### Use this
Lemma provides authentication and scoped authorization primitives, with IAM capabilities expanding over time.

### Avoid this
Lemma is a complete enterprise IAM replacement (unless feature matrix proves parity).

---

## "Do Not Say" List

- "Replaces OAuth" (unqualified)
- "No network calls" (unqualified)
- "Credentials can't be stolen"
- "One login works everywhere"
- "Server has no idea who's logged in" (unqualified)

---

## Safe Alternatives (Copy-ready)

- "Local verification hot path after key/revocation sync; full auth may still include backend session binding."
- "Works across participating Lemma sites."
- "Designed to reduce cross-site linkability through site-specific PPIDs."
- "Fast revocation propagation through online channels."
- "Performance claims are benchmark observations; validate against your own workload and architecture."

---

## Buyer-Facing Metrics to Lead With

Prefer these over micro-benchmarks in hero messaging:
- End-to-end login latency percentiles (p50/p95/p99).
- Availability/SLO and incident response posture.
- Integration time and migration complexity.
- Security review artifacts and threat model completeness.
- Authorization semantics and auditability guarantees.

Keep microsecond-level crypto measurements in technical appendices.

---

## One-line Positioning (Recommended)

Lemma.id is a passkey-first, privacy-oriented authentication system with site-specific pseudonymous identity, local-first credential verification, and backend session/revocation controls.

