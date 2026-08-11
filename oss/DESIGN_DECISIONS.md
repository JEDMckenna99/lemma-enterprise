# Design decisions

This document explains the main cryptographic and trust-model choices in the
lemma.id verification path. For proof semantics, see
[`specs/HUMAN_AUTH_SECURITY_CONTRACT.md`](specs/HUMAN_AUTH_SECURITY_CONTRACT.md).

## Site-private PPIDs (pairwise identifiers)

**Decision:** Each relying site receives a stable opaque handle (`ppid`) derived
from the person's root and the site's canonical hostname — not a global user ID.

**Why:**

- **Unlinkability:** `example.com` and `other.example` cannot correlate the same
  person from PPIDs alone. Neither can lemma.id correlate sites from PPIDs.
- **Continuity:** The same person root + hostname always yields the same PPID,
  so accounts persist across sessions without usernames or email.
- **Fail-closed binding:** A credential's `siteId` claim must match the verifier's
  expected hostname; mismatches reject.

**Formula:** `PPID = HMAC(assigned_person_root, "lemma.id/site-ppid/v1" || canonical_hostname)`

See [`specs/LEMMA_ID_PRESENTATION_MODEL.md`](specs/LEMMA_ID_PRESENTATION_MODEL.md).

## Ed25519 signatures

**Decision:** Every cross-trust-boundary artifact is Ed25519-signed with a
canonical byte message.

**Why:**

- **Local verification:** Relying sites verify presentations on their own
  backend in milliseconds — no per-request call to lemma.id.
- **Small keys and signatures:** Fits browser WebCrypto and edge runtimes.
- **Single algorithm:** Presentations, trust lists, Bloom snapshots, action
  stamps, and session assertions all use the same verify path.

Browser credentials use `browserCanonicalMessage()` (v2 includes `credential.id`).
Server verifiers in `packages/` implement the same canonicalization in Python and
JavaScript.

## Pinned network roots

**Decision:** Issuer trust lists are signed by a **network root** key distinct
from issuer keys. Verifiers pin allowed root public keys and reject trust lists
whose `signer_pubkey` is not in that pin set.

**Why:**

- **No self-issued roots:** Without pinning, an attacker who can serve a
  trust list could sign it with their own key and list arbitrary issuer keys.
- **Rotation without trust drift:** Multiple pinned keys (`NETWORK_ROOT_PUBKEYS.json`)
  support overlap during rotation.
- **Fail-closed:** Missing pins, unpinned signers, stale lists, and bad
  signatures all reject with stable reason codes (e.g. `trust_list_signer_not_pinned`).

Pin set: [`specs/NETWORK_ROOT_PUBKEYS.json`](specs/NETWORK_ROOT_PUBKEYS.json).

## Signed Bloom revocation snapshots

**Decision:** Revocation state ships as a signed Bloom filter snapshot, refreshed
periodically (production default: every 15 minutes). Verifiers cache it locally.

**Why:**

- **Privacy:** Bloom membership tests do not reveal which credential IDs exist.
- **Offline hot path:** After fetch, verification needs no live call to lemma.id.
- **Safe false positives:** A Bloom false positive denies (fail closed); false
  negatives are structurally impossible for revoked credentials in the snapshot.
- **Staleness bound:** Snapshots carry `valid_until_unix` and monotonic
  `sequence_number`; expired or unsigned snapshots reject.

Sessions bind the Bloom `sequence_number` at mint time so replay across
revocation epochs fails closed.

## Assurance ladder (passkey vs isHuman)

**Decision:** `passkey` and `ishuman` are assurance values, not permissions.

- **passkey:** Continuity with a lemma.id-bound person root (anyone can mint
  another lemma.id — not Sybil resistance alone).
- **ishuman:** IDV-backed person assurance with document-root uniqueness on the
  same PPID (raises Sybil cost; not biometric unique-human).

Integrators choose `requiredAssurance` per action. Sybil-sensitive gates
(trials, tickets, payouts) should default to `ishuman`.

## What we deliberately did not optimize for

- Replacing a site's existing login stack (lemma.id is a proof layer).
- Exposing legal identity or KYC fields to relying sites.
- Absolute unique biological human across all government documents (see
  [`SECURITY_LIMITATIONS.md`](SECURITY_LIMITATIONS.md)).
