# Lemma vs Traditional Auth: Security, Privacy & Operational Cost Analysis

> A technical comparison of Lemma's local-first authentication model against common centralized providers (Auth0, Okta, Firebase Auth, Cognito).
> Figures are directional and should be validated for your environment, traffic profile, and security requirements.

## Executive Summary

| Category | Traditional Auth | Lemma | Practical Note |
|----------|------------------|-------|----------------|
| **Security** | Server-trusting model | Client-verifiable proofs | Different trust boundaries; evaluate threat model fit |
| **Privacy** | Centralized tracking possible | PPID unlinkability | Depends on integration and telemetry choices |
| **Operational Cost** | ~$0.01-0.05/MAU | ~$0.001/MAU | Model-based estimate, not a guaranteed outcome |
| **Network Calls** | 5-7 per login | 1 (issuance only) | Depends on cache/session strategy |
| **Offline Capability** | Limited | Strong after issuance | Revocation/issuance still require network |
| **Vendor Lock-in** | Typically high | Lower with local proofs | Migration cost still applies |
| **Maturity** | Production-grade | Emerging | Validate before critical workloads |
| **Enterprise Integrations** | SAML/LDAP/AD | Growing | Existing enterprise stack may require adapters |
| **User Directory** | Managed only | Managed or self-hosted patterns | Operational ownership differs |

---

## 1. Security Analysis

### 1.1 Attack Surface Comparison

#### Traditional Auth (Auth0/Okta Model)

```
┌─────────────────────────────────────────────────────────────────┐
│                    ATTACK SURFACE                                │
├─────────────────────────────────────────────────────────────────┤
│  ⚠️  Auth Server         - Single point of compromise           │
│  ⚠️  Token Storage       - Server-side session state            │
│  ⚠️  Network Interception- Man-in-the-middle on token exchange  │
│  ⚠️  OAuth Flow          - CSRF, redirect attacks               │
│  ⚠️  Database            - Credential breach exposure           │
│  ⚠️  API Keys            - Leaked secrets enable impersonation  │
│  ⚠️  Rate Limiting       - Brute force if misconfigured         │
└─────────────────────────────────────────────────────────────────┘
```

**Risk Profile:**
- **Breach Impact**: HIGH - Compromising auth server exposes ALL users
- **Blast Radius**: Millions of users from single breach
- **Historical**: Auth0 (2020), Okta (2022) experienced breaches

