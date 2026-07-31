# Presale code distributor: demo script

**Live demo:** https://tickets-demo.lemma.id/?tour=presale

**Duration:** ~3 minutes

**Hub context:** This is **Enforce in the wild**: action-level presence stamps on a relying site. The hub demo covers Create · Sign in · Enforce at the identity layer; presale shows stamps at claim time. The tickets site default `/` is the Sign in shell; open `/?tour=presale` for this tour.

## One-liner

Phone is for delivery; passkey is who you are; Face ID again to get the code.

## Talk track

### 1. Join presale (Step 1)

- Click **Step 1, Passkey register for drop**.
- Say: email and phone are CRM/delivery fields on the relying site only, not identity, not sent to lemma.id.
- Point at the defense strip: site PPID, action stamp, server nonce.

### 2. Unlock code (Step 2)

- Click **Step 2, Fresh passkey unlocks unique code**.
- Say: this is a fresh passkey ceremony at claim time, bots cannot replay a cached session.
- Toggle **Show backend gates** and show `fresh_passkey_attestation` in the cryptographic envelope (redacted excerpt).

### 3. Retry same wallet

- Click **Try again with same wallet**.
- Say: ledger enforces one code per verified person per drop, enumeration without farming.

### 4. Risk flag + IDV

- Click **Simulate site risk flag**, then claim again.
- Say: site doubt requires fresh IDV (`verifyFreshForBackend`) before code issuance when policy requires `ishuman` assurance.

### 5. Attack lab (optional)

- Expand **Attack lab** (visible in tour mode).
- **Replay last stamp** → `action_nonce_reused`.
- **Skip Step 1** (before registering) → `registration_required`.

## Objection handlers

| Objection | Response |
|-----------|----------|
| "We already use SMS OTP" | OTP proves possession of a phone number, not present control of a wallet. Fresh passkey at unlock binds the code to a site-private PPID with replay protection. |
| "Passkeys add friction" | Step 1 is low-friction passkey register; Step 2 is intentional friction at the high-value moment (code unlock). |
| "What does lemma.id see?" | Action names, bodies, and contact fields stay on your site. lemma.id attests fresh passkey to an opaque action commitment only. |
| "Can one person get multiple codes?" | No, ledger keys `(drop_id, ppid)`; same wallet retry is denied. |

## Manual deploy checklist

After merging demo UI changes:

1. `git subtree push --prefix demo-sites https://git.heroku.com/lemma-demo-tickets.git main`
2. Open https://tickets-demo.lemma.id/?tour=presale and confirm defense strip + tour banner
3. Confirm SDK loads with `requireFreshPasskey` support from lemma.id
4. Optional: set `LEMMA_PRESALE_SQLITE_PATH` on Heroku for restart-persistent ledger
