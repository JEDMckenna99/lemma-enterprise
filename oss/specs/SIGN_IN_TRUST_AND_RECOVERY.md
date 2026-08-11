# lemma.id: trust, recovery, and availability

This page answers the three questions developers ask before putting a **proof
dependency** on their critical path: **What happens if a user loses their
device? What happens if lemma.id goes down? And is this a crypto/blockchain
thing?** Short answers first, detail below.

- **Recovery:** passkey vault sync (iCloud/Google) may make the **same WebAuthn
  credential** available on another device, but it does **not** sync lemma.id
  contents (identity seed, site proofs, isHuman material). Cross-device
  continuity for the **same person** requires [lemma.id/link](https://lemma.id/link)
  (or isHuman / site-side recovery keyed to `ppid`). Your site always owns the
  account row keyed by `ppid` so you can add your own recovery. Guaranteed
  account recovery for a **single-device, passkey-only** lemma.id is not
  promised: see the honest matrix below.
- **Availability:** the verifier runs **on your backend, offline**: there is no
  per-request call to lemma.id, so verification and your own sessions do not
  depend on lemma being up. A lemma.id outage blocks **new presentation mints**
  (the popup), not your active sessions or already-verified policy.
- **No blockchain:** there is no token, no coin, and no chain. See
  ["What this is not"](#what-this-is-not).

---

## Where lemma.id sits in your proof path (and where it doesn't)

```
Browser                         Your backend                    lemma.id
-------                         ------------                    --------
verifyForBackend / popup  ----> POST /api/gate
  (mints signed                   verify(presentation)  ← runs LOCALLY, offline
   presentation) ← talks           enforce on ppid + assurance
   to lemma to derive             optional: set your OWN session cookie
   the site proof
```

Two independent facts follow from this shape:

1. **You verify locally.** `@lemma.id/proof-verifier` (Node) and
   `lemma_proof_verifier.py` (Python) verify the signed presentation on your
   server with **no network call to lemma.id per login**. They validate the
   Ed25519 signature against a cached, signed **issuer trust list** that
   refreshes on a slow interval (default ~15 minutes), not per request.
2. **You own the session.** After verification you issue your **own** HttpOnly
   cookie. lemma.id is not in your session-validation path, cannot see your
   logged-in users, and cannot revoke your sessions.

The one thing that does require lemma.id online is **minting a fresh
presentation** in the popup (`derive-site-proof`). That matters only at the
moment a user signs in, and its failure mode is spelled out below.

---

## Availability and failure modes (honest table)

| Scenario | Active sessions (already logged in) | New sign-in / re-auth | Your data |
|----------|-------------------------------------|-----------------------|-----------|
| lemma.id API/popup **down** | ✅ Unaffected: validated by your own cookie / prior verify | ❌ Blocked while down (popup can't mint a presentation) | ✅ Your `ppid`→account rows are in **your** DB |
| lemma.id **verifier/SDK CDN down** | ✅ Unaffected | ✅ Pin/self-host the verifier (npm/PyPI/vendored) and it keeps working | ✅ Unaffected |
| Issuer key rotation | ✅ Unaffected | ✅ Trust list carries `previous_keys`; verifiers refresh automatically, no site action | ✅ Unaffected |
| lemma.id **shuts down permanently** | ✅ Sessions persist until expiry | ⚠️ New logins stop; migrate via a dual-run window to another method | ✅ You keep every `ppid` and all site-scoped state |

Practical hardening you control:

- **Pin and vendor the verifier.** It's Apache-2.0. Install
  `@lemma.id/proof-verifier` from npm (or copy `lemma_proof_verifier.py`) and
  commit it, rather than hot-loading from the CDN, so a CDN blip can't affect
  logins.
- **Keep your own account table.** Match returning users on `ppid` from your
  database; never depend on lemma.id to "look up" a user.
- **Have a migration story.** Because you hold the `ppid`→account mapping and
  issue your own sessions, you can add or swap to any other auth method during a
  dual-run window without lemma's involvement. See the account-linking recipe in
  [SIMPLE_INTEGRATION_GUIDE.md](SIMPLE_INTEGRATION_GUIDE.md).

---

## Recovery: the honest matrix

lemma.id does **not** collect email, phone, or any recovery contact for the
passkey tier: which is a privacy feature and a recovery constraint. Be honest
with your users about which row they're in.

| Situation | Recovery path | Guarantee |
|-----------|---------------|-----------|
| Passkey **synced** (iCloud Keychain / Google Password Manager / synced manager) | Synced credential unlocks on the new device; **lemma.id data must still be transferred** via `/link` (or isHuman recovery) | **Partial:** passkey only; same person requires explicit transfer |
| **Second device added** via [lemma.id/link](https://lemma.id/link) | Sign in / re-link from the other device | Strong: recommended for everyone |
| **Single device, non-synced** passkey, device lost | Site-side recovery (below) or start over | **Not guaranteed**: state this to users |
| Needs guaranteed, identity-backed recovery | Step up to **isHuman** (IDV-backed, same `ppid`) | Strong: paid tier |

### What the SDK/flow already does

- **Second-device nudge on first sign-in.** After a lemma.id is created, the popup
  shows a one-tap "add a second device" screen linking to `/link`. Encourage
  users to take it; a two-device user is a recoverable user.
- **Passkey sync is not lemma.id sync.** Vault sync moves the unlock key only.
  The manager and popup block silent identity forks on empty browsers and route
  users to `/link` when a synced passkey exists without local lemma.id data.

### What you (the site) can add

Because the account row is yours, you can offer recovery **without**
reintroducing PII to lemma:

- **Require a second device** before treating an account as durable for
  high-value use.
- **Site-side recovery** on your own terms: e.g. a support-verified re-link, a
  user-held recovery code you issue, or linking a second login method: all keyed
  to the `ppid` you already store.
- **Offer isHuman** for users who want identity-backed recovery; it's the same
  `ppid`, so nothing about their account changes.

> Rule of thumb: treat a **single-device, non-synced passkey** the way you'd
> treat a user who set a password and refused to give a recovery email: usable,
> but tell them plainly to add a second device.

---

## What this is not

Sign in with lemma.id is deliberately boring infrastructure. To clear the most
common misreads:

- **No blockchain, no token, no coin, no ICO.** Nothing is written to a chain.
- **No cryptocurrency and nothing to buy for basic login.** Passkey login is
  free: no site registration and no API key.
- **No biometric database.** The passkey tier uses standard WebAuthn passkeys;
  the biometric (if any) never leaves the user's device and lemma.id never
  receives it. (isHuman IDV is a separate, opt-in, paid step-up.)
- **No profile data from lemma.** Sign-in returns `ppid` + `assurance` only  - 
  no email, name, or avatar. You own the profile; lemma owns the proof.
- **No cross-site tracking by relying sites.** PPIDs are **pairwise**: the id a
  user gets on your site is derived from your hostname and cannot be correlated
  with the id they get anywhere else **by you or by other sites**. lemma.id does
  not track users across sites, and there is no cross-site remap API. See
  [Operator capability](#operator-capability-honest) below for what the operator
  could technically do.
- **No device attestation gate on your users.** Your site only ever sees a
  signed presentation and a `ppid`; you never allow/deny users by which passkey
  provider or authenticator they chose.

---

## Operator capability (honest)

This section names what lemma.id **could** do technically, separate from what
we **do** by policy and what **relying sites** can do.

| Actor | Can correlate a user across sites? |
|-------|-------------------------------------|
| **Your site + other relying sites** | No: PPIDs are pairwise; you never receive a global user id |
| **lemma.id operator (today)** | Could derive site PPIDs from server-held person roots at issuance; we don't, and there is no cross-site remap API |
| **lemma.id operator (roadmap)** | Client-side-only derivation from sealed roots; issuance transparency log so forged credentials are detectable |

**What we observe at issuance:** hostname, wallet id, and the target site's
`ppid`: enough to bind a proof to your site, not enough for relying sites to
link accounts. We do not receive your profile data, and we do not sell or share
cross-site user lists.

**What you should tell users:** their account id on your site cannot be linked
to their account id on another site by you or by other sites. That property is
cryptographic. Operator non-linkage is a policy commitment today, with
architectural hardening on the roadmap (see
[ISSUER_KEY_CUSTODY.md](../security/ISSUER_KEY_CUSTODY.md) and
[OPERATIONAL_HARDENING.md](../architecture/OPERATIONAL_HARDENING.md)).

---

## Geographic availability (US / Canada for isHuman today)

Passkey lemma.id works anywhere passkeys work. **isHuman** (document + liveness)
currently accepts a **US or Canadian driver’s license or ID card** only — pinned
in the IDV provider dashboard and enforced server-side
(`LEMMA_ISHUMAN_ALLOWED_COUNTRIES`, default `US,CA`). Relying sites still receive
only `ppid` + assurance; country and document details are not part of the
presentation. Do not advertise “lemma.id only works in the US and Canada.”

---

## Verify these claims yourself

- **Verifier source (Apache-2.0):**
  [`packages/proof-verifier-js`](https://github.com/JEDMckenna99/lemma-enterprise/tree/main/packages/proof-verifier-js)
  and
  [`packages/proof-verifier-py`](https://github.com/JEDMckenna99/lemma-enterprise/tree/main/packages/proof-verifier-py).
- **Offline test helpers** (mint and verify presentations with no lemma.id and
  no WebAuthn): see "Testing your integration" in
  [QUICK_START_SIMPLE_LOGIN.md](QUICK_START_SIMPLE_LOGIN.md).
- **Error and outcome reference:** [ERROR_CODES.md](../ERROR_CODES.md),
  [BROWSER_SUPPORT.md](BROWSER_SUPPORT.md).
