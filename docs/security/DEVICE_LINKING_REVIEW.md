# Device linking security review (Phase F)

## Current production UI path

`LemmaWallet.generateLinkCode()` (`static/js/lemma-wallet.js`) encrypts `walletSecret` with a fresh passkey-derived AES key and places ciphertext in QR URL (`/link#...`). **Raw secret never appears in QR plaintext**, but possession of QR + passkey on receiving device recovers the full secret.

Templates: `templates/wallet_link.html`, `templates/wallet_simple.html`

## Preferred future path (SDK only today)

`beginDeviceTransfer()` / `depositDeviceTransfer()` / `claimDeviceTransfer()` relay **person-root seeds** via Redis (`POST /api/wallet/sync-device`, 60s TTL) without embedding `walletSecret` in QR.

- Backend: `api/ishuman.py`
- Tests: `tests/test_wallet_sync_device.py`
- **Gap:** No production template calls the server-relay flow; UI still uses `generateLinkCode`.

## Recommendations

1. Migrate “Add device” UI from `generateLinkCode` to server-relay transfer when UX parity is validated.
2. Keep QR TTL short; instruct users to scan only on trusted devices.
3. Document residual risk in GA materials: device linking is UX-driven secret transfer, not hardware-bound multi-device keys.