#### Lemma Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ATTACK SURFACE                                │
├─────────────────────────────────────────────────────────────────┤
│  ✅ No Central Token Store - Nothing to breach                  │
│  ✅ Local Verification     - No network interception risk       │
│  ✅ Passkey Bound          - Hardware-backed, phishing-resistant│
│  ⚠️  Bridge Iframe         - postMessage validation required    │
│  ⚠️  IndexedDB Storage     - Local XSS could access credentials │
│  ⚠️  Public Key Trust      - Must trust issuer public keys      │
└─────────────────────────────────────────────────────────────────┘
```

**Risk Profile:**
- **Breach Impact**: LOW - Each user's wallet is independent
- **Blast Radius**: Single user per compromise
- **Mitigations**: Passkey protects wallet unlock, credentials are signed

### 1.2 Authentication Strength

| Factor | Traditional | Lemma |
|--------|-------------|-------|
| **Root of Trust** | Password + MFA | Passkey (biometric) |
| **Phishing Resistance** | Medium (MFA helps) | **High** (WebAuthn) |
| **Replay Attacks** | Token expiry | **Signature + expiry** |
| **Session Hijacking** | Cookie theft risk | **Passkey required** |
| **Credential Stuffing** | Vulnerable | **Not applicable** |

### 1.3 Cryptographic Security

**Lemma's Ed25519 Verification:**
```
Signature Verification:
- Algorithm: Ed25519 (128-bit security)
- Key Size: 256-bit
- Verification: ~1ms client-side
- No network required for verification
```

**Traditional JWT Verification:**
```
Token Verification:
- Requires network call to auth server
- OR shared secret (security risk if leaked)
- Token rotation requires server coordination
```

### 1.4 Session Security Comparison

| Aspect | Traditional | Lemma |
|--------|-------------|-------|
| **Session Storage** | Server DB/Redis | Client IndexedDB |
| **Session Theft** | Cookie/token theft | Requires passkey |
| **Session Extension** | Silent refresh | **Tap-only (user presence)** |
| **Max Lifetime** | Configurable | 8 days (then re-auth) |
| **Revocation** | Server-side instant | Client-side sync (~1hr lag) |

**Lemma Session Config:**
```javascript
SESSION_CONFIG = {
    DEFAULT_DURATION: 24 * 60 * 60 * 1000,  // 24 hours
    MAX_EXTENSIONS: 7,                       // Max 7 extensions
    // Total: 8 days without full re-authentication
}
```

**Session Sync Hardening (Server-Side):**
- CORS allowlist for credentialed requests (no wildcard origins)
- CSRF double-submit token required for session sync and credential operations
- Session tokens include random nonce + HMAC signature

---

## 2. Privacy Analysis

### 2.1 Data Collection Comparison

#### Traditional Auth Providers Collect:

```
┌────────────────────────────────────────────────────────────┐
│  DATA COLLECTED BY AUTH0/OKTA                              │
├────────────────────────────────────────────────────────────┤
│  • Email addresses                                         │
│  • Phone numbers                                           │
│  • Login timestamps                                        │
│  • IP addresses                                            │
│  • Device fingerprints                                     │
│  • Session durations                                       │
│  • Which sites you authenticate to                         │
│  • Authentication frequency                                │
│  • Geographic locations                                    │
│  • User agents/browsers                                    │
│  • MFA method usage                                        │
└────────────────────────────────────────────────────────────┘
```

#### Lemma Collects:

```
┌────────────────────────────────────────────────────────────┐
│  DATA COLLECTED BY LEMMA.ID                                │
├────────────────────────────────────────────────────────────┤
│  • Issuance requests (when credentials are created)        │
│  • Revocation requests (when credentials are revoked)      │
│                                                            │
│  NOT COLLECTED:                                            │
│  ✗ Which sites you authenticate to                         │
│  ✗ When you authenticate                                   │
│  ✗ Authentication frequency                                │
│  ✗ Session data                                            │
│  ✗ IP addresses during verification                        │
└────────────────────────────────────────────────────────────┘
```

### 2.2 Cross-Site Tracking Protection

#### Traditional Auth: Cross-Site Correlation Possible

```
User authenticates:
  Site A → Auth0 → token_a (sub: "user123")
  Site B → Auth0 → token_b (sub: "user123")
  Site C → Auth0 → token_c (sub: "user123")

Auth0 knows: User123 uses Sites A, B, C
Sites could correlate: Same sub = same user
```

#### Lemma: Pairwise Pseudonymous Identifiers (PPIDs)

```javascript
// Different PPID for each site - unlinkable
subject = HMAC(master_user_secret, rp_id)

Site A sees: did:lemma:ppid_abc123def...
Site B sees: did:lemma:ppid_xyz789ghi...
Site C sees: did:lemma:ppid_qrs456jkl...

