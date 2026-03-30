# Lemma Architecture: Wallet-Based Authentication

## Overview

Lemma uses a **wallet-based** authentication model with passkey protection. All authentication flows through the user's wallet on lemma.id, ensuring consistent security and privacy across all devices and sites.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LEMMA AUTHENTICATION                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     WALLET + REDIRECT FLOW                           │   │
│   ├─────────────────────────────────────────────────────────────────────┤   │
│   │ • Passkey-protected wallet on lemma.id                              │   │
│   │ • Cross-device session sync via global session                      │   │
│   │ • Privacy-preserving PPIDs (unique per site)                        │   │
│   │ • Client-side wallet secret (never touches server)                  │   │
│   │                                                                     │   │
│   │ ✅ Broad browser support (validate against your supported matrix)    │   │
│   │ ✅ One passkey per day across all devices                           │   │
│   │ ✅ Privacy-preserving (no cross-site tracking)                      │   │
│   │ ✅ Client-side PPID derivation (no server involvement)              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Authentication Flow

### Redirect Flow (Primary)

This is the **primary recommended** authentication method. Validate behavior against your supported browsers/devices.

```
User clicks "Sign in with Lemma"
           │
           ▼
wallet.startRedirectFlow()
           │
           ▼
Redirect to lemma.id/wallet/unlock
           │
           ▼
┌──────────────────────────────────────┐
│  Check: Is global session valid?     │
│                                      │
│  YES → Skip passkey, redirect back   │
│  NO  → Prompt passkey (biometric)    │
└──────────────────────────────────────┘
           │
           ▼
User authenticates (if needed)
           │
           ▼
Encrypt wallet data client-side
           │
           ▼
Redirect back to customer site
           │
           ▼
wallet.checkRedirectReturn()
           │
           ▼
Decrypt wallet data client-side
           │
           ▼
wallet.derivePPID() → Site-specific ID
           │
           ▼
Send PPID to customer backend
```

### Key Benefits

1. **No password** - Passkey (biometric) unlocks wallet
2. **One passkey per day** - Global session syncs across devices
3. **Privacy-preserving** - Each site gets unique PPID
4. **Broad compatibility** - Redirect flow is designed to reduce browser-specific auth issues

### SDK Usage

```javascript
const wallet = new LemmaWallet();
await wallet.init();

// Check for redirect return
const result = await wallet.checkRedirectReturn();
if (result?.success) {
    const ppid = await wallet.derivePPID();
    await signInUser(ppid);
    return;
}

// Check existing auth
const auth = await wallet.getAuthenticatedPPID();
if (auth.authenticated) {
    await signInUser(auth.ppid);
} else if (auth.needsPasskey) {
    // Show sign-in button
    wallet.startRedirectFlow();
}
```

## Cross-Device Session Sync

### How It Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         GLOBAL SESSION SYNC                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Device A (Phone)              Server                    Device B (PC)      │
│   ────────────────              ──────                    ─────────────      │
│                                                                             │
│   1. User unlocks with          2. Global session                           │
│      passkey                       stored in DB                             │
│          │                           │                                      │
│          └──────────────────────────►│                                      │
│                                      │                                      │
│                                      │◄──────────────────────────┐          │
│                                      │                           │          │
│                                 3. Device B checks      4. User visits      │
│                                    global session          site             │
│                                      │                                      │
│                                      │                                      │
│                                 5. Valid? Skip passkey,                     │
│                                    sync session locally                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Session Management

- **Session duration**: Configurable 1-24 hours (default: 24h)
- **Cross-device lock**: Locking on any device locks all devices
- **Heartbeat detection**: Sites detect remote lock via visibility change + 5-min polling

## PPID (Pairwise Pseudonymous Identifiers)

### Privacy Model

```
Wallet Secret (client-side only)
           │
           ▼
    HMAC-SHA256
           │
           ├──── site_a.com ────► PPID_A (unique to site A)
           │
           ├──── site_b.com ────► PPID_B (unique to site B)
           │
           └──── site_c.com ────► PPID_C (unique to site C)
```

- **Same user + same site** → Same PPID (deterministic)
- **Same user + different site** → Different PPID (unlinkable)
- **Wallet secret** → Never leaves the client
- **Cross-site tracking** → Strongly reduced via per-site PPID separation

### PPID Format

