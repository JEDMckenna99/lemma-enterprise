# Agent Monitoring API

Use these endpoints to monitor delegated agent token activity from your own UI.

Base URL examples:
- Production: `https://lemma.id`
- Local: `http://localhost:5000`

---

## Authentication

Any one of the following is supported on monitoring endpoints:

- `X-API-Key: <site_api_key>` (recommended for external/custom dashboards)
- `X-Lemma-Credential: <base64url(full permission lemma)>`
- `X-Agent-Token: lm_agent_...`
- Browser session cookie (`customer_id`)

---

## Endpoints

### 1) List Delegated Tokens

`GET /api/agent/monitor/tokens`

Query params:
- `include_revoked` (`true|false`, default: `false`)
- `limit` (`1-500`, default: `100`)

Example:

```bash
curl -s "https://lemma.id/api/agent/monitor/tokens?include_revoked=true&limit=200" \
  -H "X-API-Key: lemma_xxx"
```

Response (example):

```json
{
  "success": true,
  "auth_method": "api_key",
  "tokens": [
    {
      "token_id": "agt_abc123",
      "agent_name": "Cursor AI",
      "scope": ["read", "write"],
      "allowed_paths": ["/api/sites/*"],
      "max_operations": 500,
      "use_count": 81,
      "operations_remaining": 419,
      "task_deviation_count": 2,
      "last_used_at": "2026-02-11T16:40:10Z",
      "issued_at": "2026-02-11T14:00:00Z",
      "expires_at": "2026-02-11T18:00:00Z",
      "revoked": false,
      "revoked_at": null,
      "description": "Launch test run",
      "status": "active"
    }
  ]
}
```

---

### 2) Event Stream (Detailed Activity)

`GET /api/agent/monitor/events`

Query params:
- `token_id` (optional)
- `status` (`all|success|failure`, default: `all`)
- `hours` (`1-720`, default: `24`)
- `limit` (`1-1000`, default: `200`)

Example:

```bash
curl -s "https://lemma.id/api/agent/monitor/events?token_id=agt_abc123&status=failure&hours=24&limit=300" \
  -H "X-API-Key: lemma_xxx"
```

Response (example):

```json
{
  "success": true,
  "auth_method": "api_key",
  "window_hours": 24,
  "events": [
    {
      "token_id": "agt_abc123",
      "action": "GET:/api/agent/credentials",
      "resource": null,
      "method": "GET",
      "path": "/api/agent/credentials",
      "status_code": 200,
      "success": true,
      "path_allowed": true,
      "task_deviation": false,
      "deviation_reason": null,
      "timestamp": "2026-02-11T16:39:15Z"
    }
  ]
}
```

---

### 3) Summary Metrics

`GET /api/agent/monitor/summary`

Query params:
- `token_id` (optional)
- `hours` (`1-720`, default: `24`)

Example:

```bash
curl -s "https://lemma.id/api/agent/monitor/summary?hours=24" \
  -H "X-API-Key: lemma_xxx"
```

Response (example):

```json
{
  "success": true,
  "auth_method": "api_key",
  "window_hours": 24,
  "token_id": null,
  "summary": {
    "total_actions": 81,
    "success_count": 78,
    "failure_count": 3,
    "denied_count": 2,
    "deviation_count": 1,
    "unique_paths": 12,
    "last_seen_at": "2026-02-11T16:40:10Z",
    "top_paths": [
      {"path": "/api/agent/credentials", "count": 25}
    ],
    "status_codes": [
      {"status_code": 200, "count": 78},
      {"status_code": 403, "count": 2},
      {"status_code": 500, "count": 1}
    ]
  }
}
```

---

## Revoke Token (Kill Switch)

Use existing revoke endpoint:

`POST /api/agent/credentials/<token_id>/revoke`

Example:

```bash
curl -s -X POST "https://lemma.id/api/agent/credentials/agt_abc123/revoke" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: lemma_xxx" \
  -d '{"reason":"Manual revoke from custom dashboard"}'
```

---

## Suggested Custom Dashboard Widgets

- Active tokens table (`/monitor/tokens`)
- Last 24h summary cards (`/monitor/summary`)
- Recent events stream (`/monitor/events`)
- Failure-only stream (`status=failure`)
- Token drill-down (`token_id=<...>`)

---

## Security Notes

- Prefer short TTL agent tokens and strict `allowed_paths`.
- Alert on non-zero `denied_count` or `deviation_count`.
- Revoke and rotate any shared testing token after validation runs.
