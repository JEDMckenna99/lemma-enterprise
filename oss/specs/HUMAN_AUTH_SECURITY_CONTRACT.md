# Human-Auth Security Contract

- Status: Active P0 contract
- Audience: Security reviewers, lemma.id SDK engineers (internal: wallet), verifier maintainers,
  platform engineers, and relying-site integrators

## Glossary

| Term | Meaning |
|------|---------|
| **lemma.id** | Preferred public noun: the user's passkey-protected local identity store. |
| **wallet** (internal) | Legacy code/API name for a lemma.id instance and its unlock/session artifacts (`LemmaWallet`, `wallet_assertion`, `wallet_session`, etc.). |

## Product security objective

lemma.id provides accounts rooted in an IDV-backed human identity, represented
to each relying site by a site-private PPID and accessed through a
passkey-secured lemma.id. Daily authentication and human assurance are separate
claims and must be evaluated separately.

The relying-site integration contract remains
`docs/integration/ISHUMAN_AGENT_INTEGRATION.md`. This document defines the
security meaning of the proofs used to implement that contract.

## Proof semantics

| Proof or value | Establishes | Does not establish | Required verification |
|---|---|---|---|
| Passkey WebAuthn assertion | User verification and possession of the registered authenticator for the exact RP ID, origin, and challenge | Unique humanity, legal identity, site membership, or permission | Server verifies challenge, origin, RP ID, signature, sign counter policy, user verification, purpose, and expiry |
| Passkey-tier credential | Continuity with a lemma.id-bound provisional or known person root at `assurance=passkey` | IDV-backed humanity or one-person-per-account assurance | Verify signed presentation, site binding, expiry, revocation, and assurance |
| isHuman-tier credential | IDV-backed human assurance for the credential subject at `assurance=ishuman`, anchored by document-root uniqueness | Absolute unique biological humanity across all government IDs; that every later action is manually performed by that person; that account sharing is impossible | Verify signed presentation, exact assurance policy, site binding, expiry, revocation, and convergence |
| PPID | Stable opaque account handle for one canonical person root and normalized site hostname | Authentication, permission, legal identity, or a secret | Accept only after extracting it from a verified signed presentation |
| lemma.id Ed25519 assertion (`wallet_assertion`) | Possession of an already authorized lemma.id device signing key and binding of the declared fields to a server challenge | Passkey user verification, human assurance, site administration, or authority to enroll itself | Verify enrolled non-revoked device key, nonce, lemma.id binding, purpose-bound fields, expiry, and replay state |
| lemma.id unlock session cookie or unlock token (`wallet_session`) | Server-issued cached unlock state for the lemma.id named in the signed token | Fresh passkey proof, unique humanity, permission, site ownership, or authority to create new lemma.id keys | Verify server signature, expiry, intended audience and purpose; restrict to explicitly permitted low-risk operations |
| Signed presentation | Issuer-signed credential claims and, when present, a site-session proof of possession | Authorization beyond its verified claims or immunity from replay when no action binding exists | Backend verifier validates pinned trust root, issuer, canonical signature, required fields, site binding, assurance, expiry, revocation, and optional session assertion |
| Action stamp | Possession of the site signing key over a canonical action, method, path, body hash, nonce, and time window | Fresh passkey use unless a valid fresh-passkey attestation is also bound; IDV assurance beyond the credential | Verify credential, action signature, exact action binding, freshness, nonce atomically, and required assurance |
| Fresh-passkey attestation | A recent server-verified WebAuthn ceremony bound to an opaque action commitment | A new assurance tier, permission, or disclosure of the relying site's action body to lemma.id | Verify issuer signature, credential and PPID binding, site binding, action commitment, expiry, and required action stamp |
| Recovery proof | Completion of the specifically documented recovery ceremony and authority to bind a replacement authenticator to the canonical person | Authority derived from email, lemma.id id (`wallet_id`), or IDV session ID alone | Verify one-time recovery state, fresh IDV when required, replacement passkey possession, exact account/site binding, expiry, and atomic consumption |
| Permission credential | Issuer-granted scope such as `admin_access`, bound to its site and subject | Human assurance unless accompanied by a complete identity proof | Verify signed permission, subject, site, scope, expiry, revocation, and required identity proof |
| Site API key | Possession of a relying-site backend credential scoped to one registered site | End-user identity, lemma.id control, or authority over another site | Compare using the authoritative hash-only key store, enforce active status and exact site ownership |
| Webhook signature | Authenticity and integrity of one provider event within its replay window | End-user identity or authorization outside that provider event | Verify provider signature, timestamp, event identity, endpoint purpose, and idempotency |

