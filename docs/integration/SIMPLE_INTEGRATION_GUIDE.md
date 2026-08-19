# lemma.id integration guide

Local-first proof continuity for relying sites: verify signed presentations,
enforce policy on site-private PPIDs + assurance, optional action stamps and
site-block. Passkey unlock mints presentations; optional session cookies are
your responsibility.

**Start here for why:** [Continuity & abuse](CONTINUITY_AND_ABUSE.md)  
**Canonical source of truth:** [ISHUMAN Agent Integration Guide](ISHUMAN_AGENT_INTEGRATION.md)

For a shorter walkthrough, see [Quick start: verify a lemma proof](QUICK_START_SIMPLE_LOGIN.md).

---

## Architecture

```
Browser (your site)
  └─ ProofVerifier.verifyForBackend({ requiredAssurance: 'ishuman' })
       └─ Lemma popup → signed presentation
Your backend
  └─ Local verifier (npm or Python drop-in)
       └─ ppid + assurance → enforce policy (block / stamp / optional session)
```

lemma.id is not in the hot path after trust-list refresh. Your server verifies signatures locally.

---

## 1. Embed the SDK

**Recommended: drop-in button (mint a presentation)**

```html
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
<script src="https://lemma.id/sdk/lemma-signin.js"></script>
<lemma-signin site-id="app.example.com"></lemma-signin>
```

Listen for `lemma-signin-success` / `lemma-signin-error` events (see [Quick start](QUICK_START_SIMPLE_LOGIN.md)).

**Advanced: SDK only:**

```html
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
```

```javascript
const verifier = new ProofVerifier({ siteId: window.location.hostname });
```

Use the canonical hostname in production (e.g. `app.example.com`). Internal `site_...` database ids are never runtime `siteId` values.

---

## 2. Gate a sensitive action

```javascript
const { ok, presentation, ppid, assurance, reason } = await verifier.verifyForBackend({
  autoProvision: true,
  requiredAssurance: 'ishuman',
});

if (!ok) {
  // Fail closed: show retry UI
  console.error(reason);
  return;
}

await fetch('/api/gate', {
  method: 'POST',
  credentials: 'include',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ presentation }),
});
```

Call `verifyForBackend` only from user-initiated actions (button click).

Use `'passkey'` for continuity-only gates; `'ishuman'` for Sybil-sensitive actions.

---

## 3. Verify on your server

Install the verifier for your stack:

| Runtime | Package |
|---------|---------|
| Node 18+ | `@lemma.id/proof-verifier` (npm) |
| Python | Copy [`lemma_proof_verifier.py`](https://lemma.id/sdk/proof-verifier.py) until PyPI publish |

```javascript
// Node
const verifier = createVerifier({ siteId: 'app.example.com', requiredAssurance: 'ishuman' });
const result = await verifier.verify(presentation);
```

```python
# Python
ctx = VerificationContext(site_id="app.example.com", required_assurance="ishuman")
result = ctx.verify(presentation)
```

Enforce on `result.ppid` and `result.assurance`. Fail closed when `ok` is false.

---

## 4. Abuse controls (site-block)

Do not rely on the browser to enforce bans. Use server-side site-block when a
PPID must stay blocked across IDV, recovery, and credential rotation.

| Need | Registration |
|------|----------------|
| Local verify + gate | None |
| `POST /api/ishuman/site-block` etc. | Register site + domain verification + API key |

See [Continuity & abuse](CONTINUITY_AND_ABUSE.md) for block/doubt/check patterns.

Keys are for **enforcement**, not for the verify path itself.

---

## 5. Action stamps (T2+)

For fraud-sensitive mutations, attach action-bound proofs with `stampAction` and
verify with `verifyActionStamp()` plus a nonce store. See the canonical guide
for presale/tickets reference flows.

---

## 6. isHuman step-up (Sybil-sensitive actions)

Same integration; stricter assurance:

```javascript
requiredAssurance: 'ishuman'
```

Use for signup bonuses, trials, tickets, payouts, or IDV-backed person policies
(document uniqueness, not biometric unique-human). Same PPID across tiers.

---

## 7. Session layer (optional: your responsibility)

Lemma does not issue relying-site session cookies. If you want passwordless login,
after verification:

1. `findOrCreateUser(ppid)`
2. Set HttpOnly, Secure, SameSite session cookie
3. Guard protected routes with your middleware
4. `POST /logout` clears the cookie

Many sites keep existing auth and use lemma only on gated actions.

See runnable examples under [`examples/`](../../examples/).

---

## 8. Localhost workflow

| Topic | Behavior |
|-------|----------|
| `siteId` | Page hostname; `localhost` for all local ports |
| Popup | Hosted on lemma.id; works with local relying origin |
| Mismatch | Dev warns if browser/backend hostnames differ |

---

## 9. Recovery policy

- **Passkey continuity:** passkey vault sync does **not** sync lemma.id contents.
  Same-person cross-device continuity requires [lemma.id/link](https://lemma.id/link)
  (or isHuman / site-side recovery). Encourage second device for everyone.
- **isHuman step-up:** same PPID, stronger recovery assurances.

Do not promise email/password-style recovery for passkey-only accounts. See [Trust & availability](SIGN_IN_TRUST_AND_RECOVERY.md).

---

## 10. Profile data (you own it)

lemma.id returns **`ppid`** and **`assurance`**: not email, name, or avatar. Collect profile fields in your app and key them to the verified `ppid`.

---

## 11. Link lemma proof to an existing account

When users already have a password/OAuth account, verify a presentation while they are logged in, then attach the PPID:

1. User signed in with your existing auth.
2. User clicks "Verify with lemma.id" → `verifyForBackend({ requiredAssurance: 'passkey' })`.
3. Backend verifies presentation; attach `lemma_ppid` to the current session user.
4. Use lemma on gated actions keyed to that PPID.

Never link on a bare client `ppid` without presentation verification.

### Legacy SDK redirect callback (retired)

`/auth/sdk-callback` does **not** verify a presentation or bind a subject. It
returns `lemma_auth=error&reason=callback_unbound`. Use `<lemma-signin>` /
`ProofVerifier.verifyForBackend` and POST the presentation to your backend.

---

## 12. Sign-out semantics

Two independent layers:

| Layer | Who controls | What it does |
|-------|--------------|--------------|
| **Site session** | Your backend | Clear your HttpOnly cookie on `POST /logout`. User is signed out of your app only. |
| **lemma.id site disconnect** | User / lemma.id | Revocation and bloom snapshot updates can invalidate cached site proofs. SDK polling surfaces "sign out everywhere" style disconnect for that site binding. |

Document both for support: logging out of your site does not delete the user's lemma.id.

---

## 13. What lemma.id does not provide

| Expectation | Reality | Alternative |
|-------------|---------|-------------|
| User management dashboard | No: privacy by design | Your DB is the user list; key rows by `ppid` |
| Webhooks on login/revoke | No: hard product rule | Poll bloom snapshot / use SDK `checkStatus()` for revocation |
| Email/name from lemma.id | No | Collect after verify in your UI |
| Site registration for basic verify | No | Optional API keys only for abuse APIs |
| Replace your login stack | No: optional | Gate actions only; keep OAuth/email |

---

## Do not use (legacy)

- `lemma-wallet.js` + `startRedirectFlow()` redirect login
- Bare client `ppid` without presentation verification
- `X-Lemma-Credential` as the relying-site login protocol

These patterns are superseded by presentation verification.
