# Revocation Path Post-Deploy Check (2026-02-11)

Raw output: `docs/launch-evidence/2026-02-11-revocation-path-post-deploy.txt`

## Test Performed

- Issued a controlled test revocation request on production:
  - `POST /api/wallet/revoke` with a unique `credential_id`.
- Then checked:
  - `GET /api/v1/revocation/list`
  - `GET /api/revocation/bloom-filter`

## Observed Result

- API returned `success=true` but `site_updated=false`.
- Test credential did **not** appear in revocation list.
- Test credential hash did **not** appear in `hashed_revoked_ids`.

## Conclusion

- This reveals a launch-blocking behavior gap in site-specific revocation persistence/visibility.
- Follow-up code remediation is required and must be re-validated post-deploy.

