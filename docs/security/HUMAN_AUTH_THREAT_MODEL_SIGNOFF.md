# Human-Auth Threat Model Sign-Off

Status: Pending independent review

This record is the human approval gate for Section 1 of
`docs/status/HUMAN_BACKED_AUTHENTICATOR_PRODUCTION_READINESS.md`. Automated
checks cannot approve threat completeness or residual-risk acceptance.

## Review scope

- `docs/security/HUMAN_AUTH_SECURITY_CONTRACT.md`
- `docs/security/THREAT_MODEL.md`
- `docs/api/AUTHORITY_OPERATIONS_V1.json`
- `docs/protocol/ISHUMAN_PROTOCOL_VERSIONS.json`
- `docs/protocol/ISHUMAN_PROTOCOL_MIGRATION_POLICY.md`
- `docs/cryptographic/CANONICAL_MESSAGES.md`

## Required review checks

- [ ] Proof semantics distinguish authentication, assurance, continuity,
      permission, action binding, and recovery.
- [ ] A wallet ID, PPID, Origin header, email address, phone number, or IDV
      session identifier is never treated as an authentication secret.
- [ ] Leaked-wallet-ID threats and device-enrollment authority are complete.
- [ ] Lost-device and compromised-passkey scenarios cover both containment and
      recovery.
- [ ] Malicious relying-site and cross-tenant threats cover application and
      database boundaries.
- [ ] Account-sharing limitations are explicit in security and product claims.
- [ ] Replay and race analysis covers actions, recovery, transfer, webhooks,
      revocation, and billing.
- [ ] Database, Redis, KMS, IDV, and network failures have explicit fail-open or
      fail-closed behavior.
- [ ] Issuer, trust-root, and signing-service compromise includes rotation,
      propagation, and emergency containment.
- [ ] Every critical authority operation maps to at least one threat and a
      required target proof.
- [ ] Residual risks are accurate and have named owners.
- [ ] Protocol versions and migration rules preserve verification and
      revocation continuity.
- [ ] Product claims do not imply continuous human presence or guaranteed
      prevention of voluntary account sharing.

## Automated evidence

- Authority contract check:
- Protocol registry check:
- Cryptographic invariant tests:
- Auth Launch Gate:
- CI Regression:
- Release commit:

## Findings

Critical findings:

High findings:

Medium findings:

Accepted residual risks:

Required follow-up:

## Approval

Decision: `APPROVED` / `CHANGES_REQUIRED` / `REJECTED`

Security reviewer:

Role or organization:

Review date:

Signature or approval record:

Notes:

Section 1 remains `IN_PROGRESS` or `BLOCKED` until this record has a named
reviewer, a decision of `APPROVED`, no unresolved critical/high contract
finding, and links to reproducible automated evidence.