Lemma is designed to reduce correlation by avoiding a shared cross-site identifier in default flows.
Sites receive different identifiers by site; correlation risk still depends on additional identifiers sites collect or share.
```

### 2.3 Privacy Properties

| Property | Traditional | Lemma |
|----------|-------------|-------|
| **Provider can track logins** | ✅ Yes | Reduced in local verification paths (still depends on issuance/session/revocation flows) |
| **Cross-site correlation** | ✅ Possible | Reduced by PPID design; not absolute if sites share extra identifiers |
| **Session data centralized** | ✅ Yes | Can be reduced in credential-first flows; optional server sessions still exist |
| **Verification observable** | ✅ Yes | Local hot-path can be unobserved by issuer after sync |
| **Data portability** | Limited | **Full (wallet export)** |

### 2.4 GDPR/Privacy Compliance

| Requirement | Traditional | Lemma |
|-------------|-------------|-------|
| **Data minimization** | Collects more than needed | **Minimal by design** |
| **Right to erasure** | Requires provider action | **User controls wallet** |
| **Data portability** | Provider-dependent | **Built-in export** |
| **Consent** | Required for tracking | Reduced tracking surface by design (integration-dependent) |

---

## 3. Operational Cost Analysis

### 3.1 Network Call Breakdown

#### Traditional Auth (Per Login Session)

```
┌────────────────────────────────────────────────────────────┐
│  OPERATION                │  CALLS  │  LATENCY (TYPICAL)  │
├────────────────────────────────────────────────────────────┤
│  Initial page load        │  1-2    │  50-100ms           │
│  Check session/token      │  1      │  20-50ms            │
│  Token refresh (hourly)   │  1      │  30-80ms            │
│  Token validation         │  1      │  20-50ms            │
│  User info fetch          │  1      │  30-80ms            │
│  Logout                   │  1      │  20-50ms            │
├────────────────────────────────────────────────────────────┤
│  TOTAL PER SESSION        │  5-7    │  170-410ms          │
│  TOTAL PER HOUR (refresh) │  6-8    │  200-490ms          │
└────────────────────────────────────────────────────────────┘
```

#### Lemma (Per Login Session) - Current Implementation

```
┌────────────────────────────────────────────────────────────┐
│  OPERATION                │  CALLS  │  LATENCY            │
├────────────────────────────────────────────────────────────┤
│  Initial page load        │  0      │  0ms (SW cached)    │
│  Check session            │  0      │  <5ms (IndexedDB)   │
│  Session extension        │  0      │  ~200ms (passkey)   │
│  Credential verification  │  0      │  ~1ms (Ed25519)     │
│  Revocation sync          │  1*     │  ~100ms (background)│
├────────────────────────────────────────────────────────────┤
│  TOTAL PER SESSION        │  0      │  <10ms              │
│  TOTAL PER HOUR           │  0      │  <10ms              │
└────────────────────────────────────────────────────────────┘

