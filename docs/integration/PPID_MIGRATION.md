# PPID migration (document refresh)

When a user re-proves with a **new government document number**, Lemma may issue a
**site-scoped, signed migration object** so relying sites can **opt in** to
updating an existing account's PPID. This is **not automatic** and **never**
links users across sites.

## When migration is issued

All must be true:

1. Wallet was **already verified** and bound to person A before IDV started.
2. User completed **fresh IDV** (liveness + document check) yielding person B.
3. Lemma recorded a **wallet-bound person merge** (A → B).
4. User derives a site credential; `POST /api/ishuman/derive-site-proof` may
   include `ppid_migration` in the response.

Routine credential TTL renewal (**same document**) does **not** produce migration.

## Presentation shape

`verifyForBackend()` may include:

```json
{
  "credential": { "...": "..." },
  "session_assertion": { "...": "..." },
  "session_signature": "...",
  "ppid_migration": {
    "type": "lemma.ppid_migration.v1",
    "mergeId": "merge_...",
    "siteId": "app.example.com",
    "legacyPpid": "did:lemma:ppid_...",
    "currentPpid": "did:lemma:ppid_...",
    "walletId": "wallet_...",
    "nonce": "...",
    "issuedAt": 1710000000,
    "expiresAt": 1710003600,
    "issuerDid": "did:lemma:...",
    "issuerPubkey": "...",
    "signature": "..."
  }
}
```

## Site integration (recommended, fail-closed)

### Path A — own auth + Lemma confirm (simplest)

Most sites already have email/OAuth login. When a returning user verifies with a
**new** PPID after document refresh:

1. User logs in with **your** auth (unchanged).
2. Browser runs `verifyForBackend()` — you verify the **new** PPID locally.
3. Your backend sees: session user has `legacy_ppid`, presentation has `current_ppid`.
4. Call Lemma (site API key):

```http
POST /api/ishuman/confirm-ppid-migration
X-API-Key: your_site_key
Content-Type: application/json

{
  "legacy_ppid": "did:lemma:ppid_...",
  "current_ppid": "did:lemma:ppid_..."
}
```

5. If `{ "success": true, "approved": true }`, update `user.ppid = current_ppid`.

Lemma checks internal wallet-bound merge records. An attacker with only a leaked
legacy PPID cannot get `approved: true` without the victim's wallet completing
fresh IDV.

### Path B — signed migration in presentation (offline-friendly)

Same guards, but approval is embedded in `presentation.ppid_migration` and
verified locally (no confirm API call). Use when you prefer zero server calls
to Lemma after the initial verify.

```python
result = ctx.verify(presentation)
if not result.ok:
    deny()

migration = presentation.get("ppid_migration")
if migration:
    ok, reason = verify_ppid_migration(
        migration,
        site_id=YOUR_SITE,
        current_ppid=result.ppid,
        trusted_pubkey_hex=migration["issuerPubkey"],  # or trust-list lookup
    )
    if not ok:
        deny()

    user = db.find_by_ppid(migration["legacyPpid"])
    if user and session.user_id == user.id:  # require logged-in session
        user.ppid = migration["currentPpid"]
    else:
        # Do not create accounts from legacy PPID alone
        treat_as_new_signup()
```

**Do not:**

- Accept migration without verifying Lemma's Ed25519 signature.
- Update accounts using only `legacyPpid` (leaked DB → takeover).
- Auto-link across sites — migration is scoped to `siteId`.

## Python helper

`lemma_ishuman_verify.verify_ppid_migration()` validates type, site, expiry,
signature, and that `currentPpid` matches the verified credential subject.

## Privacy

Lemma stores merge metadata internally (wallet id, person ids, document root
hashes). Sites receive **only** the pairwise legacy/current PPIDs **for their
site**, signed and time-limited. Other sites never see the linkage.
