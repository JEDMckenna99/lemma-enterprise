# Transport/TLS Evidence (2026-02-11)

Non-destructive transport security checks run against production `https://lemma.id`.

Raw output: `docs/launch-evidence/2026-02-11-transport-tls-checks.txt`

## Checks Performed

- HTTP to HTTPS behavior:
  - `curl -I -L --max-redirs 5 http://lemma.id`
- TLS version behavior:
  - `curl -I --tls-max 1.1 https://lemma.id` (expected handshake failure)
  - `curl -I --tlsv1.2 https://lemma.id` (expected success)

## Observed Results

- HTTP request returned `301 Moved Permanently` with `Location: https://lemma.id/`, then final `200 OK` on HTTPS.
- TLS <= 1.1 attempt failed with Schannel handshake error (`curl: (35)`).
- TLS 1.2 request succeeded with `200 OK`.

## Launch-Gate Interpretation

- Strong evidence that production traffic is HTTPS-enforced.
- Strong evidence that obsolete TLS protocols are rejected and TLS 1.2+ works.
- This is a point-in-time production validation and should be periodically re-run.