* Revocation sync is background, once per hour, non-blocking
```

### 3.1.1 Detailed Scenario: User Logs Into 3 Sites

**Traditional Auth (Auth0/Okta):**
```
┌─────────────────────────────────────────────────────────────┐
│  EVENT                          │ CALLS │ WHAT HAPPENS      │
├─────────────────────────────────────────────────────────────┤
│  Site A - First login           │   3   │ OAuth flow→token  │
│  Site A - Session checks (×5/hr)│  10   │ Validate token    │
│  Site A - Token refresh (×2)    │   2   │ Refresh endpoint  │
│  Site B - First login           │   3   │ OAuth flow→token  │
│  Site B - Session checks (×3/hr)│   6   │ Validate token    │
│  Site B - Token refresh (×1)    │   1   │ Refresh endpoint  │
│  Site C - First login           │   3   │ OAuth flow→token  │
│  Site C - Session checks (×2/hr)│   4   │ Validate token    │
├─────────────────────────────────────────────────────────────┤
│  TOTAL NETWORK CALLS            │  32+  │ All require server│
│  SERVER LOAD                    │  32+  │ Auth server hit   │
│  LATENCY ADDED                  │~1.5-3s│ Total auth latency│
└─────────────────────────────────────────────────────────────┘
```

**Lemma (With Server Sync for Unified Wallet):**
```
┌─────────────────────────────────────────────────────────────┐
│  EVENT                          │ CALLS │ WHAT HAPPENS      │
├─────────────────────────────────────────────────────────────┤
│  Unlock wallet (once per day)   │   1   │ Passkey + cookie  │
│  Site A - Credential issuance   │   1   │ Issue + DB sync   │
│  Site A - All verifications     │   0   │ Local Ed25519     │
│  Site B - Bridge session check  │   0   │ Cookie validates  │
│  Site B - Credential issuance   │   1   │ Issue + DB sync   │
│  Site B - All verifications     │   0   │ Local Ed25519     │
│  Site C - Bridge session check  │   0   │ Cookie validates  │
│  Site C - Credential issuance   │   1   │ Issue + DB sync   │
│  Site C - All verifications     │   0   │ Local Ed25519     │
│  View wallet (optional)         │   1   │ Fetch from DB     │
├─────────────────────────────────────────────────────────────┤
│  TOTAL NETWORK CALLS            │  4-5  │ Only issuance     │
│  SERVER LOAD                    │  4-5  │ Minimal hits      │
│  LATENCY ADDED                  │ ~50ms │ Issuance only     │
└─────────────────────────────────────────────────────────────┘
```

### 3.1.2 Network Call Categories

| Category | Traditional | Lemma | Reduction |
|----------|-------------|-------|-----------|
| **Authentication** | 3-5 per login | 1 (first time) | **80-90%** |
| **Session validation** | Every request | 0 (local) | **100%** |
| **Token refresh** | Hourly | Never | **100%** |
| **Permission check** | Per request | 0 (local) | **100%** |
| **Credential issuance** | N/A | 1 per cred | N/A |
| **Wallet sync** | N/A | 1 per issuance | N/A |

### 3.1.3 When Lemma Server Is Called (Complete List)

| Action | Calls | When | Purpose |
|--------|-------|------|---------|
| Wallet unlock | 1 | Once per 24hr | Passkey auth |
| Set session cookie | 1 | After unlock | Cross-site session |
| Credential issuance | 1 | First site access | Sign credential |
| Credential DB sync | 1 | After issuance | Unified wallet |
| Fetch wallet (UI) | 1 | View lemma.id/wallet | Display all creds |
| Revocation sync | 1 | Hourly, background | Security update |

**NEVER calls server for:**
- ✗ Session validation (local cookie + IndexedDB)
- ✗ Token refresh (no tokens!)
- ✗ Permission verification (local Ed25519)
- ✗ Credential verification (local crypto)
- ✗ User info lookup (in credential)

### 3.1.4 Server Load at Scale (Daily)

| MAU | Traditional | Lemma | Savings |
|-----|-------------|-------|---------|
| 1K | 32,000 req | 4,000 req | **8× fewer** |
| 10K | 320,000 req | 40,000 req | **8× fewer** |
| 100K | 3.2M req | 400K req | **8× fewer** |
| 1M | 32M req | 4M req | **8× fewer** |

**Key Insight:** After credential issuance, all verification is **100% local**.
The server sync is purely for the **unified wallet view** convenience feature.

### 3.2 Infrastructure Cost Comparison

#### Traditional Auth Provider Costs

| Provider | Pricing Model | Est. Cost/MAU |
|----------|---------------|---------------|
| **Auth0** | $0.018-0.070 per MAU | $0.02-0.07 |
| **Okta** | $2-8 per user/month (enterprise) | $0.067-0.27 |
| **Firebase Auth** | Free tier + backend costs | $0.01-0.02 |
| **Cognito** | $0.0055 per MAU | $0.005-0.01 |

**Hidden Costs:**
- Token storage (Redis/DB)
- Network egress
- Rate limiting infrastructure
- DDoS protection for auth endpoints
- Session management servers

#### Lemma Infrastructure Costs

| Component | Cost | Notes |
|-----------|------|-------|
| **Issuance Server** | ~$50-200/mo | Only for issuance, not verification |
| **CDN (Cloudflare)** | Free-$20/mo | Static file serving |
| **Revocation Sync** | ~$10-50/mo | Lightweight periodic sync |

**Est. Cost Per MAU: $0.001-0.005**

```
Cost Comparison (100,000 MAU):

Traditional (Auth0):  100,000 × $0.02 = $2,000/month
Lemma:                Fixed ~$150/month + negligible per-user

Savings: ~$1,850/month = $22,000/year
```

### 3.2.1 Cost Scaling: Users × Sites

#### Traditional Auth: Linear Cost Growth

Traditional auth costs scale **linearly** with both users AND authentication events:

```
Cost = (MAU × per_user_cost) + (auth_events × compute_cost)

Where:
- MAU grows with your user base
- Auth events = users × logins × session_checks × sites
```

**Auth0 Pricing at Scale:**

| MAU | Sites | Daily Auth Events | Monthly Cost | Cost/User |
|-----|-------|-------------------|--------------|-----------|
| 1,000 | 1 | 32,000 | $70 | $0.07 |
| 1,000 | 3 | 96,000 | $70 | $0.07 |
| 10,000 | 1 | 320,000 | $700 | $0.07 |
| 10,000 | 3 | 960,000 | $700+ | $0.07+ |
| 100,000 | 1 | 3.2M | $7,000 | $0.07 |
| 100,000 | 3 | 9.6M | $7,000+ | $0.07+ |
| 1,000,000 | 1 | 32M | $35,000+ | $0.035 |
| 1,000,000 | 3 | 96M | $35,000+ | $0.035+ |

*Note: Enterprise tiers may have volume discounts but require contracts*

#### Lemma: Fixed + Marginal Cost Growth

Lemma costs are **mostly fixed** because verification is local:

```
Cost = Fixed_Infrastructure + (Issuance_Events × marginal_cost)

