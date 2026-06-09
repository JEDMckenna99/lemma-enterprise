# Third-party script origins (CSP `script-src`)

Lemma.id CSP uses **route profiles** built by `build_content_security_policy()` in [`app.py`](../../app.py).
Global pages use the `strict` profile (`'self'` + per-request nonce only).

## Route profiles

| Profile | Routes | Extra `script-src` origins |
|---------|--------|----------------------------|
| `strict` | All routes by default | *(none)* |
| `unlock_idv` | `/unlock`, `/wallet/unlock`, `/wallet/popup`, `/wallet/ishuman-idv` | `js.stripe.com`, `challenges.cloudflare.com` |
| `link_qr` | `/link`, `/wallet/link` | `unlock_idv` origins + `unpkg.com` (html5-qrcode) |

`connect-src`, `frame-src`, and `form-action` expand on `unlock_idv` / `link_qr` for Stripe and Turnstile.

## Removed from global policy

| Origin | Reason |
|--------|--------|
| `https://static.cloudflareinsights.com` | Not loaded in layout templates |
| `https://cdn.jsdelivr.net/npm/` | No current template dependency; add via route profile if needed |

## Template map

| Origin | Template / route | Profile |
|--------|------------------|---------|
| `https://unpkg.com/` | [`templates/wallet_link.html`](../../templates/wallet_link.html) | `link_qr` |
| `https://js.stripe.com` | Wallet unlock / IDV flows (dynamic load) | `unlock_idv`, `link_qr` |
| `https://challenges.cloudflare.com` | Turnstile surfaces on wallet flows | `unlock_idv`, `link_qr` |

## Review checklist

Before adding a new `script-src` origin:

1. Add `# CSP-ALLOW: <reason>` comment in `build_content_security_policy()` next to the origin.
2. Document the route/template that requires it in this file.
3. Extend [`tests/test_csp_security.py`](../../tests/test_csp_security.py) profile expectations.
4. Prefer route-specific CSP profiles instead of expanding the global `strict` policy.

## XSS note

Third-party script compromise is equivalent to first-party XSS for pages that load the script.
Minimize global allowances; load payment and scanner scripts only on routes that need them.
