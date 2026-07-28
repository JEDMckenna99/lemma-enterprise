# Quick start: Sign in with lemma.id (passkey login)

Free passwordless login for your site. Users create or unlock a passkey-backed lemma.id wallet in a Lemma-hosted popup; your backend verifies a signed **presentation** and stores the site-private **`ppid`** as the account key. You then issue **your own** session cookie.

Canonical contract: [ISHUMAN Agent Integration Guide](ISHUMAN_AGENT_INTEGRATION.md)

---

## What you build

| Step | Where | Action |
|------|-------|--------|
| 1 | Browser | Drop in `<lemma-signin>` **or** call `verifyForBackend({ requiredAssurance: 'passkey' })` |
| 2 | Your API | Verify the presentation with `@lemma.id/proof-verifier` or `lemma_proof_verifier.py` |
| 3 | Your API | Find/create user by `result.ppid`, set HttpOnly session cookie |
| 4 | Your API | Protect routes with your session guard; `/logout` clears the cookie |

No site registration, no API key, and no IDV required for basic login. Require `ishuman` assurance when you need Sybil-resistant step-up on the same PPID.

---

## Step 1: Browser sign-in (recommended — drop-in button)

```html
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
<script src="https://lemma.id/sdk/lemma-signin.js"></script>

<lemma-signin site-id="app.example.com"></lemma-signin>

<script>
  document.querySelector('lemma-signin').addEventListener('lemma-signin-success', async (e) => {
    const resp = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ presentation: e.detail.presentation }),
    });
    if (resp.ok) window.location.href = '/';
  });

  document.querySelector('lemma-signin').addEventListener('lemma-signin-error', (e) => {
    console.error(e.detail.reason);
  });
</script>
```

Attributes: `site-id` (required), `required-assurance` (default `passkey`), `auto-provision` (default `true`), `label` (button text).

**React:** see [`examples/nextjs_ishuman_signup/components/LemmaSignIn.tsx`](../../examples/nextjs_ishuman_signup/components/LemmaSignIn.tsx).

### Advanced: SDK directly

```html
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
<script>
  const SITE_ID = 'app.example.com'; // canonical hostname — not site_... ids

  async function signIn() {
    const verifier = new ProofVerifier({ siteId: SITE_ID });
    const { ok, presentation, reason } = await verifier.verifyForBackend({
      autoProvision: true,
      requiredAssurance: 'passkey',
    });
    if (!ok) throw new Error(reason || 'not_verified');

    const resp = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ presentation }),
    });
    if (!resp.ok) throw new Error('login_failed');
    window.location.href = '/';
  }
</script>
<button type="button" onclick="signIn()">Sign in with lemma.id</button>
```

---

## Step 2: Backend verify + session

**Node.js** (`@lemma.id/proof-verifier`):

```javascript
import { createVerifier } from '@lemma.id/proof-verifier';

const verifier = createVerifier({
  siteId: 'app.example.com',
  requiredAssurance: 'passkey',
});

app.post('/api/login', async (req, res) => {
  const presentation = req.body?.presentation;
  if (!presentation) return res.status(400).json({ error: 'presentation_missing' });

  const result = await verifier.verify(presentation);
  if (!result.ok) return res.status(401).json({ error: result.reason });

  const user = await findOrCreateUserByPpid(result.ppid);
  res.cookie('session', signSession(user.id), { httpOnly: true, secure: true, sameSite: 'lax' });
  return res.json({ success: true, ppid: result.ppid });
});
```

**Python** (drop-in verifier until PyPI publish):

```python
# pip install from repo path, or:
# curl -O https://lemma.id/sdk/proof-verifier.py
from lemma_proof_verifier import VerificationContext

ctx = VerificationContext(site_id="app.example.com", required_assurance="passkey")

@app.post("/api/login")
def login():
    presentation = request.get_json(silent=True) or {}
    presentation = presentation.get("presentation")
    if not presentation:
        return jsonify({"error": "presentation_missing"}), 400
    result = ctx.verify(presentation)
    if not result.ok:
        return jsonify({"error": result.reason}), 401
    user = find_or_create_by_ppid(result.ppid)
    resp = jsonify({"success": True, "ppid": result.ppid})
    resp.set_cookie("session", sign_session(user.id), httponly=True, secure=True, samesite="Lax")
    return resp
```

Fail closed when `ok` is false. Never trust a bare client `ppid` on signup/login.

---

## Localhost development

- `siteId` defaults to the page hostname. All `localhost` ports collapse to binding `localhost`.
- Hostname mismatch between browser SDK and backend verifier is **warn-only** in dev; align both to the same canonical hostname in production.
- Supported pattern: production lemma.id popup + local relying site (e.g. `http://localhost:5050` with `siteId: 'localhost'`).

