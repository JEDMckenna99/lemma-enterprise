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

## One-time npm Trusted Publisher setup

On [npmjs.com](https://www.npmjs.com) → `@lemma.id/proof-verifier` → **Settings** → **Trusted Publisher**:

| Field | Value |
|---|---|
| Publisher | GitHub Actions |
| Organization or user | `JEDMckenna99` |
| Repository | `lemma-enterprise` |
| Workflow filename | `proof-verifier-release.yml` |
| Environment name | *(leave blank)* |
| Allowed actions | Allow npm publish |

No `NPM_TOKEN` GitHub secret is required. Publishing uses OIDC from that workflow on tag pushes.

## Publish

1. Commit version bumps on `main` (or the release branch you will tag).
2. Tag: `proof-verifier-v{backend_verifier}` (e.g. `proof-verifier-v1.4.1`). Legacy tag `ishuman-verify-v*` still triggers the workflow.
   ```powershell
   git tag proof-verifier-v1.4.1
   git push github proof-verifier-v1.4.1
   ```
3. Watch GitHub Actions `proof-verifier-release`:
   - Tag push → build, test, npm OIDC publish, PyPI upload
   - Manual `workflow_dispatch` → build/test only (no registry publish)
4. Deploy lemma.id if CDN/versioned `/sdk/v…` routes or `/api/sdk/versions` changed.
5. Run prod + registry smoke:
   ```powershell
   python scripts/section10_prod_smoke.py
   python scripts/section10_registry_smoke.py --require-registry
   ```
   Update `EXPECTED_VERSION` in `scripts/section10_registry_smoke.py` when bumping.

## Registry auth

| Registry | Auth |
|---|---|
| npm `@lemma.id/proof-verifier` | Trusted Publisher OIDC (workflow above) |
| PyPI `lemma-proof-verifier` | GitHub Actions secret `PYPI_API_TOKEN` |

## Post-release

1. Record evidence in [`HUMAN_BACKED_AUTHENTICATOR_PRODUCTION_READINESS.md`](../status/HUMAN_BACKED_AUTHENTICATOR_PRODUCTION_READINESS.md) Section 10.
2. Announce in release notes (breaking changes per [`ISHUMAN_SDK_DEPRECATION_POLICY.md`](../sdk/ISHUMAN_SDK_DEPRECATION_POLICY.md)).
