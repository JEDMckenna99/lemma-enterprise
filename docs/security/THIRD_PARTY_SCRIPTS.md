# Third-party script origins (CSP `script-src`)

Lemma.id CSP allows only `'self'`, per-request nonces, and the origins below.
Each origin is marked with `# CSP-ALLOW:` in [`app.py`](../../app.py) for CI review.

| Origin | Purpose | Used on | Remove candidate? |
|--------|---------|---------|-------------------|
| `https://cdn.jsdelivr.net/npm/` | npm packages via jsDelivr | Various admin/developer tooling | Audit per-page need |
| `https://unpkg.com/` | html5-qrcode scanner | Admin QR flows | Scope to admin-only route CSP override |
| `https://js.stripe.com` | Stripe.js | IDV / billing (`/unlock`, wallet IDV) | Required |
| `https://challenges.cloudflare.com` | Cloudflare Turnstile | Bot protection surfaces | Audit usage |
| `https://static.cloudflareinsights.com` | Cloudflare Web Analytics | Global layout | Optional — remove if unused |

## Review checklist

Before adding a new `script-src` origin:

1. Add `# CSP-ALLOW: <reason>` comment in `app.py` next to the origin.
2. Document the route/template that requires it in this file.
3. Update [`tests/test_csp_security.py`](../../tests/test_csp_security.py) `EXPECTED_SCRIPT_ORIGINS`.
4. Prefer route-specific CSP overrides instead of expanding the global policy.

## XSS note

Third-party script compromise is equivalent to first-party XSS for pages that load the script.
Minimize global allowances; load payment and scanner scripts only on routes that need them.
