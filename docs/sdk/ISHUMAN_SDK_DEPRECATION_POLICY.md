# isHuman SDK deprecation policy

## Principles

1. **Protocol-first:** Signed artifact changes follow [`ISHUMAN_PROTOCOL_MIGRATION_POLICY.md`](../protocol/ISHUMAN_PROTOCOL_MIGRATION_POLICY.md).
2. **Immutable pins:** Production sites pin versioned SDK URLs (`/sdk/v{semver}/...`) with optional SRI.
3. **Rolling aliases:** Unversioned `/sdk/proof-verifier.js` remains available during deprecation windows but is not recommended for new integrations.
4. **Fail closed:** Removed SDK APIs must not degrade to unverified trust.

## Support windows

| Channel | Support | Notes |
|---|---|---|
| Current browser line (`1.9.x`) | Active | Default in integration guide |
| Current backend line (`1.4.x`) | Active | npm/PyPI + served `.mjs`/`.py` |
| Previous browser line | 90 days after successor GA | Security fixes only |
| Previous backend line | 90 days after successor GA | Security fixes only |

## Deprecation process

1. Bump [`ISHUMAN_SDK_VERSIONS.json`](ISHUMAN_SDK_VERSIONS.json) and run lockstep tests (`tests/test_sdk_integration_section10.py`).
2. Publish immutable versioned assets on lemma.id.
3. Update compatibility matrix and integration guide.
4. Add `Deprecation` / `Sunset` response headers on rolling alias routes when applicable.
5. Release npm/PyPI packages with semver tag and changelog.

## Demo mirrors

`demo-sites/lemma_*verify*.py` are **generated mirrors** of `packages/proof-verifier-py/` for subtree deploys. Run `python scripts/sync_proof_verifier_packages.py` before demo releases; CI fails on drift (`--check`).

Legacy `lemma_ishuman_*` mirror filenames remain for subtree compatibility but are deprecated.

## Breaking change examples (require major bump)

- Changing canonical message bytes for credentials or action stamps
- Removing `verifyStamp` / `verify_with_policy` fail-closed defaults
- Requiring new fields without backward-compatible verification path

Non-breaking (minor/patch):

- New optional verifier options
- Additional structured log fields
- Performance improvements with identical decisions on fixtures
