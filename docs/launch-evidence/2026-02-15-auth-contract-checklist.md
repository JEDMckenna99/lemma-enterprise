# Evidence: Auth Contract Consistency Checklist

Date: 2026-02-15  
Environment: Production target (`https://lemma.id`)

## Contract requirements tracked

- `auth_required`
- `invalid_token`
- `token_expired`
- `token_revoked`
- `audience_mismatch`
- `missing_scope`
- `path_not_allowed`
- `max_operations_exceeded`
- `task_mismatch`

## Implemented in codebase

- `api/agent_credentials.py`
  - `validate_agent_token_with_reason()` provides deterministic token failure reasons.
  - `/api/agent/validate` returns machine-readable `error` values.
- `mcp-server/index.js`
  - centralized `authorizeThenExecute()` enforces consistent deny responses.

## Current runtime note

Live production runs still depend on:
- token validity at execution time
- wallet unlock state for issuance endpoints
- limiter windows during repeated issuance-heavy conformance passes
