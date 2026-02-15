# Lemma.id Standalone Auth Contract v1

Date: 2026-02-15

Contract schema:
- `docs/STANDALONE_AUTH_CONTRACT_V1.json`

## Decision Object

- `allow: true|false`
- `error_code`: canonical machine code
- `reason`: optional human-readable summary
- `token_id`: optional credential id

## Canonical Error Codes

- `auth_required`
- `invalid_token`
- `token_expired`
- `token_revoked`
- `audience_mismatch`
- `missing_scope`
- `path_not_allowed`
- `max_operations_exceeded`
- `task_mismatch`
- `rate_limit_exceeded`

## Determinism Requirement

For identical input context, the same runtime version must emit the same `error_code`.

## Versioning Policy

- Non-breaking additions (new optional fields) keep `v1`.
- Any behavior/meaning change to existing codes requires `v2`.
