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

## How to submit

- **Title:** `Show HN: Local-first person continuity — site-private handles, verify offline`
- **URL:** `https://lemma.id/docs` (not `/` — root can send returning browsers to `/app`)
- **When:** weekday 8–10am ET, only if you can sit the thread 4–6 hours
- **Immediately after submit:** paste the first comment below

Do not ask anyone to upvote.

---

## Title options (pick one)

- `Show HN: Local-first person continuity — site-private handles, verify offline`
- `Show HN: Stop the same abuser from coming back as a new account — without storing KYC on your site`
- `Show HN: A local-first proof layer that gives each site a stable, pairwise-private user handle`

Recommended: the first. Short enough for `/newest`. The job is in the first comment.

---

## Post body

Use this if HN asks for text. The URL is the docs; the first comment carries the
substance.

> **lemma.id** is a local-first proof layer for web apps. Users mint a signed
> presentation with a passkey; your backend verifies it **offline** and gets a
> stable, **site-private** handle (`ppid`) + assurance level. Use it to enforce
> one trial per IDV-backed person (same verified document), one code per person,
> post-ban blocks that survive new accounts, and auditable action stamps — without
> storing government ID on your servers. There is **no blockchain, no token, and
> nothing to buy** for basic verify — no site registration and no API key.
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
>   IDV-backed person assurance (document uniqueness) on the **same PPID** — for
>   Sybil-sensitive actions, not a separate integration. Not biometric unique-human.
> - **Site-block that sticks.** Server-side PPID bans survive browser clears and
>   fresh IDV. Optional action stamps bind mutations for audit/fraud.
> - **No profile dump.** Verify returns `ppid` + assurance only — you own email,
>   names, and sessions.
>
> Honest about the hard parts:
>
> - **Uniqueness.** isHuman is per verified government document, not absolute
>   unique-human. Distinct documents with different numbers can yield distinct
>   persons on fresh enrollments; same document rematches.
> - **Recovery.** We don't collect email or phone at the passkey tier. Passkey vault
>   sync (iCloud/Google) moves the unlock key only — not lemma.id contents. Users
>   add a second device via `/link` for same-person continuity; you hold the `ppid`
>   for site-side recovery. A **single-device, passkey-only** lemma.id that's lost
>   without `/link` or isHuman is not guaranteed recoverable — we say so in the docs
>   and in the UI.
> - **If lemma.id is down:** local verification and your sessions keep working, but
>   *new presentation mints* are blocked because the popup needs us online. Pin/vendor
>   the verifier and you're insulated from everything except new proof creation.
> - **Not open sourcing the whole platform (yet).** The verifier and credential
>   format are the parts you need to trust for verification, and those are open.
>
> Try: https://lemma.id/demo
> Docs: https://lemma.id/docs/integration/CONTINUITY_AND_ABUSE.md
> Quick start: https://lemma.id/docs/integration/QUICK_START_SIMPLE_LOGIN.md
> Trust/availability: https://lemma.id/docs/integration/SIGN_IN_TRUST_AND_RECOVERY.md
> Verifier source (Apache-2.0): https://github.com/JEDMckenna99/lemma-proof

---

## First comment (paste immediately)

> No blockchain, no token, nothing to buy for basic verify.
>
> What you get: a signed presentation the user mints with a passkey. Your backend
> verifies it **offline** with `@lemma.id/proof-verifier` (Apache-2.0) and gets a
> site-private `ppid` + assurance. No per-request call to us. Keep your existing
> login; gate trials, tickets, payouts, and bans.
>
> `passkey` = continuity. `ishuman` = IDV-backed person on the **same** PPID.
> That is per verified government document, not unique-human. Same document
> rematches; a different document on a fresh lemma.id can be a different person.
>
> Recovery: we don't collect email at the passkey tier. iCloud/Google sync moves
> the unlock key, not lemma.id contents. Add a second device at /link, or recover
> via isHuman / your own `ppid` row. A single-device passkey-only lemma.id that
> is lost is not guaranteed recoverable.
>
> isHuman IDV currently accepts a US or Canadian driver’s license or ID card.
> Passkey continuity works anywhere passkeys work.
>
> Demo (no ID scan): https://lemma.id/demo
> Verifier: https://github.com/JEDMckenna99/lemma-proof

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

Passkey vault sync may restore the WebAuthn credential on a new device, but it
does not sync lemma.id contents — empty-browser create without `/link` can mint a
different person. We don't hold email for reset at the passkey tier. Mitigations:
second device via `/link`, site-side recovery keyed to `ppid`, and isHuman for
identity-backed recovery (same PPID).

### "Do you see my users / can you track them across sites?"

We don't receive your profile data (verify returns `ppid` + assurance only), and
PPIDs are pairwise per hostname so **relying sites** cannot correlate across sites.
Honest operator caveat documented in trust materials.

### "How do I know the privacy claims are true if it's not fully open source?"

The parts you rely on to verify are open (Apache-2.0): Node and Python verifiers
and the credential format. Source: https://github.com/JEDMckenna99/lemma-proof
Offline test harness included.

### "What does it cost?"

Basic verify (passkey continuity) is free — no registration, no API key. isHuman
(IDV-backed person on the same `ppid`, document uniqueness) is the paid step-up,
opt-in per action. Site-block API keys are for enforcement.

### "Does lemma.id only work in the US and Canada?"

No. You can create and use a **passkey lemma.id** anywhere passkeys work. **Human
verification (isHuman)** currently accepts a US or Canadian driver’s license or ID
card only — enforced in the IDV provider config and server-side. Relying sites still
receive only `ppid` + assurance, not country or document details. More countries
will be added over time.

### "Is this Worldcoin / unique-human / proof of personhood?"

No. isHuman is document-rooted. It raises the cost of account rotation. It does
not claim biometric unique-human. Distinct government documents with different
numbers can yield distinct persons on a fresh enrollment.

---

## Do NOT say / avoid in-thread

- Don't claim "zero downtime dependency" — the popup needs us online for new
  presentation mints. Say exactly that instead.
- Don't argue recovery "isn't a problem." Concede the single-device case.
- Don't lead with "passwordless login" as the product — lead with continuity under abuse.
- Don't claim "one account per verified human" or unique-human. Say document.
- Don't link `github.com/JEDMckenna99/lemma-enterprise` — that repo is private. Use
  https://github.com/JEDMckenna99/lemma-proof
