# Sign in with lemma.id — integration guide

Passwordless login using passkeys and site-private PPIDs. This guide matches the current `ProofVerifier` contract.

**Canonical source of truth:** [ISHUMAN Agent Integration Guide](ISHUMAN_AGENT_INTEGRATION.md)

For a shorter walkthrough, see [QUICK_START_SIMPLE_LOGIN.md](QUICK_START_SIMPLE_LOGIN.md).

---

## Architecture

```
Browser (your site)
  └─ ProofVerifier.verifyForBackend({ requiredAssurance: 'passkey' })
       └─ Lemma popup → signed presentation
Your backend
  └─ Local verifier (npm or Python drop-in)
       └─ ppid → your user row → your session cookie
```

lemma.id is not in the hot path after trust-list refresh. Your server verifies signatures locally.

---

## 1. Embed the SDK

**Recommended — drop-in button:**

```html
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
<script src="https://lemma.id/sdk/lemma-signin.js"></script>
<lemma-signin site-id="app.example.com"></lemma-signin>
```

Listen for `lemma-signin-success` / `lemma-signin-error` events (see [QUICK_START_SIMPLE_LOGIN.md](QUICK_START_SIMPLE_LOGIN.md)).

**Advanced — SDK only:**

```html
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
```

```javascript
const verifier = new ProofVerifier({ siteId: window.location.hostname });
```

Use the canonical hostname in production (e.g. `app.example.com`). Internal `site_...` database ids are never runtime `siteId` values.

---

## 2. Sign in (passkey tier)

```javascript
const { ok, presentation, ppid, assurance, reason } = await verifier.verifyForBackend({
  autoProvision: true,
  requiredAssurance: 'passkey',
});

if (!ok) {
  // Fail closed — show retry UI
  console.error(reason);
  return;
}

await fetch('/api/login', {
  method: 'POST',
  credentials: 'include',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ presentation }),
});
```

Call `verifyForBackend` only from user-initiated actions (button click).

---

## 3. Verify on your server

Install the verifier for your stack:

| Runtime | Package |
|---------|---------|
| Node 18+ | `@lemma.id/proof-verifier` (npm) |
| Python | Copy [`lemma_proof_verifier.py`](https://lemma.id/sdk/proof-verifier.py) until PyPI publish |

```javascript
// Node
const verifier = createVerifier({ siteId: 'app.example.com', requiredAssurance: 'passkey' });
const result = await verifier.verify(presentation);
```

```python
# Python
ctx = VerificationContext(site_id="app.example.com", required_assurance="passkey")
result = ctx.verify(presentation)
```

On success, bind `result.ppid` to your account model and issue your session.

---

## 4. Session layer (your responsibility)

Lemma does not issue relying-site session cookies. After verification:

1. `findOrCreateUser(ppid)`
2. Set HttpOnly, Secure, SameSite session cookie
3. Guard protected routes with your middleware
4. `POST /logout` clears the cookie

See runnable examples under [`examples/`](../../examples/).

---

## 5. Localhost workflow

| Topic | Behavior |
|-------|----------|
| `siteId` | Page hostname; `localhost` for all local ports |
| Popup | Hosted on lemma.id; works with local relying origin |
| Mismatch | Dev warns if browser/backend hostnames differ |

---

## 6. Recovery policy

- **Passkey login:** best-effort continuity; encourage second device at [lemma.id/link](https://lemma.id/link).
- **isHuman step-up:** same PPID, stronger recovery assurances.

Do not promise email/password-style recovery for passkey-only accounts.

---

## 7. When to register a site / API key

| Need | Registration |
|------|----------------|
| Basic login | None |
| `POST /api/ishuman/site-block` etc. | Register site + domain verification + API key |

Keys are for abuse controls only, not for the login path itself.

---

## 8. isHuman step-up (paid tier)

Same integration; stricter assurance:

```javascript
requiredAssurance: 'ishuman'
```

Use for signup bonuses, payouts, or one-human-per-account policies.

---

## 9. Profile data (you own it)

lemma.id returns **`ppid`** and **`assurance`** — not email, name, or avatar. After first login, collect profile fields in your app and key them to the verified `ppid`. lemma.id proves continuity; your database holds display names, preferences, and entitlements.

---

## 10. Link to an existing password account

When users already have a password account, verify a presentation while they are logged in, then attach the PPID:

1. User signs in with password (existing session).
2. User clicks "Link lemma.id" → `verifyForBackend({ requiredAssurance: 'passkey' })`.
3. Backend verifies presentation; `UPDATE users SET lemma_ppid = ? WHERE id = ?` for the current session user.
4. Future logins can use lemma.id only, or offer both methods.

Never link on a bare client `ppid` without presentation verification.

### Legacy SDK redirect callback (retired)

`/auth/sdk-callback` does **not** verify a presentation or bind a subject. It
returns `lemma_auth=error&reason=callback_unbound`. Use `<lemma-signin>` /
`ProofVerifier.verifyForBackend` and POST the presentation to your backend.

---

## 11. Sign-out semantics

Two independent layers:

| Layer | Who controls | What it does |
|-------|--------------|--------------|
| **Site session** | Your backend | Clear your HttpOnly cookie on `POST /logout`. User is signed out of your app only. |
| **lemma.id site disconnect** | User / lemma.id | Revocation and bloom snapshot updates can invalidate cached site proofs. SDK polling surfaces "sign out everywhere" style disconnect for that site binding. |

Document both for support: logging out of your site does not delete the user's lemma.id.

---

## 12. What lemma.id does not provide

| Expectation | Reality | Alternative |
|-------------|---------|-------------|
| User management dashboard | No — privacy by design | Your DB is the user list; key rows by `ppid` |
| Webhooks on login/revoke | No — hard product rule | Poll bloom snapshot / use SDK `checkStatus()` for revocation |
| Email/name from lemma.id | No | Collect after first login in your UI |
| Site registration for basic login | No | Optional API keys only for abuse APIs |

---

## Do not use (legacy)

- `lemma-wallet.js` + `startRedirectFlow()` redirect login
- Bare client `ppid` without presentation verification
- `X-Lemma-Credential` as the relying-site login protocol

These patterns are superseded by presentation verification.
