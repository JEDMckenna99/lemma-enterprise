# Presale code distributor: demo script

**Live demo:** https://tickets-demo.lemma.id/?tour=presale

**Duration:** ~3 minutes

**Hub context:** Default tickets site `/` is the **user-lane welcome tour**. This presale tour at `/?tour=presale` is **Enforce in the wild** for integrators. The hub **Try it** lane links to the welcome tour; **See how it works** covers Create · Sign in · Enforce.

## One-liner

Passkey is who you are; Face ID again to get the code; delivery contact is optional after you claim.

## Talk track

### 1. Join presale (Step 1)

- Click **Step 1, Passkey register for drop** (no email or phone first).
- Say: passkey proves identity — no signup form, nothing sent to lemma.id.

### 2. Unlock code (Step 2)

- Click **Step 2, Fresh passkey unlocks unique code**.
- Say: fresh passkey at claim time — bots cannot replay a cached session.
- Optional delivery: after success, email/phone are **where to send the code** — site-local only.

### 3. Retry same lemma.id

- Click **Try again with same lemma.id**.
- Say: one code per person for this drop — you already got yours.

### 4. Risk flag + IDV

- Click **Simulate site risk flag**, then claim again.
- Say: site doubt requires fresh identity check before code issuance when human proof is required.

### 5. Attack lab (optional)

- Expand **Attack lab** (presale tour mode or engineer view).
- **Replay last stamp** → blocked: old approval reused.
- **Skip Step 1** (before registering) → sign up for the drop first.

## Objection handlers

| Objection | Response |
|-----------|----------|
| "We already use SMS OTP" | OTP proves possession of a phone number, not present control of a lemma.id. Fresh passkey at unlock binds the code to a site-private PPID with replay protection. |
| "Passkeys add friction" | Step 1 is low-friction passkey register; Step 2 is intentional friction at the high-value moment (code unlock). |
| "What does lemma.id see?" | Action names, bodies, and contact fields stay on your site. lemma.id attests fresh passkey to an opaque action commitment only. |
| "Can one person get multiple codes?" | No, ledger keys `(drop_id, ppid)`; same lemma.id retry is denied. |

## Manual deploy checklist

After merging demo UI changes:

1. `git subtree push --prefix demo-sites https://git.heroku.com/lemma-demo-tickets.git main`
2. Open https://tickets-demo.lemma.id/?tour=presale and confirm defense strip + tour banner
3. Confirm SDK loads with `requireFreshPasskey` support from lemma.id
4. Optional: set `LEMMA_PRESALE_SQLITE_PATH` on Heroku for restart-persistent ledger
