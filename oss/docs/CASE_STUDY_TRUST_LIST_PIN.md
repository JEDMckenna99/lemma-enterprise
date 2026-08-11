# Case study: unpinned trust-list root

This case study walks through a vulnerability class on the **public verification
path**, its exploit condition, the fix, and the regression test shipped in this
repository.

## Vulnerability class

**Accepting a self-issued network root.**

The issuer trust list tells verifiers which issuer DIDs and Ed25519 keys are
active. The list itself is signed by a **network root** key — distinct from any
issuer key. If a verifier checks only that the trust list has *some* valid
Ed25519 signature but does **not** pin which keys may sign trust lists, an
attacker can:

1. Generate their own Ed25519 key pair.
2. Build a trust list listing arbitrary issuer keys under attacker control.
3. Sign the list with their own key.
4. Serve it to a verifier that treats any self-consistent signature as trusted.

The relying site would then accept credentials signed by attacker-controlled
issuer keys.

## Exploit condition

All of the following must be true:

| Condition | Attacker capability |
|-----------|---------------------|
| Verifier validates trust-list signature format | Can supply a well-formed list |
| Verifier does **not** check `signer_pubkey` against a pin set | Can use their own signing key |
| Verifier fetches trust material from a path the attacker controls (MITM, bad mirror, stale cache) | Can substitute the forged list |

This is **not** a lemma.id server compromise. It is a **verifier misconfiguration**
or incomplete implementation of the trust contract.

## Fix

Pin allowed network-root public keys before signature verification:

1. Ship the pin set in [`../specs/NETWORK_ROOT_PUBKEYS.json`](../specs/NETWORK_ROOT_PUBKEYS.json).
2. Reject when `signer_pubkey` is not in that set — reason code
   `trust_list_signer_not_pinned`.
3. Only then validate content hash, expiry, and Ed25519 signature on the list.

Both verifiers implement this check early and fail closed:

- Python: `signer_pubkey_is_pinned()` in `lemma_proof_verifier.py`
- JavaScript: `signerPubkeyIsPinned()` in `index.mjs`

Production verifiers also reject stale trust lists and unsigned Bloom snapshots;
see [`../DESIGN_DECISIONS.md`](../DESIGN_DECISIONS.md).

## Regression test

### Fixture

[`../fixtures/protocol/trust_list_unpinned_signer.json`](../fixtures/protocol/trust_list_unpinned_signer.json)

- `pinned_roots_hex`: contains `cc…cc` only
- `trust_list.signer_pubkey`: `aa…aa` (not pinned)
- `expected_reason`: `trust_list_signer_not_pinned`

Pin check runs **before** signature validation, so the fixture uses placeholder
hash/signature values — the verifier must still reject at the pin gate.

### Harness

[`../tests/test_protocol_fixtures.py`](../tests/test_protocol_fixtures.py) —
`test_trust_list_unpinned_signer_parity`:

- Python: `_verify_signed_trust_list_payload(..., network_root_pubkeys=pinned)`
- Node: same pin gate logic against the JS verifier module

Monorepo smoke: [`tests/test_oss_protocol_fixtures.py`](../../tests/test_oss_protocol_fixtures.py)
(relative to repo root: `tests/test_oss_protocol_fixtures.py`).

### Related monorepo coverage

The private monorepo also tests live trust-list construction in
`tests/test_issuer_trust_list.py` (`test_verify_signed_trust_list_rejects_unpinned_self_signed`)
and Section 4 cross-verifier tests in `tests/test_protocol_fixtures_section4.py`.

## Lessons for integrators

1. **Never skip root pinning** when implementing custom verifiers.
2. Treat `LEMMA_ALLOW_UNPINNED_TRUST_ROOT=1` as dev-only; production must pin.
3. Fail closed on stale or missing Bloom snapshots — a second class of trust-list
   attacks is serving an old list with revoked issuers still marked active.
4. Read [`../SECURITY_LIMITATIONS.md`](../SECURITY_LIMITATIONS.md) for what
   pinning does **not** solve (multi-document Sybil, voluntary sharing, etc.).