```
did:lemma:ppid_<64-character-hex-string>

Example:
did:lemma:ppid_4ecdc53ba75e564cf755975e8d1ec55e08a09f3a31ebdb83bf92b8276b57e1e3
```

## Security Model

### Trust Boundaries

| Component | Trust Level | Location |
|-----------|-------------|----------|
| Wallet secret | Highest | Client IndexedDB only |
| Passkey | Highest | Device secure enclave |
| Global session | Medium | Server (convenience only) |
| PPID | Public | Derived client-side |

### What the Server Knows

| Data | Server Knows? | Notes |
|------|---------------|-------|
| Wallet secret | ❌ Never | Only in client IndexedDB |
| User's sites | ❌ Never | PPIDs derived locally |
| Session status | ✅ Yes | For cross-device sync |
| Wallet ID | ✅ Yes | Pseudonymous identifier |

### Attack Resistance

| Attack | Mitigation |
|--------|------------|
| Phishing | Passkeys bound to lemma.id origin |
| Session hijacking | Global session is convenience, not security boundary |
| Cross-site tracking | Different PPID per site |
| Server compromise | Wallet secret never on server |

## Device Linking

### Flow

```
Device A (has wallet)              Device B (new device)
────────────────────              ────────────────────

1. Generate link code
   (requires fresh passkey)
        │
        ▼
2. Show QR code + copy link
        │
        ├─────────────────────────► 3. Scan QR or paste link
        │
        │                           4. Decrypt wallet data
        │                              (client-side)
        │
        │                           5. Store wallet secret
        │
        │                           6. Register passkey
        │                              for this device
        │
        ▼                           ▼
   Both devices now share      New passkey created
   same wallet secret          (device-specific)
```

### Security

- Link codes expire in 60 seconds
- Requires fresh passkey verification to generate
- Encrypted client-side (server never sees wallet secret)
- Each device gets its own passkey

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER'S BROWSER                                  │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         LEMMA WALLET SDK                                │ │
│  │  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────────────┐ │ │
│  │  │   Passkey    │  │   Wallet Secret  │  │      Session State       │ │ │
│  │  │  (Biometric) │  │   (IndexedDB)    │  │      (IndexedDB)         │ │ │
│  │  └──────────────┘  └──────────────────┘  └──────────────────────────┘ │ │
│  │         │                   │                        │                │ │
│  │         └──────────┬────────┴────────────────────────┘                │ │
│  │                    │                                                   │ │
│  │              ┌─────▼──────┐                                            │ │
│  │              │    PPID    │   HMAC(wallet_secret, site_domain)         │ │
│  │              │ Derivation │                                            │ │
│  │              └────────────┘                                            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                       │
│                                      ▼                                       │
│                          ┌──────────────────────┐                            │
│                          │   Customer Backend    │                            │
│                          │   (receives PPID)     │                            │
│                          └──────────────────────┘                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              LEMMA.ID SERVER                                 │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         GLOBAL SESSION STORE                            │ │
│  │  • Wallet ID → Session status (unlocked_at, expires_at)                │ │
│  │  • Used for cross-device sync (NOT for security)                       │ │
│  │  • Never contains wallet secret or PPIDs                               │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Configuration

### Customer Site

No server configuration required. Just add the SDK:

```html
<script src="https://lemma.id/static/js/lemma-wallet.js"></script>
```

### Session Duration

Users configure at `lemma.id/wallet`:
- Minimum: 1 hour
- Maximum: 24 hours
- Default: 24 hours

## Migration from Traditional Auth

### From Username/Password

```javascript
// Old
const user = await authenticateWithPassword(email, password);

// New
const auth = await wallet.getAuthenticatedPPID();
if (auth.authenticated) {
    const user = await findOrCreateUserByPPID(auth.ppid);
}
```

### From OAuth/OIDC

```javascript
// Old
// const user = await auth0.getUser();
// const userId = user.sub;

// New
const auth = await wallet.getAuthenticatedPPID();
const userId = auth.ppid;
```

## Summary

| Feature | Implementation |
|---------|---------------|
| Authentication | Passkey (biometric) on lemma.id |
| Session sync | Global session in database |
| Identity | PPID derived client-side |
| Privacy | PPID separation helps reduce cross-site tracking |
| Security | Wallet secret never leaves client |
