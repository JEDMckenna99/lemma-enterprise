# Launch collateral: Show HN — lemma.id proof continuity

Internal launch doc. Not served publicly. Contains a ready-to-post Show HN
submission plus a pre-emptive FAQ written to defuse the objections a technical
audience will raise (recovery, centralization/lock-in, "why not plain WebAuthn",
crypto vibes, closed infra). Sources for every claim: `docs/integration/
CONTINUITY_AND_ABUSE.md`, `SIGN_IN_TRUST_AND_RECOVERY.md`, `QUICK_START_SIMPLE_LOGIN.md`, and the
Apache-2.0 verifier packages.

Golden rules for the thread:
1. **Lead with what it is not** (no blockchain, no token) in the first two lines.
2. **Say the verifier runs offline on your backend** before anyone assumes lemma
   is in the hot path.
3. **Lead with the abuse/continuity job**, not passwordless login.
4. **Be first to raise recovery.** Name the single-device caveat yourself.
5. **Never argue that a real limitation isn't real.** Concede, then show the
   mitigation. HN rewards this and punishes the opposite.

---

## Title options (pick one)

- `Show HN: Site-private person continuity — verify proofs locally, enforce one-human policy, block abusers who rotate accounts`
- `Show HN: A local-first proof layer that gives each site a stable, pairwise-private user handle`
- `Show HN: Stop the same abuser from coming back as a new account — without storing KYC on your site`

Recommended: the first. It front-loads the job developers pay for.

---

## Post body

> **lemma.id** is a local-first proof layer for web apps. Users mint a signed
> presentation with a passkey; your backend verifies it **offline** and gets a
> stable, **site-private** handle (`ppid`) + assurance level. Use it to enforce
> one trial per human, one code per person, post-ban blocks that survive new
> accounts, and auditable action stamps — without storing government ID on your
> servers. There is **no blockchain, no token, and nothing to buy** for basic
> verify — no site registration and no API key.
>
> Keep your existing login if you want. Gate the expensive or abuse-prone step.
>
> What's actually different from rolling your own WebAuthn or using an OAuth
> provider:
>
> - **You verify locally.** The verifier (`@lemma.id/proof-verifier`, Apache-2.0)
>   runs on your backend and checks a signed presentation **offline** — no
>   per-request call to us. It validates against a cached, signed issuer trust list
>   (refreshes ~every 15 min).
> - **Site-private continuity handle.** The `ppid` a user gets on your site is derived
>   from your hostname and can't be correlated with the id they get anywhere else
>   **by relying sites**. We don't track users across sites, and there is no
>   cross-site remap API. (Operator capability is documented honestly in the trust doc.)
> - **Assurance ladder on one handle.** `passkey` = continuity; optional `ishuman` =
>   IDV-backed one human per account on the **same PPID** — for Sybil-sensitive
>   actions, not a separate integration.
> - **Site-block that sticks.** Server-side PPID bans survive browser clears and
>   fresh IDV. Optional action stamps bind mutations for audit/fraud.
> - **No profile dump.** Verify returns `ppid` + assurance only — you own email,
>   names, and sessions.
>
> Honest about the hard parts:
>
> - **Recovery.** We don't collect email or phone at the passkey tier. Passkeys sync
>   (iCloud/Google), users can add a second device, and you hold the `ppid` for
>   site-side recovery. A **single-device, non-synced** passkey that's lost is not
>   guaranteed recoverable — we say so in the docs and in the UI.
> - **If lemma.id is down:** local verification and your sessions keep working, but
>   *new presentation mints* are blocked because the popup needs us online. Pin/vendor
>   the verifier and you're insulated from everything except new proof creation.
> - **Not open sourcing the whole platform (yet).** The verifier and credential
>   format are the parts you need to trust for verification, and those are open.
>
> Quickstart, an offline test harness (mint + verify with no lemma.id and no
> WebAuthn), and framework examples (Flask/Express/FastAPI/Next.js) are linked
> below.
>
> Docs: https://lemma.id/docs/integration/CONTINUITY_AND_ABUSE.md
> Quick start: https://lemma.id/docs/integration/QUICK_START_SIMPLE_LOGIN.md
> Trust/availability: https://lemma.id/docs/integration/SIGN_IN_TRUST_AND_RECOVERY.md
> Verifier source (Apache-2.0): https://github.com/JEDMckenna99/lemma-enterprise/tree/main/packages/proof-verifier-js

---

## Pre-emptive FAQ (paste answers as replies as questions come in)

### "Is this a crypto / blockchain / web3 thing?"

No. There is no chain, no token, no coin, and nothing to buy. lemma.id is a
passkey-protected local credential store on the user's device — not cryptocurrency
infrastructure. Basic presentation verify is free with no registration and no API key.

### "So lemma.id is a single point of failure?"

For *new presentation mints* during an outage, yes — the popup mints the proof. For
everything else, no: verification runs on your backend offline (no per-request call
to us), and you enforce on `ppid` in your DB. Pin/vendor the Apache-2.0 verifier.
Full failure-mode table:
https://lemma.id/docs/integration/SIGN_IN_TRUST_AND_RECOVERY.md#availability-and-failure-modes-honest-table

### "What happens if lemma.id gets acquired / shuts down / changes terms?"

You keep every `ppid` and all site-scoped state (roles, bans, profiles) because
they live in your database. New proof mints would stop; migrate via a dual-run
window to any other method with no involvement from us.

### "This is just WebAuthn / SSH keys with extra steps. Why not do it myself?"

Raw WebAuthn is an authenticator protocol; you'd still build continuity, pairwise
IDs, optional IDV step-up, and site-block. lemma packages verify → `{ ppid,
assurance }` + optional stamps and enforcement APIs. If you only need a login
button for one app and don't care about abuse continuity, plain WebAuthn may be enough.

### "Passkeys mean my users will lose their accounts."

Passkeys sync in the common case. The wrinkle is we don't hold email for reset at
the passkey tier. Mitigations: sync, second device, site-side recovery keyed to
`ppid`, and isHuman for identity-backed recovery (same PPID).

### "Do you see my users / can you track them across sites?"

We don't receive your profile data (verify returns `ppid` + assurance only), and
PPIDs are pairwise per hostname so **relying sites** cannot correlate across sites.
Honest operator caveat documented in trust materials.

### "How do I know the privacy claims are true if it's not fully open source?"

The parts you rely on to verify are open (Apache-2.0): Node and Python verifiers
and the credential format. Offline test harness included.

### "What does it cost?"

Basic verify (passkey continuity) is free — no registration, no API key. isHuman
(one-verified-human-per-account, IDV-backed) is the paid step-up on the same `ppid`,
opt-in per action. Site-block API keys are for enforcement.

---

## Do NOT say / avoid in-thread

- Don't claim "zero downtime dependency" — the popup needs us online for new
  presentation mints. Say exactly that instead.
- Don't argue recovery "isn't a problem." Concede the single-device case.
- Don't lead with "passwordless login" as the product — lead with continuity under abuse.
