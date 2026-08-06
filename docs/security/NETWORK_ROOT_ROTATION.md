# Network root rotation

The issuer trust list is signed by a **network root** Ed25519 key distinct from
individual issuer signing keys. Verifiers pin allowed root public keys and reject
trust lists whose `signer_pubkey` is not in the pin set.

## Pin sources

1. `LEMMA_NETWORK_ROOT_PUBKEYS` — comma-separated 64-char hex pubkeys (preferred in production)
2. [`docs/cryptographic/NETWORK_ROOT_PUBKEYS.json`](../cryptographic/NETWORK_ROOT_PUBKEYS.json) — checked into the repo for Browser SDK embed sync

Browser, Python, and Node verifiers must agree on the same pin set.

Trust bundle distribution mirrors are documented in
[TRUST_BUNDLE_MIRROR.md](../operations/TRUST_BUNDLE_MIRROR.md).

## Normal rotation (overlap)

1. Generate the replacement root keypair offline or in a separate custody boundary.
2. Add the **new** pubkey to `LEMMA_NETWORK_ROOT_PUBKEYS` and the JSON file **before** switching signing.
3. Deploy verifiers with both old and new pubkeys pinned.
4. Start signing trust lists with the new private key.
5. After all verifiers and caches have refreshed, remove the old pubkey from the pin set.

Overlap ensures trust lists signed by either key verify successfully during the window.

## Emergency rollover

If the online root may be compromised:

1. Revoke/stop using the compromised private key immediately.
2. Publish a new root pubkey in the pin set (out-of-band if necessary).
3. Deploy verifier pin updates before or concurrently with the new signed trust list.
4. Invalidate stale trust-list caches (Browser `localStorage`, server-side snapshot TTL).
5. Record the incident, affected `signer_pubkey`, and rollback commit in the evidence bundle.

## Compromise response

- Treat all trust lists signed by the compromised root as untrusted after rollover.
- Re-issue Bloom snapshots under the new root.
- Do not accept `LEMMA_ALLOW_UNPINNED_TRUST_ROOT=1` in production.

## Operational checklist

- [ ] Production Heroku config includes `LEMMA_NETWORK_ROOT_PUBKEYS`
- [ ] Browser SDK embed in `static/js/ishuman-verifier.js` matches JSON pins
- [ ] Rotation drill documented with commit SHA and test output
