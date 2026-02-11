# Origin/CORS and DOM Safety Evidence (2026-02-11)

This evidence combines runtime CORS checks on production auth endpoints and static scanning for risky DOM/script patterns.

## Runtime Origin/CORS Validation

Raw output: `docs/launch-evidence/2026-02-11-origin-cors-checks.txt`

Endpoint tested: `POST/OPTIONS https://lemma.id/api/passkey/authenticate/begin`

Observed behavior:

- Allowed origin (`https://lemma.id`):
  - `OPTIONS` returned `200` with:
    - `Access-Control-Allow-Origin: https://lemma.id`
    - `Access-Control-Allow-Credentials: true`
  - `POST` returned `200` with:
    - `Access-Control-Allow-Origin: https://lemma.id`
    - `Access-Control-Allow-Credentials: true`
- Disallowed origin (`https://evil.example`):
  - `POST` returned `200` **without** `Access-Control-Allow-Origin`, so browser JS cannot read response.
  - `OPTIONS` returned `200` with `Access-Control-Allow-Origin: *` (non-credentialed preflight response).

Interpretation:

- Main credentialed CORS path appears origin-restricted on POST response headers.
- Preflight wildcard behavior for disallowed origins should be reviewed for strictness consistency.

## Static Scan: eval / innerHTML

Scan commands:

- `rg "\\beval\\s*\\("`
- `rg "innerHTML\\s*="`
- `rg "innerHTML\\s*=\\s*`[^`]*\\$\\{"`

Key findings:

- No direct `eval(` usage in primary app runtime paths.
- `innerHTML` usage exists in multiple templates/scripts.
- Dynamic `innerHTML` interpolation exists, including:
  - `templates/wallet_simple.html` using `${e.message}` directly in `innerHTML`.
  - Several admin/demo/docs pages using template interpolation into `innerHTML`.
  - `static/js/lemma-wallet.js` uses `escapeHtml(log.message)` before interpolation (safer pattern).

Interpretation:

- Control "`No eval() or innerHTML with data`" is **not fully met** because at least one dynamic `innerHTML` insertion with unescaped error text is present.
- Remediation should migrate dynamic content to `textContent` or sanitize at the insertion point.

