# isHuman SDK release checklist

## Pre-release

1. Update [`docs/sdk/ISHUMAN_SDK_VERSIONS.json`](../sdk/ISHUMAN_SDK_VERSIONS.json) (browser + backend semver lines).
2. Bump `@version` comments in `static/js/ishuman-verifier.js` and `static/js/proof-verifier.mjs`.
3. Align `packages/proof-verifier-js/package.json` and `packages/proof-verifier-py/pyproject.toml`.
4. Run package sync:
   ```powershell
   python scripts/sync_proof_verifier_packages.py
   python scripts/sync_proof_verifier_packages.py --check
   ```
5. Run tests:
   ```powershell
   python -m pytest tests/test_sdk_integration_section10.py tests/test_ishuman_verify_packages.py tests/test_protocol_fixtures_section4.py -q
   python scripts/generate_sri_hashes.py
   ```
6. Update [`ISHUMAN_SDK_COMPATIBILITY_MATRIX.md`](../sdk/ISHUMAN_SDK_COMPATIBILITY_MATRIX.md) and integration guide if URLs changed.

## Publish

1. Tag: `proof-verifier-v{backend_verifier}` (e.g. `proof-verifier-v1.4.0`). Legacy tag `ishuman-verify-v*` still triggers the workflow.
2. Push tag → GitHub Actions `proof-verifier-release.yml` builds npm + PyPI artifacts.
3. Deploy lemma.id (versioned routes + `/api/sdk/versions`).
4. Run prod smoke:
   ```powershell
   python scripts/section10_prod_smoke.py
   python scripts/section10_registry_smoke.py
   python scripts/section10_registry_smoke.py --require-registry
   ```

## Registry secrets (GitHub Actions)

- `NPM_TOKEN` — publish `@lemma.id/proof-verifier`
- `PYPI_API_TOKEN` — publish `lemma-proof-verifier`

## Post-release

1. Record evidence in [`HUMAN_BACKED_AUTHENTICATOR_PRODUCTION_READINESS.md`](../status/HUMAN_BACKED_AUTHENTICATOR_PRODUCTION_READINESS.md) Section 10.
2. Announce in release notes (breaking changes per [`ISHUMAN_SDK_DEPRECATION_POLICY.md`](../sdk/ISHUMAN_SDK_DEPRECATION_POLICY.md)).
