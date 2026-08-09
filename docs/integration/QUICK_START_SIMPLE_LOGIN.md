# Quick start: verify a lemma proof

Gate a sensitive action with a locally verified presentation. Your backend gets a
site-private **`ppid`** + **`assurance`** and enforces policy — one trial per
human, one code per person, post-ban blocks, etc. Users mint presentations via
passkey unlock in the lemma.id popup; you verify with `@lemma.id/proof-verifier`
or `lemma_proof_verifier.py`.

**Start here for why:** [Continuity & abuse](CONTINUITY_AND_ABUSE.md)  
**Canonical contract:** [ISHUMAN Agent Integration Guide](ISHUMAN_AGENT_INTEGRATION.md)

---

## What you build

| Step | Where | Action |
|------|-------|--------|
| 1 | Browser | Call `verifyForBackend({ requiredAssurance: 'ishuman' })` **or** drop in `<lemma-signin>` to mint a presentation |
| 2 | Your API | Verify the presentation locally (no per-request call to lemma.id) |
| 3 | Your API | Enforce on `result.ppid` + assurance; optional site-block |
| 4 | Optional | Issue HttpOnly session cookie from the same verified `ppid` |

No site registration or API key required for verify. Register keys only for
server-side block/unblock APIs.

---

## Step 1: Gate an action (SDK — recommended)

```html
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
<script>
  const SITE_ID = 'app.example.com'; // canonical hostname — not site_... ids

  async function claimTrial() {
    const verifier = new ProofVerifier({ siteId: SITE_ID });
    const { ok, presentation, reason } = await verifier.verifyForBackend({
      autoProvision: true,
      requiredAssurance: 'ishuman', // or 'passkey' for continuity-only
    });
    if (!ok) throw new Error(reason || 'not_verified');

    const resp = await fetch('/api/claim-trial', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ presentation }),
    });
    if (!resp.ok) throw new Error('gate_failed');
  }
</script>
<button type="button" onclick="claimTrial()">Claim trial</button>
```

Call `verifyForBackend` only from user-initiated actions (button click).

### Mint a presentation (drop-in button)

Same SDK; use for gated actions or optional login UX:

```html
<script src="https://lemma.id/sdk/proof-verifier.js"></script>
<script src="https://lemma.id/sdk/lemma-signin.js"></script>

<lemma-signin site-id="app.example.com" required-assurance="ishuman"></lemma-signin>

<script>
  document.querySelector('lemma-signin').addEventListener('lemma-signin-success', async (e) => {
    const resp = await fetch('/api/gate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ presentation: e.detail.presentation }),
    });
    if (resp.ok) window.location.href = '/success';
  });

  document.querySelector('lemma-signin').addEventListener('lemma-signin-error', (e) => {
    console.error(e.detail.reason);
  });
</script>
```

Attributes: `site-id` (required), `required-assurance` (default `passkey`), `auto-provision` (default `true`), `label` (button text), `lemma-origin` (optional — override the lemma.id API/popup host for staging or local demos; omit in production).

```html
<!-- Staging demo site pointing at demo.lemma.id -->
<lemma-signin site-id="tickets-demo.lemma.id" lemma-origin="https://demo.lemma.id"></lemma-signin>
```

**React:** see [`examples/nextjs_ishuman_signup/components/LemmaSignIn.tsx`](../../examples/nextjs_ishuman_signup/components/LemmaSignIn.tsx).

---

## Step 2: Backend verify + enforce

**Node.js** (`@lemma.id/proof-verifier`):

```javascript
import { createVerifier } from '@lemma.id/proof-verifier';

const verifier = createVerifier({
  siteId: 'app.example.com',
  requiredAssurance: 'ishuman',
});

app.post('/api/claim-trial', async (req, res) => {
  const presentation = req.body?.presentation;
  if (!presentation) return res.status(400).json({ error: 'presentation_missing' });

  const result = await verifier.verify(presentation);
  if (!result.ok) return res.status(401).json({ error: result.reason });

  // Enforce one trial per ppid (your policy)
  if (await alreadyClaimed(result.ppid)) {
    return res.status(403).json({ error: 'already_claimed' });
  }
  await recordClaim(result.ppid, result.assurance);
  return res.json({ success: true, ppid: result.ppid });
});
```

**Python** (drop-in verifier until PyPI publish):

```python
# pip install from repo path, or:
# curl -O https://lemma.id/sdk/proof-verifier.py
from lemma_proof_verifier import VerificationContext

ctx = VerificationContext(site_id="app.example.com", required_assurance="ishuman")

@app.post("/api/claim-trial")
def claim_trial():
    presentation = request.get_json(silent=True) or {}
    presentation = presentation.get("presentation")
    if not presentation:
        return jsonify({"error": "presentation_missing"}), 400
    result = ctx.verify(presentation)
    if not result.ok:
        return jsonify({"error": result.reason}), 401
    if already_claimed(result.ppid):
        return jsonify({"error": "already_claimed"}), 403
    record_claim(result.ppid, result.assurance)
    return jsonify({"success": True, "ppid": result.ppid})
```

Fail closed when `ok` is false. Never trust a bare client `ppid`.

---

## Optional: session cookie from the same presentation

After verify, you may issue your own login session:

```javascript
const user = await findOrCreateUserByPpid(result.ppid);
res.cookie('session', signSession(user.id), { httpOnly: true, secure: true, sameSite: 'lax' });
```