---

## Recovery expectations

| Tier | Recovery |
|------|----------|
| `passkey` (free login) | Durable across device upgrades when passkeys sync (iCloud/Google). Adding a second device via [lemma.id/link](https://lemma.id/link) improves continuity. Guaranteed account recovery is not promised for passkey-only wallets. |
| `ishuman` (step-up) | Same PPID; IDV-backed recovery on the paid tier. |

Document this honestly to users when you ship passkey-only login.

---

## Step-up to isHuman

Use the same SDK and PPID; change policy only:

```javascript
await verifier.verifyForBackend({
  autoProvision: true,
  requiredAssurance: 'ishuman', // Sybil-resistant
});
```

Backend: `requiredAssurance: 'ishuman'`.

---

## What login returns (profile data)

Sign-in returns **`ppid`** + **`assurance`** only — no email, name, or avatar from lemma.id. That is intentional: lemma owns the proof; you own the profile.

**First-login pattern:** after verifying the presentation, show a one-time screen to collect a display name (or avatar URL) and store it in **your** database keyed by `ppid`:

```javascript
// After successful /api/login
if (user.is_new) {
  redirect('/welcome?ask=display_name');
}
```

Returning users match on `ppid` alone. Do not expect lemma.id to supply profile fields unless you build wallet-side share (future work).

---

## Testing your integration

Run login-handler unit tests **without** lemma.id or WebAuthn:

**Python** (copy `lemma_proof_verifier_testing.py` from the repo or package):

```python
from lemma_proof_verifier_testing import (
    create_offline_test_context,
    mint_test_issuer,
    mint_test_presentation,
)

issuer = mint_test_issuer()
presentation = mint_test_presentation(
    site_id="localhost",
    ppid="did:lemma:ppid_test_user",
    assurance="passkey",
    issuer=issuer,
)
ctx = create_offline_test_context(
    site_id="localhost",
    issuer_did=issuer["did"],
    issuer_pubkey_hex=issuer["pubkey_hex"],
    required_assurance="passkey",
)
assert ctx.verify(presentation).ok
```

**Node** (`@lemma.id/proof-verifier/testing`):

```javascript
import {
  mintTestIssuer,
  mintTestPresentation,
  verifyTestPresentationOffline,
} from '@lemma.id/proof-verifier/testing';

const issuer = await mintTestIssuer();
const presentation = await mintTestPresentation({
  siteId: 'localhost',
  ppid: 'did:lemma:ppid_test_user',
  assurance: 'passkey',
  issuer,
});
const result = await verifyTestPresentationOffline({
  presentation,
  siteId: 'localhost',
  requiredAssurance: 'passkey',
  trustedIssuerPubkeyHex: issuer.pubkeyHex,
});
assert(result.ok);
```

For server paths that read `TRUSTED_ISSUER_DIDS`, set it to the test issuer DID from `mint_test_issuer()`. See [BROWSER_SUPPORT.md](BROWSER_SUPPORT.md) for browser matrix and SDK error codes.

---

## Examples in this repo

- [`examples/flask_ishuman_signup/`](../../examples/flask_ishuman_signup/) — Flask login + session cookie
- [`examples/express_ishuman_signup/`](../../examples/express_ishuman_signup/) — Express
- [`examples/fastapi_ishuman_signup/`](../../examples/fastapi_ishuman_signup/) — FastAPI
- [`examples/nextjs_ishuman_signup/`](../../examples/nextjs_ishuman_signup/) — Next.js App Router

---

## Optional: abuse API keys

Site API keys are **not** required for login. Register a site and issue keys only when you need server-side block/unblock APIs. See [External API keys](https://lemma.id/developer/external-api-keys).

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Popup shows "passkey sign-in is not available yet" | Platform flags not enabled yet (`LEMMA_ONE_PPID_ASSURANCE_MODEL` + `LEMMA_PASSKEY_ASSURANCE_ENABLED`) |
| `site_id_mismatch` | Same hostname in browser `siteId` and backend verifier |
| `assurance_insufficient` | Request `passkey` for login; use `ishuman` only when policy requires it |
| `derive_site_proof_rate_limited` | Back off; see [ERROR_CODES.md](../ERROR_CODES.md) |
| `passkey_unsupported`, `popup_blocked`, `user_cancelled`, `rate_limited` | SDK stable outcomes — see [BROWSER_SUPPORT.md](BROWSER_SUPPORT.md) |

Full reference: [ERROR_CODES.md](../ERROR_CODES.md)
