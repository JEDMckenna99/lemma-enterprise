# Lemma Architecture: Wallet-First Authentication

## Overview

Lemma uses a **wallet-first** authentication model that prioritizes decentralized, offline-capable verification. This document explains the architecture and when to use each authentication method.

## The Two Authentication Paths

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LEMMA AUTHENTICATION                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────┐    ┌─────────────────────────────────┐   │
│   │   WALLET-FIRST (Primary)    │    │    OAUTH (Fallback/API)         │   │
│   ├─────────────────────────────┤    ├─────────────────────────────────┤   │
│   │ • User login                │    │ • Server-to-server API calls    │   │
│   │ • Permission verification   │    │ • Third-party integrations      │   │
│   │ • Bot protection            │    │ • Delegated access              │   │
│   │                             │    │                                 │   │
│   │ ✅ Works offline            │    │ ❌ Requires server              │   │
│   │ ✅ ~1ms verification        │    │ ⚠️ ~50-200ms verification       │   │
│   │ ✅ No server dependency     │    │ ⚠️ Token can be stolen         │   │
│   │ ✅ Privacy-preserving       │    │ ⚠️ Centralized token storage   │   │
│   └─────────────────────────────┘    └─────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Wallet-First Flow (Primary)

This is the **recommended** authentication method for user login.

### How It Works

```
1. User clicks "Sign in with Lemma"
                │
                ▼
2. Browser checks wallet for existing permission
                │
    ┌───────────┴───────────┐
    │                       │
    ▼                       ▼
Has Permission          No Permission
    │                       │
    ▼                       ▼
3a. Verify locally      3b. Request from Lemma.id
    (no server call)        │
    │                       ▼
    │                   4b. Store in wallet
    │                       │
    ▼                       ▼
4. User authenticated   User authenticated
   (~1ms)                  (one-time server call)
```

### Key Benefits

1. **No password** - Passkey (biometric) unlocks wallet
2. **No email verification loop** - Instant authentication
3. **Works offline** - After first permission grant
4. **Privacy** - No per-verification data sent to Lemma

### SDK Usage

```javascript
const lemma = new LemmaIAM({
    siteId: 'your_site_id',
    debug: true
});

// Primary method - tries wallet first
const result = await lemma.signIn();

if (result.success) {
    console.log('User:', result.user);
    console.log('Method:', result.method);     // 'wallet' or 'oauth'
    console.log('Offline:', result.offline);   // true = no server call
}
```

## OAuth Flow (Fallback/API)

Use OAuth when:
- Wallet is not available (server-side code)
- You need API access tokens
- Third-party app needs delegated access

### How It Works

```
1. Site redirects to /oauth/authorize
                │
                ▼
2. User unlocks wallet + consents
                │
                ▼
3. Lemma redirects back with auth code
                │
                ▼
4. Site exchanges code for access token
                │
                ▼
5. Site uses token for API calls
```

### SDK Usage

```javascript
// Explicit OAuth (when needed)
lemma.signInWithOAuth({
    scope: 'profile permissions'
});

// Handle callback
const result = await lemma.handleOAuthCallback(code, state);
```

## When to Use What

| Scenario | Method | Why |
|----------|--------|-----|
| User login on website | Wallet-first | Fast, offline-capable |
| User login on mobile app | Wallet-first | Native passkey support |
| Server calling Lemma API | OAuth | No browser/wallet available |
| Third-party integration | OAuth | Standard protocol |
| Bot protection check | Wallet-first | Local verification |
| Background permission check | Either | Depends on context |

## Technical Comparison

| Aspect | Wallet-First | OAuth |
|--------|-------------|-------|
| **Verification time** | ~1ms | ~50-200ms |
| **Server dependency** | None (after grant) | Every verification |
| **Token storage** | Browser wallet (encrypted) | Server database |
| **Revocation** | Bloom filter sync | Token invalidation |
| **Works offline** | Yes | No |
| **Phishing resistance** | High (passkey bound) | Medium (token can leak) |

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER'S BROWSER                                  │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         LEMMA WALLET                                    │ │
│  │  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────────────┐ │ │
│  │  │   Passkey    │  │    Permission    │  │    Issuer Public Keys   │ │ │
│  │  │  (encrypted) │  │     Lemmas       │  │      (cached)           │ │ │
│  │  └──────────────┘  └──────────────────┘  └──────────────────────────┘ │ │
│  │                                                                        │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │ │
│  │  │                    LOCAL VERIFICATION                             │ │ │
│  │  │  • Ed25519 signature check (Web Crypto API)                       │ │ │
│  │  │  • Expiration check                                               │ │ │
│  │  │  • Revocation check (bloom filter)                                │ │ │
│  │  └──────────────────────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ (only for issuance/revocation)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              LEMMA.ID SERVER                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │
│  │ Issue Lemmas    │  │ Revoke Lemmas   │  │ Publish Revocation Filter   │ │
│  │ (KMS-backed)    │  │ (network-wide)  │  │ (sync to verifiers)         │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Configuration

### Required Environment Variables

```bash
# Core secrets (all required in production)
LEMMA_OAUTH_JWT_SECRET=<64-char-random-string>
LEMMA_NETWORK_AUTH_KEY=<64-char-random-string>
LEMMA_PPID_ROOT_KEY=<64-char-random-string>
LEMMA_BILLING_HMAC_SECRET=<64-char-random-string>
LEMMA_HPKE_SERVER_KEY=<64-char-random-string>
LEMMA_WALLET_SALT=<64-char-random-string>
SECRET_KEY=<flask-secret-key>

# Optional (for full functionality)
REDIS_URL=<redis-connection-string>
AWS_ACCESS_KEY_ID=<aws-key>
AWS_SECRET_ACCESS_KEY=<aws-secret>
LEMMA_KMS_KEY_ID=<kms-key-id>
STRIPE_SECRET_KEY=<stripe-key>
```

### Generate Secrets

```bash
# Generate a secure random secret
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Migration from OAuth-Only

If you're currently using only OAuth, migrating to wallet-first is simple:

1. Update SDK to latest version
2. Change `signInWithOAuth()` to `signIn()`
3. The SDK automatically handles the wallet-first flow with OAuth fallback

```javascript
// Before (OAuth-only)
lemma.signInWithOAuth();

// After (wallet-first with OAuth fallback)
lemma.signIn();  // Tries wallet first, falls back to OAuth if needed
```

## Summary

- **User login → Wallet-first** (primary, recommended)
- **API access → OAuth** (when needed)
- **The SDK handles both** automatically via `signIn()`