Where:
- Fixed infrastructure: ~$100-300/month (server, DB, CDN)
- Issuance events: Only when NEW credentials are created
- Verification: $0 (100% local)
```

**Lemma Pricing at Scale:**

| MAU | Sites | Issuance Events* | Monthly Cost | Cost/User |
|-----|-------|------------------|--------------|-----------|
| 1,000 | 1 | 1,000 | ~$150 | $0.15 |
| 1,000 | 3 | 3,000 | ~$150 | $0.15 |
| 10,000 | 1 | 10,000 | ~$200 | $0.02 |
| 10,000 | 3 | 30,000 | ~$250 | $0.025 |
| 100,000 | 1 | 100,000 | ~$300 | $0.003 |
| 100,000 | 3 | 300,000 | ~$400 | $0.004 |
| 1,000,000 | 1 | 1,000,000 | ~$500 | $0.0005 |
| 1,000,000 | 3 | 3,000,000 | ~$800 | $0.0008 |

*Issuance = new credential per user per site (one-time, not per login)*

### 3.2.2 Cost Comparison Chart

```
Monthly Cost ($) vs MAU
                                                    
$40,000 ┤                                    ╭── Traditional (Auth0)
        │                               ╭────╯
$30,000 ┤                          ╭────╯
        │                     ╭────╯
$20,000 ┤                ╭────╯
        │           ╭────╯
$10,000 ┤      ╭────╯
        │ ╭────╯
        │╭╯    ════════════════════════════ Lemma (nearly flat)
   $500 ┼═══════════════════════════════════════════════════
        │
      0 ┼───────┬───────┬───────┬───────┬───────┬───────┬──▶
        0    100K    200K    400K    600K    800K    1M   MAU
```

### 3.2.3 Cost Scaling Formula

**Traditional Auth:**
```
Monthly_Cost = Base_Fee + (MAU × Per_User_Rate)

Example (Auth0 Professional):
- Base: $240/month
- Per MAU: $0.07 (after 500 free)
- 100K users: $240 + (99,500 × $0.07) = $7,205/month
```

**Lemma:**
```
Monthly_Cost = Infrastructure + (New_Credentials × DB_Cost)

Example:
- Infrastructure: $200/month (Heroku + Postgres)
- DB write cost: ~$0.0001 per credential
- 100K users × 3 sites: $200 + (300K × $0.0001) = $230/month
```

### 3.2.4 Multi-Site Cost Impact

The cost advantage grows dramatically with multiple sites:

| Scenario | Traditional | Lemma | Savings |
|----------|-------------|-------|---------|
| 10K users, 1 site | $700/mo | $200/mo | 3.5× |
| 10K users, 3 sites | $700/mo | $250/mo | 2.8× |
| 10K users, 10 sites | $700/mo | $350/mo | 2× |
| 100K users, 1 site | $7,000/mo | $300/mo | **23×** |
| 100K users, 3 sites | $7,000/mo | $400/mo | **17×** |
| 100K users, 10 sites | $7,000/mo | $600/mo | **12×** |
| 1M users, 1 site | $35,000/mo | $500/mo | **70×** |
| 1M users, 3 sites | $35,000/mo | $800/mo | **44×** |
| 1M users, 10 sites | $35,000/mo | $1,500/mo | **23×** |

**Why Lemma scales better:**
- Traditional: Charges per user regardless of auth events
- Lemma: Only charges for storage (credentials) and one-time issuance
- All verification is FREE (local crypto)

### 3.2.5 What You're Paying For

**Traditional Auth (recurring costs per user):**
```
┌────────────────────────────────────────────────────────┐
│  ✓ Token generation (every login)                      │
│  ✓ Token validation (every request)                    │
│  ✓ Token refresh (hourly)                              │
│  ✓ Session storage (Redis/DB)                          │
│  ✓ User profile storage                                │
│  ✓ MFA infrastructure                                  │
│  ✓ Auth server compute                                 │
│  ✓ Network egress                                      │
└────────────────────────────────────────────────────────┘
```

**Lemma (one-time costs per credential):**
```
┌────────────────────────────────────────────────────────┐
│  ✓ Credential signing (one-time per site)              │
│  ✓ Credential storage in DB (~1KB per cred)            │
│  ✓ Session cookie (negligible)                         │
│                                                        │
│  FREE (client-side):                                   │
│  ✗ All verification                                    │
│  ✗ All session checks                                  │
│  ✗ All permission checks                               │
│  ✗ Token refresh (no tokens!)                          │
└────────────────────────────────────────────────────────┘
```

### 3.2.6 Break-Even Analysis

At what scale does Lemma become cheaper?

```
Break-even point: ~500 MAU

