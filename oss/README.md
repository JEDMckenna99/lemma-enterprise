# Sign in with lemma.id — verifiable source

This repository contains every artifact a relying site or auditor needs to
verify lemma.id's claims **without trusting the lemma.id service**: the
verifier code sites run on their own backends, the browser SDK served from
`https://lemma.id/sdk/`, the client-side credential-store crypto, and the
protocol specs. Apache-2.0 licensed.

lemma.id is passwordless sign-in with passkeys and a site-private, stable
`ppid` as the account key — no usernames, passwords, or email collection.
**isHuman** is an optional step-up assurance tier (one verified human per
account, same PPID).

## What is here, and what each piece lets you verify

### `packages/` — server-side verifiers (the trust core)

The code your backend runs to accept a lemma.id presentation. Verification
is entirely local: Ed25519 signature checks against pinned network root
keys plus a signed Bloom revocation snapshot refreshed every 15 minutes.
lemma.id is never contacted on the hot path and never sees an individual
verification.

- `proof-verifier-js/` — published as [`@lemma.id/proof-verifier`](https://www.npmjs.com/package/@lemma.id/proof-verifier).
  Zero dependencies; only requires WebCrypto. Node 19+, Deno, Bun, edge runtimes.
- `proof-verifier-py/` — published as [`lemma-proof-verifier`](https://pypi.org/project/lemma-proof-verifier/).

Both ship offline testing helpers that mint valid test presentations
locally, so you can audit the accept/reject logic end to end without any
network access.

### `sdk/` — browser SDK

Byte-identical to what `https://lemma.id/sdk/` serves.

- `proof-verifier.js` — the `ProofVerifier` client (legacy alias
  `IsHumanVerifier`): local Ed25519 verification, revocation checks, and the
  sign-in popup flow.
- `lemma-signin.js` — the drop-in `<lemma-signin>` button component.

### `wallet/` — the client-held credential store

The code behind the claim that **signing keys never leave the user's
device**. Credentials live in IndexedDB, unlocked by a passkey; at-rest
encryption keys are derived from the WebAuthn PRF extension.

- `lemma-keys.js` — HKDF key derivation and Ed25519 signing.
- `wallet-at-rest-crypto.js` — PRF-derived AES-GCM envelope encryption for
  everything stored at rest.
- `lemma-wallet.js` — the credential store itself: storage, passkey unlock,
  site-private PPID derivation, presentation signing.

### `specs/` — protocol and trust contracts

- `LEMMA_ID_PRESENTATION_MODEL.md` — presentation format and PPID
  derivation. PPIDs are derived per site (person root + canonical
  hostname), which is the basis of the cross-site unlinkability claim.
- `HUMAN_AUTH_SECURITY_CONTRACT.md` — precisely what each proof type does
  and does not establish (passkey, isHuman, stamps, recovery).
- `SIGN_IN_TRUST_AND_RECOVERY.md` — the trust and recovery model, stated
  plainly, including what lemma.id can and cannot do to your accounts.
- `NETWORK_ROOT_PUBKEYS.json` — the network root public keys pinned by the
  verifiers.

## What is deliberately not here

Issuer key management (KMS), identity-verification provider integration,
billing, abuse controls, and platform admin tooling remain private. None of
it is on the verification path: nothing in it can change what your verifier
accepts, and your trust in a presentation never depends on it.

## Verifying what production serves

The SDK files here should match what `https://lemma.id/sdk/` serves for the
same version. Fetch and diff:

```sh
curl -s https://lemma.id/sdk/proof-verifier.js | diff - sdk/proof-verifier.js
```

## Provenance

This tree is assembled from the lemma.id monorepo by
`scripts/build_oss_repo.py`; each file's canonical source path is listed
there. Issues and audits welcome.
