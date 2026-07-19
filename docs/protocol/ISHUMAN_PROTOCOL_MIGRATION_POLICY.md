# isHuman Protocol Migration Policy

Status: Active contract

This policy applies before changing any artifact registered in
`docs/protocol/ISHUMAN_PROTOCOL_VERSIONS.json`.

## Change classification

### Non-breaking

- Documentation corrections that do not alter accepted bytes or decisions
- New optional envelope metadata ignored by all existing verifiers
- New issuer keys using the same trust-list and signature format
- SDK implementation changes that preserve all pinned vectors and reason codes

### Breaking

- Any canonical-byte change
- Adding, removing, renaming, retyping, or reinterpreting a signed field
- Changing assurance ordering or required fields
- Changing site-binding canonicalization
- Changing issuer or trust-root authentication semantics
- Changing revocation candidates, hashes, freshness, or failure behavior
- Changing nonce, replay, session, or action-binding semantics
- Rejecting an artifact previously accepted by a supported verifier

A breaking change creates a new per-artifact version. It never reuses the old
marker.

## Required migration record

Before implementation, add a migration record containing:

- artifact and old/new versions;
- security reason and threat-model references;
- canonical old/new test vectors;
- issuer and verifier implementation owners;
- minimum supported SDK versions;
- issuance cutover condition;
- dual-verification entry and exit conditions;
- credential or wallet reprovisioning behavior;
- revocation and site-policy continuity;
- telemetry and rollback conditions;
- removal approval and evidence.

The record must be reviewed before canonical code changes merge.

## Migration stages

1. **Freeze old behavior:** pin old positive and negative vectors across every
   supported verifier.
2. **Add dual verification:** verifiers recognize explicit old and new markers
   and dispatch to separate immutable code paths.
3. **Deploy verifiers first:** supported relying-site verifiers accept the new
   artifact before production issuers emit it.
4. **Begin versioned issuance:** issuers emit the new marker only when the
   recipient path is compatible.
5. **Reissue or reprovision:** wallets obtain new credentials or artifacts
   without changing the canonical PPID unless the migration explicitly changes
   identity-root semantics.
6. **Observe:** compare acceptance, denial reasons, revocation, recovery, and
   rollback signals against approved thresholds.
7. **Stop old issuance:** only after all supported issuer paths emit the new
   version and rollback remains possible.
8. **End old verification:** only after old artifacts have expired or been
   revoked/reissued and removal evidence is approved.

Calendar time alone never ends an overlap. Exit is evidence-based.

## Verifier behavior

- Dispatch on an authenticated schema or canonical prefix, not field guessing,
  whenever the artifact supports an explicit marker.
- Keep old and new canonical builders separate.
- Reject unknown versions with a stable `unsupported_protocol_version` reason.
- Do not silently coerce a malformed new artifact into the old verifier.
- Apply the same assurance, site, expiry, trust, and revocation policy after
  version-specific signature verification.
- Browser, Python, and Node must pass the same fixture corpus before support is
  advertised.
- Durable audit verification may retain an old verifier after live acceptance
  ends, but it must be explicitly audit-only and cannot authorize mutations.

## Issuance and rollback

- Verifiers deploy before issuers.
- Issuance selects an explicit artifact version; ambient client behavior cannot
  change canonical bytes.
- Rollback can stop new issuance while dual-verification remains active.
- A rollback never reuses a new-version signature as an old-version artifact.
- Emergency disabling of one issuer key uses trust-list rotation under the
  existing envelope version unless trust-root semantics themselves changed.
- If a root-key migration is compromised, freeze issuance and publish a signed
  emergency trust update from an independently pinned recovery root.

## Credential and presentation migration

The current `ishuman_credential` and `presentation_envelope` versions are
implicit legacy v1 shapes.

- Adding an explicit credential identifier to signed bytes requires a new
  credential version.
- Old credentials remain subject to their original signature verifier and
  revocation candidates during overlap.
- New credentials must bind every revocation identifier used for authorization.
- A presentation containing mixed artifact versions is accepted only when the
  compatibility matrix explicitly permits that combination.
- Wallet auto-provisioning may reissue a site credential, but the relying-site
  account remains bound to the verified canonical PPID.

## Revocation continuity

- A migration cannot make an old revocation disappear.
- During overlap, publishers include all candidate identifiers needed by every
  accepted artifact version.
- Site blocks and doubts are applied to canonical and verified legacy PPIDs
  during convergence.
- Trust-list and Bloom migrations deploy verifier support before publisher
  cutover.
- Publisher failure returns unavailable; migration fallback never signs an
  empty revocation set.

## PPID, identity-root, and recovery continuity

- `site_ppid`, `document_root`, `person_root`, and `ppid_convergence` are
  versioned independently.
- A document-root schema change does not change a canonical assigned
  `person_root` after the person has been resolved.
- If root derivation changes, retain a versioned lookup path that resolves the
  same known person before assigning a replacement root.
- A PPID derivation change requires a signed convergence artifact and
  transactional relying-site account merge.
- Recovery must verify the old and new root-version evidence before binding a
  replacement passkey.

## Action and fresh-passkey continuity

- `action_stamp`, `action_commitment`, and `fresh_passkey_attestation` versions
  are independent but their allowed combinations are explicit.
- A new action-stamp version cannot downgrade nonce, method, path, body hash,
  subject, credential, assurance, or site binding.
- A fresh-passkey attestation is accepted only for the exact action commitment
  version and value it signs.
- Replay state is not reset by protocol migration.

## Artifact coverage

This policy covers every registry artifact:

- `site_ppid`
- `document_root`
- `person_root`
- `ishuman_credential`
- `site_session_presentation`
- `wallet_assertion`
- `wallet_master_secret`
- `bloom_snapshot`
- `issuer_trust_list`
- `ppid_convergence`
- `action_commitment`
- `fresh_passkey_attestation`
- `action_stamp`
- `presentation_envelope`

Adding an artifact to the registry requires adding it to this list and defining
its migration class before issuance.

## Approval gate

A migration is approved only when:

- canonical and negative vectors pass in every supported verifier;
- old/new overlap and rollback tests pass;
- revocation and site-policy continuity tests pass;
- the threat model is updated;
- the compatibility record is published;
- Security and the affected issuer/verifier owners approve the evidence.
