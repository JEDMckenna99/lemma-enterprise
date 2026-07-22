# isHuman SDK compatibility matrix

Canonical version manifest: [`ISHUMAN_SDK_VERSIONS.json`](ISHUMAN_SDK_VERSIONS.json)

## Current release line

| Surface | Version | Install / URL |
|---|---|---|
| Browser verifier (`ProofVerifier`) | 1.9.2 | `https://lemma.id/sdk/v1.9.2/proof-verifier.js` (immutable) or `/sdk/proof-verifier.js` (rolling) |
| Node backend verifier | 1.4.0 | `npm install @lemma/proof-verifier@1.4.0` or `/sdk/v1.4.0/proof-verifier.mjs` |
| Python backend verifier | 1.4.0 | `pip install lemma-proof-verifier==1.4.0` or `/sdk/v1.4.0/proof-verifier.py` |
| Protocol epoch | `browser_canonical_v2` | [`ISHUMAN_PROTOCOL_VERSIONS.json`](../protocol/ISHUMAN_PROTOCOL_VERSIONS.json) |

## Runtime requirements

| Component | Minimum |
|---|---|
| Browser | WebCrypto, modern Chromium/Firefox/Safari with passkeys |
| Node backend verifier | Node 18+ (19+ recommended for native WebCrypto) |
| Python backend verifier | Python 3.10+, `cryptography>=42` |
| Redis (production nonce store) | Redis 6+ with `SET NX` |

## Assurance policy compatibility

| Relying-site policy | Browser SDK | Backend verifier |
|---|---|---|
| Passkey continuity (`passkey`) | `requiredAssurance: 'passkey'` | `required_assurance='passkey'` |
| Sybil-resistant signup (`ishuman`) | `requiredAssurance: 'ishuman'` | `required_assurance='ishuman'` |

Backend verifiers treat `ishuman` as satisfying `passkey` (monotonic assurance).

## Cross-verifier parity

Shared fixtures: `tests/protocol_fixtures/` exercised by `tests/test_protocol_fixtures_section4.py` and `tests/test_ishuman_verify_packages.py`.

Browser, Node package, and Python package must produce identical allow/deny decisions for every shared vector before release.

## Integrity

Fetch SRI hashes from `GET /api/sdk/integrity` or run `python scripts/generate_sri_hashes.py`.

Prefer immutable versioned URLs in production HTML:

```html
<script src="https://lemma.id/sdk/v1.9.2/proof-verifier.js"
        crossorigin="anonymous"></script>
```

Pin integrity when embedding:

```html
<script src="https://lemma.id/sdk/v1.9.2/proof-verifier.js"
        integrity="sha384-..."
        crossorigin="anonymous"></script>
```
