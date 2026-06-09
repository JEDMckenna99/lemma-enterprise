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

### CSP alert thresholds (Sentry)

Configure a Sentry alert rule (lemma-enterprise project):

| Signal | Threshold | Action |
|--------|-----------|--------|
| `security=csp` tagged events | > 10 in 5 minutes | Page on-call; open incident channel |
| Same `blocked_uri` on `/unlock` or `/wallet/*` | > 3 in 15 minutes | Treat as possible XSS attempt; run §1 user guidance if user-reported |
| `violated_directive=script-src` spike sitewide | > 25 in 5 minutes | Check recent deploy; consider rollback |

**Escalation path:** Sentry alert → on-call acknowledges within 15m → triage using this runbook §1–4 → if wallet paths affected, notify Security Lead and capture evidence under `ops/evidence/launch/*incident-drill*`.

**Dry-run verification:** POST a sample report (returns `204`):

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST https://lemma.id/api/security/csp-report \
  -H "Content-Type: application/csp-report" \
  -d '{"csp-report":{"violated-directive":"script-src","blocked-uri":"https://drill.example.invalid","document-uri":"https://lemma.id/unlock"}}'
```

Confirm the event appears in Sentry with tag `security=csp`.

## 4. Post-incident hardening

- Identify the injection vector (template bug, third-party script, stored content).
- Add regression test or CSP CI guard if the class of bug is new.
- Consider temporary `LEMMA_DISABLE_DAILY_UNLOCK=true` on affected environments while patching.