Below 500 MAU:
- Auth0 free tier (7,000 MAU) may be cheaper
- Lemma fixed costs (~$150/mo) higher than $0

Above 500 MAU:
- Lemma: ~$150-200 fixed
- Auth0: 500 × $0.07 = $35 (but grows linearly)

At 5,000 MAU:
- Auth0: ~$350/month
- Lemma: ~$175/month
- Lemma wins by 2×

At 50,000 MAU:
- Auth0: ~$3,500/month
- Lemma: ~$250/month
- Lemma wins by 14×
```

### 3.3 Scalability Characteristics

| Metric | Traditional | Lemma |
|--------|-------------|-------|
| **Auth server load** | Linear with users | **Constant** (issuance only) |
| **Peak traffic handling** | Requires scaling | **No central bottleneck** |
| **Geographic latency** | CDN + auth server | **0ms** (local) |
| **Failure mode** | Auth outage = total outage | **Graceful degradation** |

---

## 4. Operational Characteristics

### 4.1 Availability Comparison

#### Traditional Auth: Single Point of Failure

```
If Auth0/Okta is down:
├── Cannot authenticate new users
├── Cannot refresh tokens (eventual session loss)
├── Cannot verify permissions
└── Total application outage for auth-protected features
```

**Historical Incidents:**
- Auth0 outage (2020): 4+ hours downtime
- Okta breach (2022): Trust concerns, security review required
- AWS Cognito (2021): Regional outages affected authentication

#### Lemma: Distributed Resilience

```
If Lemma.id is down:
├── ✅ Existing users can still authenticate (local passkey)
├── ✅ Existing credentials still verify (local Ed25519)
├── ✅ Sessions still valid (client-side storage)
├── ⚠️ Cannot issue NEW credentials
├── ⚠️ Revocation sync paused (1hr stale max)
└── Core functionality continues
```

### 4.2 Developer Experience

| Aspect | Traditional | Lemma |
|--------|-------------|-------|
| **Integration time** | 1-4 hours | 30 min - 2 hours |
| **SDK size** | 50-200KB | ~30KB |
| **Dependencies** | OAuth libs, JWT libs | None (native WebCrypto) |
| **Server-side code** | Required | **Optional** |
| **Testing** | Requires auth server | **Can test offline** |

### 4.3 Maintenance Burden

| Task | Traditional | Lemma |
|------|-------------|-------|
| **Token rotation** | Server-side logic | **Not needed** |
| **Secret management** | Critical | **Minimal** (public keys only) |
| **Session cleanup** | Cron jobs | **Client-side (auto)** |
| **Scaling auth servers** | Manual/auto-scale | **Not needed** |
| **Security patches** | Provider-dependent | **SDK updates only** |

---

## 5. Risk Assessment

### 5.1 Traditional Auth Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Provider breach | Medium | **Critical** | MFA, monitoring |
| Provider outage | Medium | High | Multi-provider |
| Token theft | Medium | High | Short expiry |
| Vendor lock-in | High | Medium | Abstraction layer |
| Price increases | High | Medium | Contract negotiation |

### 5.2 Lemma Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Local storage compromise (XSS) | Low | Medium | CSP, sanitization |
| Passkey device loss | Medium | Low | Recovery flow |
| Revocation sync lag | Medium | Low | Background sync |
| Browser compatibility | Low | Medium | Polyfills, fallbacks |
| New technology adoption | Medium | Low | Education, docs |

---

## 6. User Directory & Management

### 6.1 Lemma's User Management Options

Lemma.id provides **two deployment models**, giving developers flexibility:

#### Option A: Managed Service (Lemma hosts user directory)

```
POST /api/v1/sites/register/managed

