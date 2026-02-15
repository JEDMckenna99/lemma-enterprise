# Evidence: Principal-Aware Issuance Limiter

Date: 2026-02-15  
Environment: Production target (`https://lemma.id`)

## Implemented changes

- `auth/rate_limiter.py`
  - `get_issuance_identifier()` added (principal-first, IP fallback).
  - `credential_issue_limit()` now differentiates:
    - authenticated principal: `120 per hour` default
    - anonymous/IP fallback: `20 per hour` default
  - `rate_limit()` now supports `key_func` override and returns:
    - `retry_after`
    - `limit_scope` (`principal` or `ip`)
- `api/agent_credentials.py`
  - issuance endpoints now use:
    - `@rate_limit(credential_issue_limit, key_func=get_issuance_identifier)`

## Expected operational impact

- Legitimate admin issuance runs no longer collide solely due to shared IP.
- Abuse protection remains active with explicit scope metadata on 429 responses.
