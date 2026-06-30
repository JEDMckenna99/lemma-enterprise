# Lemma Trust Core Spec (Thin Formalization)

Status: Draft v0.1  
Owner: Authz/Platform  
Scope: Runtime verification contract for lemmas used by protected API routes.

## Purpose

This document defines a small, stable trust core so all services verify lemmas the same way.

It is designed to:
- keep lemma presentation uniform across issuers;
- preserve composability across endpoints and nodes;
- provide deterministic allow/deny outcomes with explicit reason codes;
- serve as a test oracle and audit artifact for authorization behavior.

This is intentionally a thin formalization, not a full theorem-prover system.

## Non-Goals

- Replacing existing deployment and routing policy systems.
- Rewriting auth flows end-to-end.
- Introducing non-deterministic or network-dependent verification steps.

## Canonical Lemma Envelope

All runtime-verifiable lemmas MUST follow the canonical envelope shape.  
Fields may be produced by different issuers, but the verifier input shape is fixed.

```json
{
  "version": "v1",
  "type": "authn | authz | delegation | attestation",
  "subject": {
    "ppid": "string",
    "site_id": "site_* (optional)",
    "site_domain": "normalized-domain (optional)"
  },
  "issuer": {
    "id": "string",
    "key_id": "string"
  },
  "scope": ["string"],
  "permissionId": "admin_access (for admin compatibility when present)",
  "permission_level": "viewer | operator | admin (optional)",
  "issued_at": 0,
  "expires_at": 0,
  "site_binding": {
    "site_id": "site_* (optional)",
    "site_domain": "normalized-domain (optional)"
  },
  "proof": {
    "alg": "string",
    "sig": "string"
  }
}
```

## Type and Shape Invariants

The verifier MUST enforce:
- timestamps are numeric;
- booleans remain booleans;
- `scope` is an array of strings;
- admin compatibility uses canonical `permissionId = admin_access`;
- selected admin level is preserved separately via `permission_level`;
- when both `site_id` and `site_domain` exist, both are preserved for validation context.

## Site Identity and PPID Binding Rules

- `site_id` is an ownership/database binding key (`site_*`).
- `siteId` / `site_domain` (normalized hostname) is the PPID derivation and **runtime** credential matching key.
- PPID derivation MUST use wallet secret + normalized hostname/domain only.
- Host normalization requires lowercase, no scheme/path/port, and `www.` stripping when applicable.
- Customer-site default identity input SHOULD align with `window.location.hostname`.
- Platform runtime binding canonicalizes to `lemma.id` (aliases: `lemma_platform`, `www.lemma.id`).
- Verifier fails closed on issued/requested site binding mismatch.
- Verifier MUST NOT silently coerce mismatched bindings.
- Empty site fields on identity proofs are optional metadata; skip before strict canonicalization.

Presentation model: `docs/product/LEMMA_ID_PRESENTATION_MODEL.md`

## Core Verification Rules (v1)

Verification is deterministic and local:

1. `R1_SIGNATURE_VALID`  
   Cryptographic proof verifies against trusted issuer key material.

2. `R2_ISSUER_TRUSTED`  
   Issuer ID and key ID exist in trusted issuer set for environment.

3. `R3_TIME_VALID`  
   `issued_at <= now <= expires_at` with defined skew tolerance.

4. `R4_SITE_BINDING_MATCH`  
   Request context and lemma `site_binding` match exactly after normalization.

5. `R5_SUBJECT_BINDING_MATCH`  
   Subject PPID in lemma matches the authenticated/requested principal context.

6. `R6_SCOPE_SATISFIES_POLICY`  
   Route policy required scopes are contained in lemma scope.

7. `R7_PERMISSION_COMPAT`  
   If admin path requires elevated access, `permissionId` and `permission_level` satisfy policy.

8. `R8_DELEGATION_BOUNDS`  
   Delegated lemma chains (if present) do not exceed max depth and preserve scope narrowing.

If any rule fails, deny with standardized reason code.

## Standard Deny Reason Codes

The verifier and decorators should produce only cataloged deny codes:

- `AUTH_MISSING_CREDENTIAL`
- `AUTH_INVALID_CREDENTIAL_FORMAT`
- `AUTH_INVALID_SIGNATURE`
- `AUTH_ISSUER_UNTRUSTED`
- `AUTH_CREDENTIAL_EXPIRED`
- `AUTH_SITE_BINDING_MISMATCH`
- `AUTH_SUBJECT_MISMATCH`
- `AUTH_SCOPE_INSUFFICIENT`
- `AUTH_PERMISSION_INSUFFICIENT`
- `AUTH_DELEGATION_INVALID`

Each code maps to a default HTTP status and message in centralized policy/error catalog.

## Endpoint Policy Examples

These examples define expected outcomes and explainability.

1. `require_authenticated`  
   Requires `R1-R5`.  
   Deny example: `AUTH_SUBJECT_MISMATCH`.

2. `require_wallet_ppid`  
   Requires `R1-R5` plus wallet-unlocked context predicate.  
   Deny example: `AUTH_MISSING_CREDENTIAL` or route-specific wallet-unlocked deny code.

3. `require_customer_or_admin`  
   Requires `R1-R7`, with policy branch:
   - customer branch: scope includes customer action scope;
   - admin branch: `permissionId=admin_access` and `permission_level` threshold met.
   Deny example: `AUTH_SCOPE_INSUFFICIENT`.

## Verification Contract

Implementations should expose a single deterministic interface:

```python
def verify_lemma_for_request(lemma: dict, request_context: dict, route_policy: dict) -> dict:
    """
    Returns:
      {
        "allow": bool,
        "deny_code": "AUTH_* | None",
        "reason": "string",
        "normalized_principal": {...},
        "applied_rules": ["R1_SIGNATURE_VALID", ...]
      }
    """
```

No hidden side effects, no implicit network calls, no route-local custom trust logic.

## Regression and Audit Expectations

- Every protected route must map to a policy entry.
- Tests must cover at least one pass and one fail per core rule.
- Deny reason code assertions are mandatory in negative tests.
- Deployment validation should include smoke checks against live protected endpoints.

## Adoption Plan (Incremental)

1. Mark this doc as reference for authz verifier changes.
2. Ensure centralized policy and error catalog match codes/rules in this spec.
3. Add missing rule-level tests where coverage gaps exist.
4. Promote status from Draft v0.1 to Adopted v1 after full regression and deployment validation.
