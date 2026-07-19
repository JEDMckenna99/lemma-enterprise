# Wallet Cookie SameSite Inventory

Status: living record for production-readiness Section 2.

## Why `SameSite=None` still exists

Cross-site wallet unlock and session-sync require the lemma.id session cookie
to be presented on credentialed requests from relying-site origins. Browsers
only send those cookies cross-site when `SameSite=None; Secure`.

Ambient cookie authentication is therefore CSRF-sensitive. Global CSRF middleware
exempts `/api/wallet/` because those cookies are intentionally cross-site; each
cookie-authenticated mutation must enforce double-submit CSRF in-handler.

## Cookie inventory

| Cookie | Purpose | SameSite | Secure | HttpOnly | Mutation defense |
|---|---|---|---|---|---|
| `lemma_wallet_session` | Server-trusted wallet unlock state | `None` | yes | yes | Required only for listed refresh/clear/link/CLI routes; paired with CSRF |
| `lemma_wallet_csrf` | Double-submit CSRF token for wallet cookie routes | `None` | yes | no | Compared to `X-Lemma-CSRF` or form `csrf_token` |
| `lemma_csrf_token` | App/session CSRF for non-wallet browser routes | `Lax` | yes | no | Global CSRF middleware |

## Cookie-authenticated wallet mutations

These handlers accept ambient wallet session cookies and must call
`_validate_csrf()` (or equivalent) before mutation:

- `POST /api/wallet/signal-unlock` (refresh path)
- `POST /api/wallet/clear-session`
- `POST /api/wallet/link-unlock-token`
- `POST /api/wallet/cli-link/approve`

Ceremony routes that mint the first trusted session (`session-unlock/complete`)
and device enrollment (`device-enroll/*`) authenticate with WebAuthn rather than
an existing ambient session cookie.

## Minimization policy

1. Prefer WebAuthn or wallet assertion over ambient cookies for authority changes.
2. Keep `SameSite=None` only for cookies that must be readable on cross-site
   credentialed calls to lemma.id.
3. Do not expand the global `/api/wallet/` CSRF exemption to other prefixes.
4. Before Section 2 `PASS`, capture browser matrix evidence for Chrome, Safari,
   and Firefox covering enroll → unlock → transfer → revoke on lemma.id and one
   relying-site origin.
