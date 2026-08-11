# Security limitations

lemma.id is a **proof layer** for site-private person continuity and optional
IDV-backed step-up. This document states precisely what the public verifier
**does not prove**. Full proof semantics:
[`specs/HUMAN_AUTH_SECURITY_CONTRACT.md`](specs/HUMAN_AUTH_SECURITY_CONTRACT.md).

## What lemma.id does not prove

### Unique biological human

isHuman establishes **IDV-backed person assurance** anchored by **document-root
uniqueness**: one verified government document → at most one person root for
that document.

It does **not** prove:

- Absolute proof of unique biological human
- One human with any government ID always maps to one lemma.id on fresh enrollment
- Biometric uniqueness or face deduplication across independent enrollments
- Unlimited Sybil resistance against well-capitalized multi-document farmers

**Residual channel:** A person with **distinct** government documents (different
extracted document numbers) can complete IDV on a **fresh** lemma.id and receive
a **second** person root. Requiring `ishuman` raises the cost (each extra identity
needs a fresh IDV'd document) but does not eliminate this channel.

### Passkey tier alone

A passkey-tier credential proves continuity with a lemma.id-bound person root at
`assurance=passkey`. It does **not** prove IDV-backed humanity or one-person-per-account
assurance. Anyone can create another lemma.id.

### PPID is not authentication

A PPID is a stable opaque handle — not a bearer secret, not legal identity, and
not permission to act. Accept a PPID only after extracting it from a **verified
signed presentation** on your backend.

### Voluntary sharing and coercion

lemma.id does not prevent users from sharing passkeys, devices, or unlocked
browsers, or from being coerced through IDV. Account-sharing policies remain the
relying site's responsibility.

### Unlocked browser / same-origin XSS

An unlocked lemma.id in a compromised same-origin page can sign presentations.
Content Security Policy mitigates but does not eliminate this class. High-risk
mutations should use action stamps with fresh-passkey attestation where policy
requires it.

### Regulatory compliance

lemma.id does not replace KYC, AML, age verification, residency checks, or other
obligations when a relying site is legally required to perform them. No KYC
fields, names, or document numbers are disclosed to relying sites through the
default integration path.

### Permission vs identity

A valid identity proof does not grant site administration. Admin access requires
a separately verified permission credential (e.g. `admin_access`).

### lemma.id identifier is not control proof

A lemma.id instance id (`wallet_id` in internal APIs) is never proof of lemma.id
control. Server challenges, passkey ceremonies, and signed presentations are required.

## Fail-closed behavior (what rejection means)

Verification denies when trust inputs are missing, malformed, stale, revoked,
wrong-site, or unpinned — including:

| Condition | Typical reason code |
|-----------|---------------------|
| Trust list signer not in pin set | `trust_list_signer_not_pinned` |
| Bloom snapshot expired | `bloom_snapshot_stale` |
| Credential site binding mismatch | `site_id_mismatch` |
| Assurance below policy | `assurance_insufficient` |
| Missing required credential fields | `credential_id_missing`, etc. |
| Revoked credential in Bloom | `credential_revoked` |

A dependency failure must not be treated as "no revocations exist."

## For integrators

1. Default to `requiredAssurance: 'ishuman'` for Sybil-sensitive actions.
2. Verify signed presentations on the server — never trust a bare client `ppid`.
3. Read [`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md) for why PPIDs, Ed25519,
   pinned roots, and Bloom snapshots are structured this way.
4. See [`docs/CASE_STUDY_TRUST_LIST_PIN.md`](docs/CASE_STUDY_TRUST_LIST_PIN.md)
   for a concrete vulnerability class on the trust path and its regression test.
