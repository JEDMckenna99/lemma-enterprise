# Using the delay logger on a real delivery route

The **Field Delay Logger** is designed for use on your phone while working. It does **not** store package IDs, addresses, customer info, or photos.

## Setup (once)

1. Deploy to Heroku or run locally on your home Wi‑Fi (see [DEPLOY_HEROKU.md](DEPLOY_HEROKU.md)).
2. On your phone, open **`https://<your-app>/metrics/log`**
3. **Install to home screen** (recommended):
   - **iPhone:** Safari → Share → **Add to Home Screen** → name it "Delay Log"
   - **Android:** Chrome → menu → **Install app** or **Add to Home screen**
4. Optional: open **Start** once per day to set route type (urban/suburban/rural) and weather.

After install, the app opens full-screen and works **offline** — no signal required to log delays.

## During your route

1. Tap the **Delay Log** icon when something is slow.
2. Tap one button per row (big targets, one-handed):
   - Stop type (house, apartment, etc.)
   - Signal (good / weak / no service)
   - What was slow (scan, confirm, photo, nav, …)
   - How long (0–2s up to failed/retry)
   - Retry needed? Yes/No
3. Tap **Save Event** — saved instantly on the phone.
4. Repeat as needed. Stop type and signal are remembered for the next log at the same kind of stop.

**Do not enter:** tracking numbers, addresses, customer names, access codes, or package counts tied to identifiers. End-of-shift summary only asks for **total stop/package counts**.

## After your route

- **Report** — today's totals and estimated time lost (works offline).
- **End** — optional shift summary + **Export CSV** to email/save yourself.
- CSV stays on your device until you export it.

## Privacy

- All logs live in **browser localStorage** on your phone.
- Server is optional (validation echo only when online).
- Nothing syncs to Amazon or delivery systems.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Save fails / blank error | Make sure each row has a selection (all five groups). |
| Offline badge | Normal in dead zones — logs still save. |
| Lost data | Don't clear browser data for this site; export CSV weekly. |
| New phone | Export CSV from old phone, or start fresh collection. |

## Local testing before first shift

```powershell
cd delivery-prototype
flask --app app run --port 5099 --host 0.0.0.0
```

On phone (same Wi‑Fi): `http://<your-pc-ip>:5099/metrics/log`
