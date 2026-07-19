# P0 Human-Auth Feature Freeze

- Status: Active
- Scope: lemma.id wallet, human identity, relying-site verification, recovery,
  tenant controls, billing, and production operations

## Purpose

The human-backed authenticator is under a P0 security-contract freeze. Until
the blocking workstreams in
`docs/status/HUMAN_BACKED_AUTHENTICATOR_PRODUCTION_READINESS.md` pass, changes
must reduce launch risk or provide evidence for a launch gate. New product
surface is not an acceptable substitute for closing trust-boundary gaps.

## Allowed work

- P0 security remediation and regression tests
- Threat-model, protocol, and authority-contract maintenance
- Cross-language verifier conformance work
- Tenant-isolation, revocation, recovery, secret, billing, and reliability work
- Removal or disabling of unsafe legacy behavior
- Production-readiness evidence, operational drills, and independent review
- Minimal compatibility changes required to deploy a P0 fix safely

## Frozen work

- New relying-site assurance tiers or proof types
- New authentication or recovery shortcuts
- New mutable credential fields without a protocol migration plan
- Expansion of wallet-session authority
- New customer-facing identity claims not supported by reviewed evidence
- New billing exemptions for production sites
- New legacy compatibility paths that bypass signed proof verification

## Exception process

An exception requires all of the following:

1. A written security rationale identifying the P0 issue the change addresses.
2. A threat-model entry and authority-operation entry, when applicable.
3. Tests proving the change does not weaken authentication, authorization,
   site binding, revocation, replay protection, or recovery.
4. Approval by the Security Lead and the owner of the affected workstream.
5. Evidence linked from the production-readiness checklist.

Emergency containment changes may deploy before the documentation is complete
when delaying would increase active risk. Their documentation and evidence must
be added immediately after containment.

## Exit conditions

The feature freeze ends only when:

- Every P0 workstream in the human-backed authenticator checklist is `PASS`.
- The Auth Launch Gate and CI Regression checks are green on the release commit.
- Independent cryptographic review and penetration testing have no unresolved
  critical or high findings.
- The final production decision is recorded as `GO`.

Ending the freeze requires named Security and Platform approvers. A successful
demo, smoke test, or pilot does not end the freeze by itself.
