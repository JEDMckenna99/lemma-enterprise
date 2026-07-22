# isHuman Protocol Version Registry

- Status: Active contract
- Machine-readable source: `docs/protocol/ISHUMAN_PROTOCOL_VERSIONS.json`

## Policy

- Protocol versions apply per artifact. A change to one artifact does not
  automatically renumber unrelated artifacts.
- Canonical prefixes or schema identifiers are the wire version when present.
- Older formats without an explicit marker are registered as
  `implicit_legacy`; their current byte shape is v1 and must not change in
  place.
- Unknown or unsupported versions fail closed.
- SDK package versions and protocol versions are independent. The compatibility
  matrix must state which protocol versions each SDK supports.
- Any signed-byte, required-field, trust, assurance, or revocation-semantics
  change follows `docs/protocol/ISHUMAN_PROTOCOL_MIGRATION_POLICY.md`.

## Current human-auth v1 epoch

| Artifact | Current version | Marker | Status |
|---|---|---|---|
| Site PPID derivation | v1 | `lemma.id/site-ppid/v1` | Explicit |
| Document root | v2 | `lemma.identity.document-root.v2` | Explicit; legacy v1 retained |
| Person root | v1 | `lemma.id/person-root/v1` | Explicit |
| isHuman credential | browser-canonical v2 | `proof.signatureValueWeb` shape | Explicit; legacy v1 retained |
| Site session presentation | v1 | `lemma:site-session-presentation:v1` | Explicit |
| Wallet assertion | v1 | registered `build_assertion_payload` shape | Implicit legacy |
| Wallet master secret | v1 | `LEMMA_PPID_ROOT_KEY` HMAC derivation | Implicit legacy |
| Bloom snapshot | v1 | `lemma:bloom-snapshot:v1` | Explicit |
| Issuer trust list | v1 | `lemma:issuer-trust-list:v1` | Explicit |
| PPID convergence | v1 | `ppid_convergence.v1` | Explicit |
| Action commitment | v1 | `lemma:action-commitment:v1` | Explicit |
| Fresh-passkey attestation | v1 | `fresh_passkey_attestation.v1` | Explicit |
| Action stamp | v1 | `action_stamp_v1` | Explicit |
| Presentation envelope | v1 | registered composite shape | Implicit legacy |

## Important distinctions

### Document root v2 is not protocol epoch v2

Document-root schema v2 adds normalized issuing-subdivision support to
server-side identity-root material. It does not renumber presentations or site
credentials. Legacy document-root v1 records remain recovery inputs and require
the version-aware identity-root migration rules.

### Credential and presentation versions are currently implicit

The browser-canonical credential is identified by `proof.signatureValueWeb`.
The presentation is identified by its `credential` member and optional
session/convergence artifacts. These shapes are registered as v1 but do not yet
carry a top-level protocol field. A future explicit version is a breaking
migration, not an in-place field reinterpretation.

### Trust-list payload version and canonical prefix

The trust-list envelope currently carries integer `version: 1` and uses
`lemma:issuer-trust-list:v1` in the signed message. Issuer key rotation does not
by itself change the wire version. A canonical-byte or trust-root semantics
change does.

## Compatibility record

Before a release supports a new artifact version, record:

- first issuing service version;
- minimum Browser, Python, and Node verifier versions;
- old-version issuance stop condition;
- dual-verification overlap;
- revocation and site-policy continuity;
- wallet reprovisioning behavior;
- rollback boundary;
- removal evidence.

No v2 signed artifact is approved by this registry today.
