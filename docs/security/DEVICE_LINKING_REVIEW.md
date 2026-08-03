# Device linking security review

## Production paths (current)

### 1. Pull (recommended primary)

Empty device opens `/link` → **Show QR Code** → `beginLinkReceive()`.

- QR encodes `/link/send#…` with ephemeral X25519 pubkey + `transfer_id` only.
- Phone with lemma.id scans via native Camera → `/link/send` → fresh passkey →
  seals person-root seeds → `POST /api/wallet/link-receive` deposit.
- Empty device claims once, then `registerPasskey()`.

**Why strongest:** stealing the receive QR does not help without the sender’s passkey.

### 2. Push from manager (convenience)

Unlocked `/app` → **Generate QR Code** / **Send Transfer Link** → `beginLinkPush()`.

- QR/link carry only `{ v:2, mode:push, transfer_id }`, never secrets.
- Empty device opens link → `acceptLinkPushOffer` registers its pubkey.
- Both screens show the same **6-digit confirmation code**.
- Sender confirms codes match → **one** fresh passkey → `confirmLinkPushDeposit`
  (creating the offer does not require a separate passkey when already unlocked).
- Receiver claims once, keeps the enrollment grant, then is prompted immediately
  for `registerPasskey()` / device-enroll on the new browser.

**Why confirm code stays:** passkey proves the *sender*; the code binds the *receiver*
so a stolen transfer link cannot race-register and receive the deposit.

### 3. Seed transfer tab on `/link`

`beginDeviceTransfer` / `depositDeviceTransfer` / `claimDeviceTransfer` via
`POST /api/wallet/sync-device` (60s TTL). Person-root seeds only; no raw wallet secret in QR.

## Explicitly removed (do not restore)

`generateLinkCode` / `linkDevice` / `_decryptLinkQR`, embedded ciphertext + AES key
in `/link#…`. Possession of the URL recovered the identity. Guarded by
`tests/test_device_link_security.py`.

## Residual risk

Device linking is UX-driven sealed secret transfer, not hardware-bound multi-device keys.
Keep TTLs short; instruct users to scan/open only on trusted devices; never share
push transfer links in public channels without matching the confirm code.
