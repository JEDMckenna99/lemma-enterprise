# Trust bundle mirror

The signed bloom-filter + issuer trust-list bundle is served live at:

- Primary: `https://lemma.id/api/revocation/bloom-filter`

A verified mirror is published every five minutes by
[`.github/workflows/publish-trust-bundle.yml`](../../.github/workflows/publish-trust-bundle.yml):

- Mirror: `https://jedmckenna99.github.io/lemma-enterprise/trust-mirror/bloom-filter.json`

## How it works

1. `scripts/publish_trust_bundle.py` fetches the primary bundle.
2. The script verifies the trust-list and bloom signatures using the same
   pinned-root logic as `@lemma.id/proof-verifier` (fail closed).
3. On success, CI deploys the JSON to GitHub Pages (`gh-pages` branch,
   `trust-mirror/` folder).

The mirror is **not re-signed**. Integrity comes from the existing Ed25519
signatures inside the bundle; the mirror is transport redundancy only.

## Verifier failover

Backend and browser verifiers try URLs in order:

1. `{lemmaOrigin}/api/revocation/bloom-filter`
2. GitHub Pages mirror (default)

Override with `LEMMA_TRUST_BUNDLE_URLS` (comma-separated) or the
`trustBundleUrls` / `trust_bundle_urls` constructor option.

## Operator notes

- If the publish workflow fails, the mirror stops updating; verifiers continue
  using the primary URL and any still-valid cached snapshot.
- Do not point the mirror URL at unsigned JSON. The publish script and
  verifiers reject bundles that fail signature verification.
- See also [NETWORK_ROOT_ROTATION.md](../security/NETWORK_ROOT_ROTATION.md).