## Assurance and authorization rules

1. `passkey` and `ishuman` are assurance values, not permission scopes.
2. `ishuman` is required when policy promises IDV-backed person assurance
   (document uniqueness). It does not promise biometric unique-human.
3. A valid identity proof does not grant site administration. Administrative
   access requires a separately verified permission proof.
4. A PPID is never accepted as a bearer credential.
5. A lemma.id identifier (`wallet_id`) is never accepted as proof of lemma.id control.
6. An HTTP `Origin` header is a browser isolation signal, not authentication.
7. A new device key cannot authorize its own enrollment into an existing
   lemma.id.
8. Cookie-backed lemma.id unlock state cannot authorize a mutation unless that
   operation is explicitly listed for lemma.id-unlock-session principals.
9. Signup and account creation use T2 or stronger verification. T1 bare-PPID
   flows are restricted to low-risk, non-account-binding gates.
10. Fraud-sensitive mutations use action-bound proofs with durable replay
    protection.

## Session terminology

The word "session" is overloaded and must be qualified:

- **lemma.id unlock state** (internal: wallet unlock state): local encrypted state or a server-signed convenience
  token. It is not a credential or permission proof.
- **Application session:** the relying site's own authenticated session after
  it verifies a presentation and binds the PPID to an account.
- **Site session assertion:** a signed artifact proving possession of the
  per-site signing key for a bounded time and Bloom sequence.
- **IDV session:** provider and server state for one verification attempt. Its
  identifier is not a recovery or lemma.id credential.

## Authority-creation rule

Every operation that creates or changes lemma.id, identity, tenant, billing, or
recovery authority must appear in
`docs/api/AUTHORITY_OPERATIONS_V1.json`. Each entry declares:

- the current proof accepted by code;
- the required proof under this contract;
- scope and site-binding requirements;
- risk tier and threats;
- whether current behavior is compliant;
- tests and owning checklist section.

Undeclared authority-changing operations fail the contract gate.

## Fail-closed requirements

Verification or mutation is denied when any required trust input is missing,
malformed, stale, unavailable, wrong-site, revoked, replayed, or unverifiable.
This includes:

- issuer trust and root pinning;
- revocation snapshots and site policy;
- required assurance and permission;
- server challenge and nonce state;
- tenant ownership;
- recovery binding;
- billing entitlement when production issuance requires it.

A dependency failure cannot be converted into a fresh signed assertion that no
revocations, blocks, or billing restrictions exist.

## Explicit non-goals

- Preventing coercion or voluntary account sharing in every circumstance
- Proving that every routine action was manually performed by the verified
  person
- Absolute unique biological humanity across distinct government documents
  (multi-document residual Sybil); see [`HUMAN_UNIQUENESS_BOUNDS.md`](HUMAN_UNIQUENESS_BOUNDS.md)
- Exposing legal identity to relying sites
- Treating email, phone number, device fingerprint, lemma.id id (`wallet_id`), or PPID as
  identity proof by itself
- Protecting an unlocked browser from same-origin malicious JavaScript
- Replacing regulatory KYC, AML, age, residency, or accreditation checks when a
  relying site is legally required to perform them

## Protocol and migration rules

Current artifact versions are registered in
`docs/protocol/ISHUMAN_PROTOCOL_VERSIONS.json`. Changes to signed bytes or
verification meaning follow
`docs/protocol/ISHUMAN_PROTOCOL_MIGRATION_POLICY.md` before implementation.
Unknown or unsupported versions fail closed.

## Related contracts

- `docs/integration/ISHUMAN_AGENT_INTEGRATION.md`
- `docs/product/LEMMA_ID_PRESENTATION_MODEL.md`
- `docs/cryptographic/CANONICAL_MESSAGES.md`
- `docs/security/THREAT_MODEL.md`
- `docs/api/AUTHORITY_OPERATIONS_V1.json`
- `docs/status/P0_HUMAN_AUTH_FEATURE_FREEZE.md`
