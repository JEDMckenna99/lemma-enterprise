# Lemma.id Standalone Product Boundary

Date: 2026-02-15

## Product Definition

Lemma.id standalone auth is a local-authorization product with a managed control plane.

- Local data plane:
  - verify delegated credentials locally
  - enforce local policy (`aud`, `scope`, `allowed_paths`, `exp`, `nbf`, `jti`)
  - return deterministic machine deny codes
- Managed control plane:
  - issuance authority
  - revocation authority and distribution
  - issuer key distribution and rotation
  - audit and operator governance

## What "Standalone" Means in This Product

- Authorization decisions do not require a round-trip to Lemma.id on every action.
- Control-plane operations (issuance/revoke/rotation) still require network connectivity.
- Local runtime behavior is deterministic even when control plane is temporarily unavailable.

## Failure Modes and Expected Behavior

- Control plane unavailable, local cache fresh:
  - continue local decisions within freshness policy.
- Control plane unavailable, cache stale, high-risk action:
  - fail closed.
- Token revoked and revocation freshness SLA met:
  - deny with `token_revoked`.
- Missing/invalid required claims:
  - deny with contract-specific code (`audience_mismatch`, `missing_scope`, etc.).

## Non-Goals

- Fully offline identity lifecycle (issuance/revocation writes).
- Dynamic policy mutation without control-plane sync.

## Acceptance Criteria

- Conformance suite passes with stable machine codes.
- Runbook covers control-plane outage and stale-cache behavior.
- Product docs avoid claims implying fully offline control plane.