See [Integration guide — sessions](SIMPLE_INTEGRATION_GUIDE.md#4-session-layer-your-responsibility).

---

## Localhost development

- `siteId` defaults to the page hostname. All `localhost` ports collapse to binding `localhost`.
- Hostname mismatch between browser SDK and backend verifier is **warn-only** in dev; align both to the same canonical hostname in production.
- Supported pattern: production lemma.id popup + local relying site (e.g. `http://localhost:5050` with `siteId: 'localhost'`).
- `localhost` is a **development-only binding**: every localhost app shares the same
  per-user PPID and accepts each other's presentations, so it provides neither
  pairwise privacy nor replay isolation. Never ship a product bound to `localhost`;
  note that `127.0.0.1` is a different binding than `localhost`.

---

## Choosing (and changing) your siteId

Your `siteId` is your account keyspace: PPIDs are derived from it, so pick the
canonical hostname deliberately before launch (apex vs `app.` subdomain; `www.` is
stripped) and keep it stable.

**If you later change domains, every user derives a new PPID on the new hostname.**
There is deliberately no "remap my users" API — such an endpoint would let sites
correlate users across hostnames, which the pairwise design exists to prevent.
Migrate by linking accounts yourself during a dual-run window:

1. Keep the old domain serving during the migration window.
2. User completes a gated action on the old domain (old PPID). Your site issues its own short-lived,
   signed handoff token and redirects to the new domain.
3. The new domain accepts the handoff token **and** runs lemma.id there
   (new PPID). Your backend now holds both PPIDs in one authenticated context and
   links the account rows.
4. Carry over any site-scoped state (bans, roles) during the link, then retire the
   old binding once traffic drains.

No lemma.id involvement is needed: the linkage happens inside the one party entitled
to know both IDs.

---

## Recovery expectations

| Tier | Recovery |
|------|----------|
| `passkey` (continuity) | Durable across device upgrades when passkeys sync (iCloud/Google). Adding a second device via [lemma.id/link](https://lemma.id/link) improves continuity. Guaranteed account recovery is not promised for passkey-only lemma.id instances. |
| `ishuman` (step-up) | Same PPID; IDV-backed recovery on the paid tier. |

Document this honestly to users. For the full recovery matrix, lemma.id outage/failure behavior, and a "what this is not"
(no blockchain, no token, no tracking) rundown, see
[Trust, recovery & availability](SIGN_IN_TRUST_AND_RECOVERY.md).

---

## Assurance policy

Use the same SDK and PPID; change policy only:

```javascript
await verifier.verifyForBackend({
  autoProvision: true,
  requiredAssurance: 'ishuman', // Sybil-resistant
});
```

Backend: match `requiredAssurance` in your verifier config.

---

## What verify returns (profile data)

Verification returns **`ppid`** + **`assurance`** only — no email, name, or avatar from lemma.id. lemma owns the proof; you own the profile.

If you also issue sessions, collect display names in **your** database keyed by `ppid` after first successful verify.

---

## Testing your integration

Run handler unit tests **without** lemma.id or WebAuthn:

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
    assurance="ishuman",
    issuer=issuer,
)
ctx = create_offline_test_context(
    site_id="localhost",
    issuer_did=issuer["did"],
    issuer_pubkey_hex=issuer["pubkey_hex"],
    required_assurance="ishuman",
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
  assurance: 'ishuman',
  issuer,
});
const result = await verifyTestPresentationOffline({
  presentation,
  siteId: 'localhost',
  requiredAssurance: 'ishuman',
  trustedIssuerPubkeyHex: issuer.pubkeyHex,
});
assert(result.ok);
```

For server paths that read `TRUSTED_ISSUER_DIDS`, set it to the test issuer DID from `mint_test_issuer()`. See [BROWSER_SUPPORT.md](BROWSER_SUPPORT.md) for browser matrix and SDK error codes.

---

## Examples in this repo

- [`examples/flask_ishuman_signup/`](../../examples/flask_ishuman_signup/) — Flask verify + optional session
- [`examples/express_ishuman_signup/`](../../examples/express_ishuman_signup/) — Express
- [`examples/fastapi_ishuman_signup/`](../../examples/fastapi_ishuman_signup/) — FastAPI
- [`examples/nextjs_ishuman_signup/`](../../examples/nextjs_ishuman_signup/) — Next.js App Router

---

## Abuse API keys (enforcement SKU)

Site API keys are **not** required for local verify. Register a site and issue keys when you need server-side block/unblock APIs. See [External API keys](https://lemma.id/developer/external-api-keys) and [Continuity & abuse](CONTINUITY_AND_ABUSE.md).

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Popup shows "passkey sign-in is not available yet" | Platform flags not enabled yet (`LEMMA_ONE_PPID_ASSURANCE_MODEL` + `LEMMA_PASSKEY_ASSURANCE_ENABLED`) |
| `site_id_mismatch` | Same hostname in browser `siteId` and backend verifier |
| `assurance_insufficient` | Match client and backend `requiredAssurance` |
| `derive_site_proof_rate_limited` | Back off; see [ERROR_CODES.md](../ERROR_CODES.md) |
| `passkey_unsupported`, `popup_blocked`, `user_cancelled`, `rate_limited` | SDK stable outcomes — see [BROWSER_SUPPORT.md](BROWSER_SUPPORT.md) |

Full reference: [ERROR_CODES.md](../ERROR_CODES.md)
