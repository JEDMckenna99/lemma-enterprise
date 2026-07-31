# Sign in with lemma.id — demo presenter script

Hub narrative: **Create · Sign in · Enforce**.

## Create

1. Create or unlock a passkey-protected lemma.id on device.
2. Say: continuity only at first, not proof of unique humanness until a site requires it.

## Sign in

3. Sign in once and show two distinct site-private PPIDs for ticketing and trials.
4. Say: same lemma.id, unlinkable IDs; signed presentations verified offline on each site backend. Demo sites use the same `<lemma-signin>` drop-in from the docs quickstart.
5. Optional: expand **Developer view** for presentation JSON; mention **presence** (fresh passkey on high-value actions), detail lives on the presale tour, not the hub spine.

## Enforce

6. **Set assurance**: require human proof on ticketing; show valid-but-insufficient passkey proof; complete IDV; re-sign-in with **same PPID** at `ishuman`.
7. **Doubt**: create temporary site doubt; invoke `verifyFreshForBackend()`. Site can doubt passkey-only or post-human-proof users.
8. Show fresh proof clears only the ticketing doubt; it never clears a site ban or touches trials.
9. **Ban**: block the ticketing PPID; show ticketing denied while trials remains valid.
10. Explain the ban survives credential renewal, wallet recovery, document renewal, and fresh IDV until ticketing explicitly unblocks it.
11. Show local backend presentation verification and the privacy-safe billing event fields.

## Presale tour (Enforce in the wild)

On https://tickets-demo.lemma.id/?tour=presale:

- **Step 1**: Passkey register via `stampAction` + server challenge; email/phone stay site-local.
- **Step 2**: Unlock unique code with fresh passkey `stampAction` (`requireFreshPasskey: true`); ledger keys `(drop_id, ppid)`.
- **Optional**: Simulate site risk flag → fan completes fresh IDV (`verifyFreshForBackend`) when policy requires human proof → retry at `ishuman`.
- Second claim with the same wallet is denied with `allocation_already_claimed`.
- **Attack lab**: replay stamp (`action_nonce_reused`) or skip Step 1 (`registration_required`).

Do not describe or demonstrate network-wide user enumeration or revocation.
Those legacy endpoints are retired and return HTTP 410.
