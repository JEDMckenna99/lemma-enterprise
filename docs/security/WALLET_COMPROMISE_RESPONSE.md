# Wallet compromise response

Use this runbook when XSS, malware-in-browser, or suspected secret exfiltration
on lemma.id is detected or reported.

## 1. User actions (immediate)

1. **Lock the wallet** — use Lock in the wallet UI or call `LemmaWallet.lock()`.
2. **Clear site data** for `lemma.id` (IndexedDB + localStorage) if compromise is confirmed.
3. **Re-unlock with passkey** only after clearing, on a trusted device/browser.

## 2. Revoke and reissue

1. Call the reissue flow: `POST /api/ishuman/reissue-master` (requires wallet assertion).
2. This revokes the prior master credential id server-side; stale local copies cannot replay.
3. Complete IDV again if the account has no valid verified master record.

See [`THREAT_MODEL.md`](THREAT_MODEL.md) §3.3–3.4 for design rationale.

## 3. Operator monitoring

- Watch CSP reports: `POST /api/security/csp-report` logs + Sentry `security=csp` tags.
- Alert on spikes in Sentry errors under `/wallet/*`, `/unlock`, `/app`.
- Review [`THIRD_PARTY_SCRIPTS.md`](THIRD_PARTY_SCRIPTS.md) after any CSP violation involving third-party origins.

## 4. Post-incident hardening

- Identify the injection vector (template bug, third-party script, stored content).
- Add regression test or CSP CI guard if the class of bug is new.
- Consider temporary `LEMMA_DISABLE_DAILY_UNLOCK=true` on affected environments while patching.
