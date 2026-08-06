# Launch collateral: Show HN — Sign in with lemma.id

Internal launch doc. Not served publicly. Contains a ready-to-post Show HN
submission plus a pre-emptive FAQ written to defuse the objections a technical
audience will raise (recovery, centralization/lock-in, "why not plain WebAuthn",
crypto vibes, closed infra). Sources for every claim: `docs/integration/
SIGN_IN_TRUST_AND_RECOVERY.md`, `QUICK_START_SIMPLE_LOGIN.md`, and the
Apache-2.0 verifier packages.

Golden rules for the thread:
1. **Lead with what it is not** (no blockchain, no token) in the first two lines.
2. **Say the verifier runs offline on your backend** before anyone assumes lemma
   is in the hot path.
3. **Be first to raise recovery.** Name the single-device caveat yourself.
4. **Never argue that a real limitation isn't real.** Concede, then show the
   mitigation. HN rewards this and punishes the opposite.

---

## Title options (pick one)

- `Show HN: Sign in with lemma.id – passwordless login, no email, no passwords, no cross-site tracking by sites`
- `Show HN: Passwordless login where the site never sees an email and relying sites can't correlate users across sites`
- `Show HN: A passkey login that gives each site a pairwise-private, stable user ID`

Recommended: the first. It front-loads the three concrete properties and avoids
buzzwords.

---

## Post body

> **Sign in with lemma.id** is a passwordless login you can drop into a site in
> a few minutes. Users sign in with a passkey; your backend gets a stable,
> **site-private** user id (`ppid`) and you issue your own session. There is **no
> blockchain, no token, and nothing to buy** — passkey login is free, with no
> site registration and no API key.
>
> What's actually different from rolling your own WebAuthn or using an OAuth
> provider:
>
> - **The site never collects email/username/password**, and lemma never sends
>   you profile data — you get `ppid` + assurance level, nothing else. You own
>   the profile; we own the proof.
> - **Per-site, pairwise-private IDs.** The id a user gets on your site is derived
>   from your hostname and can't be correlated with the id they get anywhere else
>   **by relying sites** — you never receive a global user id. We don't track
>   users across sites, and there is no cross-site remap API. (Operator capability
>   is documented honestly in the trust/recovery doc linked below.)
> - **You verify locally.** The verifier (`@lemma.id/proof-verifier`, Apache-2.0)
>   runs on your backend and checks a signed presentation **offline** — no
>   per-login call to us. It validates against a cached, signed issuer trust list
>   (refreshes ~every 15 min), so your logins and sessions don't depend on us
>   being up.
> - **You own the session.** After verification you set your own HttpOnly cookie.
>   We're not in your session path and can't revoke your users.
>
> Honest about the hard parts:
>
> - **Recovery.** We don't collect email or phone, so we can't email you a reset
>   link. Passkeys sync across a user's devices (iCloud/Google), users can add a
>   second device, and because you hold the `ppid` you can add your own recovery.
>   A **single-device, non-synced** passkey that's lost is not guaranteed
>   recoverable — we say so in the docs and in the UI.
> - **If lemma.id is down:** active sessions are unaffected (your cookie) and
>   local verification keeps working, but *new* sign-ins are blocked because the
>   popup mints the presentation. Pin/vendor the verifier and keep your own
>   account table and you're insulated from everything except new lemma.id
>   creation.
> - **Not open sourcing the whole platform (yet).** The verifier and the credential
>   format are the parts you need to trust for verification, and those are open.
>
> Quickstart, an offline test harness (mint + verify with no lemma.id and no
> WebAuthn), and framework examples (Flask/Express/FastAPI/Next.js) are linked
> below. Happy to answer the "but what if…" questions — recovery and
> "who-can-lock-me-out" especially.
>
> Docs: https://lemma.id/docs/integration/QUICK_START_SIMPLE_LOGIN.md
> Trust/recovery/failure modes: https://lemma.id/docs/integration/SIGN_IN_TRUST_AND_RECOVERY.md
> Verifier source (Apache-2.0): https://github.com/JEDMckenna99/lemma-enterprise/tree/main/packages/proof-verifier-js

---

