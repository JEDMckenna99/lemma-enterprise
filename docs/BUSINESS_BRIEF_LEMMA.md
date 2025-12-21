# Lemma: Identity Verification That Scales

**Stop bots without scaling your infrastructure.**

---

## The Problem

Bots cost businesses money:
- **Account fraud**: Fake accounts abuse promotions, skew analytics, spam users
- **Credential stuffing**: Automated attacks test stolen passwords at scale
- **Scraping and abuse**: Bots extract data, manipulate pricing, exhaust inventory

Current defenses don't work:
| Defense | Why It Fails |
|---------|--------------|
| CAPTCHAs | Solved by human farms at $0.50/1000 |
| Fingerprinting | Spoofed by automation frameworks |
| Rate limiting | Circumvented by distributed attacks |
| IP blocking | Bypassed by proxy rotation |

The fundamental issue: **behavioral detection is an arms race**. Every defense requires continuous adaptation as attackers evolve.

---

## The Solution

**Lemma** shifts bot defense from behavior to identity.

Instead of asking "does this look like a bot?", Lemma asks "does this user have a valid credential from a verified human?"

Each user receives a **cryptographic credential** after verification. The credential:
- Proves the holder completed identity verification
- Can be verified **locally in microseconds** (no server calls)
- Cannot be shared or transferred between bot instances
- Can be revoked instantly across the entire network

---

## Why It's Different

### 1. Verification Without Server Calls

| Traditional Auth | Lemma |
|------------------|-------|
| Every check calls your server | Verification is local math |
| 50-200ms per verification | 50-100 microseconds |
| Server costs scale with users | Costs stay flat |
| Outage = auth down | Works offline |

### 2. Bot Economics Change

| Traditional Defense | Lemma |
|--------------------|-------|
| Attackers invest once, attack infinitely | Each bot needs unique verified credential |
| Defense requires continuous adaptation | Defense is structural, not reactive |
| Arms race favors attackers | Economics favor defenders |

### 3. Works at the Edge

Lemma credentials verify on any device without network connectivity:
- Package readers and logistics scanners
- Turnstiles and access control
- IoT devices and sensors
- Mobile apps in offline mode

---

## How It Works

```
1. User verifies identity once (email now, full KYC later)
           ↓
2. User receives cryptographic credential (stored locally)
           ↓
3. User presents credential to any participating site
           ↓
4. Site verifies locally (no server call, no Lemma dependency)
           ↓
5. If credential is revoked, update propagates to all sites
```

**You don't depend on Lemma for every verification.** Once you have the verification keys and revocation list, your systems work independently.

---

## Use Cases

### Bot Defense
Block automated abuse without CAPTCHAs. Each action requires a credential that bots can't mass-produce.

### Login/IAM
Replace password-based authentication with credential-based access. No session servers, no token refresh infrastructure.

### High-Throughput Verification
Package sorting, turnstiles, IoT devices - anywhere you need "is this authorized?" answered in microseconds without network calls.

### Cross-Site Trust
Accept credentials verified by partner sites. User verifies once, uses everywhere.

---

## Integration

**Simple JavaScript SDK:**

```javascript
// Check if user has valid credential
const result = await lemmaShield.verify();

if (result.valid) {
  // User is verified human - allow action
} else {
  // Redirect to verification or block
}
```

**Backend verification also available** for server-side decisions.

---

## Pricing

| Tier | Cost | Includes |
|------|------|----------|
| Starter | Free | Up to 1,000 verifications/month |
| Growth | $99/month | Up to 50,000 verifications/month |
| Scale | Custom | Unlimited + SLA + support |

No per-verification fees. Your costs don't grow with your users.

---

## Next Steps

1. **Try it**: Integrate the SDK on a test page in 30 minutes
2. **Measure**: Compare bot traffic before/after
3. **Scale**: Roll out to production

**Contact**: hello@lemma.id  
**Documentation**: https://lemma.id/docs  
**Demo**: https://lemma.id

---

*Lemma: Verify once, trust everywhere.*

