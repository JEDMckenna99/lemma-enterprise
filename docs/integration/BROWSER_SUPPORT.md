# Browser support — Sign in with lemma.id

Passkey login requires a browser with WebAuthn and (for encrypted local lemma.id storage on lemma.id) PRF support.

## Supported browsers (passkey sign-in)

| Browser | Desktop | Mobile | Notes |
|---------|---------|--------|-------|
| Chrome / Edge | Yes | Yes (Android) | Preferred for development |
| Safari | Yes (macOS 13+) | Yes (iOS 16+) | Requires user gesture for popup |
| Firefox | Yes | Limited | Test popup flow on target devices |

## PRF (encrypted local lemma.id at rest)

PRF extends WebAuthn and is required when the user's local lemma.id encrypts storage at rest. Without PRF, first-time users on older browsers may see `prf_required_for_encrypted_storage` from the lemma.id SDK layer (internal `LemmaWallet` class).

| Platform | PRF |
|----------|-----|
| Chrome 118+ | Supported |
| Safari 17+ | Supported |
| Firefox | Not yet — use supported browsers for first-time lemma.id creation |

## SDK stable outcomes

`verifyForBackend()` returns these developer-facing `reason` values for fallback UX:

| Reason | Meaning | Suggested UX |
|--------|---------|--------------|
| `passkey_unsupported` | WebAuthn unavailable | Offer alternate browser or device |
| `popup_blocked` | Popup closed or blocked | Show "allow popups" hint; offer redirect fallback |
| `user_cancelled` | User dismissed the ceremony | Keep action denied; offer retry button |
| `rate_limited` | Issuance rate limit hit | Back off and retry later |

See [ERROR_CODES.md](../ERROR_CODES.md) for the full list.

## Testing without a browser

Use offline test helpers so CI never touches lemma.id or WebAuthn:

- **Python:** `lemma_proof_verifier_testing.py` (`mint_test_presentation`, `create_offline_test_context`)
- **Node:** `@lemma.id/proof-verifier/testing` (`mintTestPresentation`, `verifyTestPresentationOffline`)

Documented in [QUICK_START_SIMPLE_LOGIN.md](QUICK_START_SIMPLE_LOGIN.md#testing-your-integration).
