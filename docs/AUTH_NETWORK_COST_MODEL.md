# Auth Network Cost Model (Lemma.id vs Traditional Auth)

Objective: estimate request volume and server dependency footprint for login + basic IAM.

This model focuses on:
- browser-to-auth-server request counts,
- backend dependency operations (DB/Redis),
- practical server footprint.

It intentionally does not estimate kWh directly; use request volume as the operational energy/cost proxy.

---

## 1) Inputs (spreadsheet variables)

Use these as columns in a sheet:

- `DAU` = daily active users
- `SitesPerUserPerDay` = average relying sites visited/user/day
- `ActiveHoursPerUserPerDay` = average hours with active tabs
- `AvgTabsOpen` = average concurrent authenticated tabs
- `LemmaIssueRate` = fraction of site visits requiring a new lemma issuance (0.0-1.0)
- `OidcLoginsPerUserPerDay` = average full OIDC login ceremonies/day

Default starting values (edit for your traffic):
- `DAU = 10000`
- `SitesPerUserPerDay = 3`
- `ActiveHoursPerUserPerDay = 2`
- `AvgTabsOpen = 2`
- `LemmaIssueRate = 0.30`
- `OidcLoginsPerUserPerDay = 1.2`

---

## 2) Lemma.id call model (current implementation)

### 2.1 Per-user daily browser calls

Core login/IAM path calls:
- `LemmaUnlockCalls = 1`
  - one unlock signal/day (`/api/wallet/signal-unlock`) when user unlocks on Lemma.id
- `LemmaGlobalSessionChecks = SitesPerUserPerDay`
  - first-check behavior (`/api/wallet/global-session`)
- `LemmaIssueCalls = SitesPerUserPerDay * LemmaIssueRate`
  - (`/api/wallet-auth/issue`) when local site lemma is missing

SSE reconnect traffic (current deployed defaults):
- stream rotates every ~10 minutes (`/api/events/revocations`)
- `LemmaSseRequestsPerUserPerDay = AvgTabsOpen * ActiveHoursPerUserPerDay * 6`
  - because `0.1 requests/min/tab = 6 requests/hour/tab`

Total per-user/day:
- `LemmaCallsPerUserPerDay = LemmaUnlockCalls + LemmaGlobalSessionChecks + LemmaIssueCalls + LemmaSseRequestsPerUserPerDay`

Total per-day:
- `LemmaCallsPerDay = DAU * LemmaCallsPerUserPerDay`

### 2.2 Backend dependency ops per call (approx)

- `/api/wallet/global-session`: ~1 DB read
- `/api/wallet/signal-unlock`: ~1 DB upsert + optional Redis pub/sub publish
- `/api/wallet-auth/issue`: ~1 DB read (site lookup) + optional DB write (permission tracking)
- `/api/events/revocations` connect/reconnect:
  - one app request lifecycle per reconnect,
  - one Redis pub/sub subscription context while stream is active

Implication: your auth decision path is local-first. SSE reconnect overhead is now much lower, but can still dominate if tab-hours are very high.

---

## 3) Traditional auth model (OIDC/SAML-style baseline)

For basic comparison, use this conservative baseline:

- `OidcCeremonyCalls = 6`
  - typical browser request sequence across authorize/login/callback/token/userinfo/session setup
- `TraditionalCallsPerUserPerDay = OidcLoginsPerUserPerDay * OidcCeremonyCalls`
- `TraditionalCallsPerDay = DAU * TraditionalCallsPerUserPerDay`

Optional introspection-heavy mode (API-side):
- If APIs introspect tokens per request, add:
  - `ApiRequestsPerUserPerDay * IntrospectionRate`
- This can dominate totals, but varies widely by architecture.

---

## 4) Worked example (with defaults)

Using defaults:
- `DAU = 10000`
- `SitesPerUserPerDay = 3`
- `ActiveHoursPerUserPerDay = 2`
- `AvgTabsOpen = 2`
- `LemmaIssueRate = 0.30`
- `OidcLoginsPerUserPerDay = 1.2`

Lemma per-user/day:
- Unlock: `1`
- Global session checks: `3`
- Issue: `0.9`
- SSE reconnect: `2 * 2 * 6 = 24`
- Total: `28.9 calls/user/day`

Lemma total/day:
- `289,000 calls/day`

Traditional OIDC per-user/day:
- `1.2 * 6 = 7.2 calls/user/day`

Traditional total/day:
- `72,000 calls/day`

Observation:
- SSE reconnect behavior remains the main transport driver.
- Local-proof login/IAM path itself is low-call (single digits to low tens per user/day in common usage).

---

## 5) Infrastructure footprint comparison

### Lemma.id (current code path)

Minimum practical services:
- Auth/API app (Flask/Gunicorn)
- Postgres (passkeys, site registry, global session records, permission tracking)
- Redis (challenge store, rate limiting, session revocation blacklist, SSE pub/sub)

### Traditional (self-hosted IAM baseline)

Typical services:
- App backend
- IAM/IdP service (Keycloak/Auth0 equivalent)
- IdP database
- Optional cache/queue

If using managed IdP, your infra burden shifts to vendor, but per-event network still traverses vendor endpoints.

---

## 6) Scenario table template

Paste this into a sheet and compute formulas:

| Scenario | DAU | Sites/User/Day | Hours/User/Day | Tabs | IssueRate | OIDC Logins/User/Day |
|---|---:|---:|---:|---:|---:|---:|
| Low | 1,000 | 2 | 1 | 1.2 | 0.20 | 0.8 |
| Medium | 10,000 | 3 | 2 | 2.0 | 0.30 | 1.2 |
| High | 50,000 | 5 | 4 | 2.5 | 0.40 | 2.0 |

Suggested computed columns:
- `LemmaCalls/User/Day`
- `LemmaCalls/Day`
- `OIDCCalls/User/Day`
- `OIDCCalls/Day`
- `LemmaMinusOIDC`

---

## 7) Immediate cost lever

Highest-impact optimization:
- reduce forced SSE reconnect frequency (or switch to async workers with longer-lived streams).

If stream rotation moves from ~20s to 10 minutes:
- reconnect request rate drops from `3/min/tab` to `0.1/min/tab` (~30x reduction).

This preserves your local-proof auth advantages while reducing baseline request load and dyno overhead.

---

## 8) Structural-cheap mode (target)

To be structurally cheaper than traditional auth/providers while keeping cross-device/site SSO:

- Keep local proof as the default authorization path (`0` network calls on warm auth decisions).
- Keep SSE long-lived and stable (few reconnects per active hour).
- Throttle redundant global-session rechecks on focus/visibility churn (SDK now caches/reuses results for 60s unless forced).

Recommended operating targets:
- `Requests/min/active_tab` from SSE reconnects: `<= 0.1`
- Warm authorization path calls: `0`
- Cross-device signout p95 when SSE connected: `< 3s`
- Fallback-only mode worst-case detection: bounded by poll interval

Break-even helper:
- `LemmaCheaperThanOIDC` when:
  - `LemmaUnlockCalls + LemmaGlobalSessionChecks + LemmaIssueCalls + LemmaSseRequestsPerUserPerDay`
  - `< OidcCeremonyCalls * OidcLoginsPerUserPerDay`

Interpretation:
- Local proof removes many traditional online checks.
- SSE/session sync must stay low-churn for total cost leadership.
