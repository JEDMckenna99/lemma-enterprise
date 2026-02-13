# Lemma Auth Contract v1 (Launch Profile)

Status: Draft (implementation target)
Owner: Lemma.id
Scope: Admin + Developer + Agent-protected API endpoints

## 1) Goals

- One canonical auth contract for protected endpoints
- Deterministic auth outcomes (no ambiguous 401/403 behavior)
- Stable error taxonomy for test automation and integrators

---

## 2) Accepted Authentication Methods (in precedence order)

For protected endpoints (`/api/admin/*`, `/api/developer/*`, `/api/agent/credentials*`):

1. **Agent token**
   - Header: `X-Agent-Token: <lm_agent_...>`
2. **Agent session cookie**
   - Established via `/api/agent/session?token=...`
3. **Credential headers (edge-verified credential id path)**
   - `X-Credential-ID: <credential_id>`
   - `X-Permission-ID: <permission>`
4. **API key**
   - `X-API-Key: lemma_...`
   - OR `Authorization: Bearer lemma_...`

If multiple methods are present, server evaluates in the order above and uses first valid method.

---

## 3) Scope Requirements

### 3.1 Admin-protected endpoints (`require_admin` / `require_site_admin`)

- Required scope for agent token/session: `admin`
- Credential path requirement: permission must satisfy admin set
  - allowed: `admin_access`, `super_admin`, `admin`, `superadmin`, `site_admin`

### 3.2 Developer-protected endpoints (`require_customer_or_admin` / optional auth + policy)

- Agent token/session must include either:
  - `admin` OR
  - a developer scope defined by endpoint policy (recommended canonical scope: `developer`)

> Note: Current code uses mixed policy surfaces. v1 requires each protected endpoint to declare required scopes explicitly.

---

## 4) HTTP Status Semantics

- `401 Unauthorized`
  - Missing auth, invalid token/key, expired, revoked, malformed credential headers
- `403 Forbidden`
  - Authenticated but lacking required scope/permission

No endpoint should return `401` for scope failure once auth identity is established.

---

## 5) Canonical Error Payload

All auth failures MUST return JSON:

```json
{
  "error": "<machine_code>",
  "message": "<human_message>",
  "auth_method": "agent_token|agent_session|credential|api_key|none",
  "required_scope": ["..."],
  "provided_scope": ["..."]
}
```

### 5.1 Allowed `error` codes

- `auth_required`
- `invalid_token`
- `token_expired`
- `token_revoked`
- `invalid_api_key`
- `credential_revoked`
- `missing_permission`
- `missing_scope`

---

## 6) Validation Contract: `/api/agent/validate`

Required behavior:

- With valid `X-Agent-Token`: `200` + `{ valid: true, scope: [...] }`
- With invalid/expired/revoked token: `401` + `{ valid: false, error: <machine_code> }`
- With no token/session: `200` + `{ valid: false, error: "auth_required" }`

This endpoint is the mandatory test preflight gate.

---

## 7) Test Suite Gate Requirements

Before running any suite that hits protected endpoints:

1. Call `/api/agent/validate` with configured token
2. Abort suite if `valid !== true`
3. Print explicit stop reason:
   - invalid token
   - missing admin scope
   - no session

---

## 8) Endpoint Classification (v1 initial)

### Admin (must require `admin`)

- `/api/admin/user-stats`
- `/api/admin/platform-stats`
- `/api/admin/recent-activity`
- `/api/admin/customers`
- `/api/admin/sites`

### Agent management

- `/api/agent/credentials` (authenticated principal required)
- `/api/agent/credentials/*` (issue/revoke/audit = policy-defined, typically admin)

### Public/non-protected

- `/api/health`
- `/api/health/detailed`
- `/api/agent/validate` (returns auth state, not protected data)

---

## 9) Immediate Implementation Tasks

1. Normalize auth error payloads in `auth/decorators.py`
2. Ensure all admin endpoints use one of: `require_admin` or `require_site_admin`
3. Ensure developer endpoints document required scopes
4. Update test harness:
   - preflight hard-stop on failed `/api/agent/validate`
   - classify 401 vs 403 separately in reports

---

## 10) Launch Exit Criteria (Auth Contract)

- `/api/agent/validate` preflight pass is deterministic
- No ambiguous 401 where 403 is expected
- All protected endpoint failures return canonical machine error
- Protected API tests fail only for real functional defects, not auth ambiguity