Features:
├── ✅ User storage in Lemma database
├── ✅ Full user management APIs
├── ✅ Dashboard UI for user management
├── ✅ Credential issuance via Lemma API
└── ✅ Per-user billing
```

**API Endpoints:**
```
GET  /api/v1/sites/{site_id}/users              # List all users
POST /api/v1/sites/{site_id}/users/{did}/permissions  # Grant permission
GET  /api/v1/sites/{site_id}/verify             # Verify credential
POST /platform/users                            # Get platform users
```

#### Option B: Self-Service (Developer controls directory)

```
POST /api/v1/sites/register/self-service

Features:
├── ✅ Site generates own keypair (browser SDK)
├── ✅ Site manages own user database
├── ✅ Site issues credentials client-side
├── ✅ Lemma syncs for revocation/verification
└── ✅ Pay only for PoH verifications
```

**Developer fetches & syncs:**
```javascript
// Fetch user directory from Lemma
const response = await fetch('/api/platform/users', {
    method: 'POST',
    body: JSON.stringify({ user_credential: myAdminCredential })
});
const { users, site_id } = await response.json();

// Sync to your own database
await syncUsersToMyDB(users);
```

### 6.2 Comparison with Traditional Providers

| Capability | Auth0 | Okta | Lemma |
|------------|-------|------|-------|
| **Managed user directory** | ✅ | ✅ | ✅ |
| **Self-hosted option** | ❌ | ❌ | ✅ |
| **User list API** | ✅ | ✅ | ✅ |
| **Bulk user operations** | ✅ | ✅ | ✅ |
| **Admin dashboard** | ✅ | ✅ | ✅ |
| **Export users** | ✅ | ✅ | ✅ |
| **SCIM provisioning** | ✅ | ✅ | 🔜 (planned) |
| **LDAP sync** | ✅ | ✅ | ❌ |
| **AD integration** | ✅ | ✅ | ❌ |

**Key Difference:** Lemma offers a **hybrid model** where developers can:
1. Use Lemma's managed directory (like Auth0)
2. OR run their own directory and sync credentials
3. OR fully self-service with their own keys

---

## 7. When to Choose What

### Choose Traditional Auth (Auth0/Okta) When:

- ✅ Need rich enterprise integrations (SAML, LDAP, AD)
- ✅ Require compliance certifications (SOC 2 Type II, HIPAA)
- ✅ Want proven, battle-tested solution
- ✅ Team unfamiliar with WebAuthn/passkeys

### Choose Lemma When:

- ✅ Privacy is a core value (no tracking)
- ✅ Need offline-capable authentication
- ✅ Want to minimize operational costs at scale
- ✅ Building consumer applications
- ✅ Geographic distribution matters (latency)
- ✅ Want to avoid vendor lock-in
- ✅ Need cryptographically verifiable credentials

---

## 8. Conclusion

### Summary Scores (1-10)

| Category | Traditional | Lemma |
|----------|-------------|-------|
| **Security** | 7 | **9** |
| **Privacy** | 4 | **10** |
| **Cost Efficiency** | 5 | **9** |
| **Scalability** | 7 | **10** |
| **Availability** | 7 | **9** |
| **Maturity** | **9** | 6 |
| **Ecosystem** | **9** | 5 |

### Bottom Line

**Lemma provides superior security, privacy, and cost efficiency** for applications where:
- User privacy matters
- Offline capability is valuable
- Scale requires cost optimization
- Vendor independence is desired

**Traditional auth remains appropriate** for:
- Enterprise environments with existing IdP integrations
- Compliance-heavy industries requiring specific certifications
- Teams without resources to adopt new authentication paradigms
