# isHuman Demo — Presenter Script

**URL:** https://lemma.id/demo/ishuman  
**Duration:** under 3 minutes (guided button path)

---

## 30-second opening (IP ban problem)

> "Bot defense today usually bans IPs, VPNs, or whole ISPs. Real users get caught in the blast radius, and attackers just rotate infrastructure. Lemma flips that: one IDV-backed human proof, reused across sites, with accountability at the *human* layer — block a site-private ID, force fresh IDV, or revoke network-wide when abuse is confirmed."

---

## 90-second guided demo (click path)

1. Open **https://lemma.id/demo/ishuman**
2. Click **Run 3-minute demo** (wallet unlocks automatically if needed)
3. Narrate while the wizard runs:
   - **Step 1–2:** "User verifies once; proof lands in the browser wallet — no passwords on stage."
   - **Step 3:** "Same human, two businesses — ticketing and trials get *different* private IDs (PPIDs)."
   - **Step 4–5:** "Ticketing blocks the abusive PPID; trials still shows HUMAN — site-scoped, not a network ban."
   - **Step 6–7:** "Network escalation: both sites go DENY with reason revoked."
4. Optional: open customer deep links:
   - Ticketing: **Reserve** → `…/reserve`
   - Trials: **Start trial** → `…/start-trial`

---

## 30-second revocation climax

> "This isn't UI theater — server derive is blocked, canonical check shows site_block and site_ppid_revoked, and network revoke kills the reusable proof everywhere. Businesses integrate with two lines; verify latency is on the card in milliseconds."

Point at **Abuse response** panel: Site block → Site-scoped only → Network revoke.

---

## Backup if Stripe UI fails

- Guided demo uses **test-mode one-click verify** (server-side token) — no document upload.
- Operator console (collapsed): **Complete test verification** + **Poll / store proof** if a session was started manually.
- Do **not** type API keys on stage; tokens are server-injected on `/demo/ishuman` only.

---

## FAQ (quick answers)

| Question | Answer |
|----------|--------|
| Privacy | Sites never see government ID; no cross-site user ID; only human + expiry + trust. |
| Cost | ~$2 per Stripe Identity verification (one-time per user for reuse). |
| Integration time | Two-line snippet; `IsHumanVerifier({ siteId: hostname }).verify()`. |
| vs CAPTCHA | Reusable proof + revocation; not a race attackers win with farms. |
| vs IP ban | Punish the human proof, not the ISP/VPN range. |

---

## Pre-flight checklist

- [ ] `LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=true` on prod
- [ ] Demo test + admin tokens set on Heroku
- [ ] `python scripts/run_ishuman_prod_revocation_smoke.py --base-url https://lemma.id` → 8/8
- [ ] `python scripts/smoke_ishuman_customer_sites.py` → PASS
- [ ] Fresh browser profile or cleared wallet for clean run