## Pre-emptive FAQ (paste answers as replies as questions come in)

### "Is this a crypto / blockchain / web3 thing?"

No. There is no chain, no token, no coin, and nothing to buy. lemma.id is a
passkey-protected local identity store on the user's device — not cryptocurrency
infrastructure. Basic login is free with no registration and no API key.

### "So lemma.id is a single point of failure in my login path?"

For *new* sign-ins during an outage, yes — the popup mints the presentation. For
everything else, no: verification runs on your backend offline (no per-login call
to us), your sessions are your own HttpOnly cookies, and you store the
`ppid`→account mapping in your DB. Pin/vendor the Apache-2.0 verifier and a CDN
or API blip can't touch your verification path or your active users. Full
failure-mode table:
https://lemma.id/docs/integration/SIGN_IN_TRUST_AND_RECOVERY.md#availability-and-failure-modes-honest-table

### "What happens if lemma.id gets acquired / shuts down / changes terms?"

You keep every `ppid` and all site-scoped state (roles, bans, profiles) because
they live in your database, and existing sessions persist. New logins would stop,
and because you own the account rows and issue your own sessions you can migrate
to any other auth method during a dual-run window with no involvement from us.

### "This is just WebAuthn / SSH keys with extra steps. Why not do it myself?"

Raw WebAuthn is a login primitive; you'd still build the account system,
cross-device continuity, and — critically — you'd store each user's credential
public key and get a per-site id you have to manage. lemma gives you a **stable, site-private, pairwise-private** id out of the box,
no credential storage on your side, and an identity the user can reuse across
sites *without* those sites being able to correlate them. If you only need a login button for one app and
don't care about pairwise privacy, plain WebAuthn is a perfectly good choice —
we say that in the docs.

### "Passkeys mean my users will lose their accounts."

Passkeys are a stronger primary factor; they don't by themselves change recovery.
The wrinkle specific to us is we don't hold an email to fall back on. Mitigations:
passkey sync (the common case), one-tap second-device add on first sign-in, and
site-side recovery you control against the `ppid` you already store. For
guaranteed, identity-backed recovery there's the isHuman step-up (same `ppid`).
We flag the single-device caveat in the UI rather than hiding it.

### "Can you (or Apple/Google) blacklist my passkey provider, like the attestation naughty-list?"

Your site never sees or gates on which authenticator/provider a user chose — you
receive a signed presentation and a `ppid`, full stop. There's no attestation
allow/deny list applied to your users.

### "Do you see my users / can you track them across sites?"

We don't receive your profile data (login returns `ppid` + assurance only), and
PPIDs are pairwise: derived from your hostname so **relying sites** cannot
correlate the id the same person gets on your site with the id they get
anywhere else. We don't track users across sites, and there is deliberately no
"remap my users across domains" API — such an endpoint would enable exactly the
cross-site correlation the design exists to prevent.

Honest operator caveat: at issuance we hold person-root material server-side, so
lemma.id *could* derive site PPIDs. We don't, and the trust doc describes the
roadmap for making that an architectural guarantee, not just a policy. The
privacy guarantee your users care about is against **you and other sites**, and
that one is cryptographic.

### "How do I know the privacy claims are true if it's not fully open source?"

The parts you rely on to verify are open (Apache-2.0): the Node and Python
verifiers and the credential format. You can mint and verify presentations
entirely offline with the test harness — no lemma.id, no WebAuthn — and confirm
what's in a presentation yourself. Verifier source:
https://github.com/JEDMckenna99/lemma-enterprise/tree/main/packages/proof-verifier-js

### "What does it cost?"

Passkey login is free — no registration, no API key. isHuman (one-verified-human
-per-account, IDV-backed) is the paid step-up on the same `ppid`, opt-in per
action.

---

## Do NOT say / avoid in-thread

- Don't claim "zero downtime dependency" — the popup needs us online for new
  sign-ins. Say exactly that instead.
- Don't argue recovery "isn't a problem." Concede the single-device case and
  point to the mitigations.
- Don't lean on "proof of personhood" framing for the sign-in product — that's
  isHuman, a separate opt-in tier, and it drags in the Worldcoin fight you don't
  need for a login button.
