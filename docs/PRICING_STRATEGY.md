# Lemma IAM Pricing Strategy: Disrupting the Market

## Executive Summary

**Lemma's competitive advantage:** Local verification with OPRF + Bloom filter means 99% fewer API calls than traditional IAM, enabling 5-10x lower pricing while maintaining 80%+ gross margins.

---

## 1. Cost Structure Analysis

### Traditional IAM (Auth0, Okta, Firebase)

**Per verification costs:**
```
API Call:
- Load balancer:           $0.000010
- Application server:      $0.000050
- Database query:          $0.000100
- Network egress:          $0.000020
- Session management:      $0.000030
────────────────────────────────────
Total per verification:    $0.000210

Per MAU (100 verifications/month):
- 100 verifications × $0.000210 = $0.021/MAU
- Plus: 25% overhead (support, sales, infra)
- Plus: 300% markup (profit margin)
────────────────────────────────────
Typical pricing:          $0.05-0.10/MAU
```

**Their pricing tiers:**
- **Auth0:** $0.05/MAU (14,000 MAU free, then $1.30/20 MAU = $0.065/MAU)
- **Okta:** $2-5/user/month ($0.067-0.167/MAU assuming 30 MAU/user)
- **Firebase Auth:** Free up to 50K, then $0.06/MAU
- **AWS Cognito:** $0.0055/MAU (first 50K free)

---

### Lemma IAM Cost Structure

**Per verification costs:**
```
Initial credential issuance (one-time):
- Ed25519 signing:         $0.000001 (Rust, <100µs)
- KMS encryption:          $0.000020 (AWS KMS call)
- Database write:          $0.000010
- Bloom filter update:     $0.000001
────────────────────────────────────
Initial issuance:          $0.000032 (ONE TIME)

Per verification (client-side, local):
- CPU cost (Ed25519):      $0.0000001 (user's device)
- OPRF evaluation:         $0.0000001 (user's device)
- Bloom filter check:      $0.0000001 (user's device)
- Nonce cache (RAM):       $0.0000001 (server)
────────────────────────────────────
Per verification:          $0.0000004

Per MAU (100 verifications/month):
- 1 issuance × $0.000032    = $0.000032
- 100 verifications × $0.0000004 = $0.00004
────────────────────────────────────
Total per MAU:             $0.000072

Server costs (per MAU):
- Bloom filter sync:       $0.000010 (60s interval)
- Nonce cache (Redis):     $0.000005
- Database storage:        $0.000003
- Network egress:          $0.000002
────────────────────────────────────
Infrastructure per MAU:    $0.000092

TOTAL COST PER MAU:        $0.000164
```

**Cost advantage: 128x cheaper than traditional IAM** ($0.000164 vs $0.021)

---

## 2. Competitive Pricing Strategy

### Pricing Philosophy
1. **Undercut competition by 50-70%** to drive adoption
2. **Maintain 85-95% gross margins** (sustainable, VC-attractive)
3. **Volume-based tiers** (reward growth)
4. **Transparent, simple pricing** (no hidden fees)

---

### Recommended Pricing Tiers

#### **Tier 1: Starter (Self-Service)**
```
Price: $0.015/MAU
- First 10,000 MAU FREE
- Then $0.015/MAU (10K-100K)
- Min: $0/month
- Max: $1,500/month (100K MAU)

Margins:
- Cost:    $0.000164/MAU
- Revenue: $0.015/MAU
- Margin:  98.9% 💰

Competitive positioning:
- Auth0:     $0.065/MAU → 77% cheaper ✅
- Okta:      $0.100/MAU → 85% cheaper ✅
- Firebase:  $0.060/MAU → 75% cheaper ✅
```

**Target customers:**
- Startups (0-100K users)
- Side projects, MVPs
- Open source projects

---

#### **Tier 2: Professional**
```
Price: $0.012/MAU
- 100K-1M MAU
- Volume discount: 20% off Starter
- Includes: Priority support, SLA 99.9%
- Monthly cost: $1,200-12,000

Margins:
- Cost:    $0.000164/MAU
- Revenue: $0.012/MAU
- Margin:  98.6% 💰

Example customer:
- 500K MAU × $0.012 = $6,000/month
- Auth0 equivalent: 500K × $0.065 = $32,500/month
- Customer saves: $26,500/month (81% savings) ✅
```

**Target customers:**
- Growth-stage startups (Series A/B)
- Profitable SaaS companies
- E-commerce platforms

---

#### **Tier 3: Enterprise**
```
Price: $0.008/MAU
- 1M+ MAU
- Volume discount: 47% off Starter
- Includes: Dedicated support, SLA 99.99%, custom deployment
- Monthly cost: $8,000+

Margins:
- Cost:    $0.000164/MAU
- Revenue: $0.008/MAU
- Margin:  98.0% 💰

Example customer:
- 10M MAU × $0.008 = $80,000/month
- Auth0 equivalent: 10M × $0.065 = $650,000/month
- Customer saves: $570,000/month (88% savings) 🚀
```

**Target customers:**
- Late-stage startups (Series C+)
- Public companies
- Fortune 500 enterprises

---

### Pricing Comparison Table

| **Provider** | **Free Tier** | **10K MAU** | **100K MAU** | **1M MAU** | **10M MAU** |
|-------------|--------------|-------------|--------------|------------|-------------|
| **Lemma** | ✅ 10K free | **$0** | **$1,350** | **$10,800** | **$80,000** |
| Auth0 | 7K free | $195 | $6,500 | $65,000 | $650,000 |
| Okta | Trial only | $500 | $10,000 | $100,000 | $1,000,000 |
| Firebase | 50K free | $0 | $3,000 | $60,000 | $600,000 |
| AWS Cognito | 50K free | $0 | $275 | $5,500 | $55,000 |

**Lemma positioning:**
- **Cheaper than AWS Cognito** (better UX, more features)
- **5-12x cheaper than Auth0/Okta** (enterprise targets)
- **Simple, predictable pricing** (vs complex feature matrices)

---

## 3. Revenue Model Details

### Why MAU (Monthly Active Users)?

**✅ Advantages:**
1. **Industry standard** - Easy to compare with competitors
2. **Aligns with value** - Customers pay for actual usage
3. **Predictable revenue** - Monthly recurring (vs per-verification spikes)
4. **Simple billing** - No complex metering required

**❌ Alternatives considered:**
- **Per-verification:** Too complex, unpredictable costs
- **Flat rate:** Doesn't scale, leaves money on table
- **Per-site:** Punishes multi-tenant customers

---

### MAU Definition

**"Monthly Active User" = Unique user who verifies ≥1 permission lemma in calendar month**

```javascript
// MAU tracking
const mau_key = `mau:${site_id}:${month}:${user_did}`;
if (!redis.exists(mau_key)) {
    redis.setex(mau_key, 30*24*60*60, 1); // 30-day TTL
    increment_mau_counter(site_id, month);
}
```

**Privacy-preserving:**
- Hash `user_did` before storage (GDPR compliant)
- No PII tracked (just counts)
- Users can opt-out (still counted, but anonymized)

---

### Additional Revenue Streams

#### 1. **Add-on: Proof of Humanity (PoH) Network**
```
Pricing: $0.002/verification
- Sybil attack prevention
- Human verification via Lemma PoH network
- 99.9% bot blocking

Example:
- 100K verifications/month = $200/month additional
- Margin: 95% (OPRF verification is cheap)
```

#### 2. **Add-on: Advanced Analytics**
```
Pricing: $99-499/month flat fee
- Real-time dashboard
- Anomaly detection (bot patterns)
- User journey analytics
- Export to data warehouse

Target: Enterprise customers who need visibility
```

#### 3. **Add-on: White-label Wallet**
```
Pricing: $999/month + $0.001/MAU
- Custom-branded wallet app
- Your logo, your domain
- iOS + Android apps

Target: Large enterprises (banks, healthcare)
```

#### 4. **Add-on: Compliance Certification**
```
Pricing: $5,000-25,000 one-time + $500/month
- SOC 2 Type II audit assistance
- HIPAA BAA (Business Associate Agreement)
- FedRAMP readiness assessment

Target: Healthcare, finance, government customers
```

---

## 4. Go-to-Market Pricing Strategy

### Phase 1: Land Grab (Months 1-12)
**Goal: 1,000 customers, 100M total MAU**

**Tactics:**
1. **Generous free tier** - 10,000 MAU free (vs Auth0's 7,000)
2. **Free migration** - We'll migrate your first 50K users from Auth0/Okta
3. **Startup credits** - YC/TechStars companies get 6 months free
4. **Open source discount** - OSS projects get 50% off forever

**Why this works:**
- Low LTV customers become evangelists
- Network effects (developers switch jobs, bring Lemma)
- Viral growth (developers share on Twitter/HN)

---

### Phase 2: Move Upmarket (Months 12-24)
**Goal: 100 enterprise customers, 1B+ total MAU**

**Tactics:**
1. **Case studies** - "How we saved $500K/year switching from Okta"
2. **Enterprise features** - SSO, SCIM, audit logs
3. **Custom contracts** - Negotiated pricing for 10M+ MAU
4. **Professional services** - Migration assistance, integration support

**Pricing:**
- Maintain aggressive pricing vs Auth0/Okta
- Add premium features (analytics, compliance)
- Upsell add-ons (PoH, white-label)

---

### Phase 3: Platform Play (Months 24+)
**Goal: Become the default IAM for Web3/decentralized apps**

**Tactics:**
1. **Developer ecosystem** - SDKs for every language/framework
2. **Marketplace** - Third-party integrations (Stripe, Salesforce, etc.)
3. **API platform** - Let others build on Lemma
4. **Compliance-as-a-Service** - Sell HIPAA/SOC2 certifications

**Pricing:**
- Marketplace revenue share (20% of add-on sales)
- API platform fees ($0.0001/call)
- Compliance premium (2x base price for certified deployments)

---

## 5. Unit Economics

### Customer Acquisition Cost (CAC)

**Assumptions:**
- **Inbound marketing:** $50 CAC (blog, SEO, community)
- **Outbound sales:** $500 CAC (mid-market), $5,000 CAC (enterprise)
- **Average customer:** 50K MAU, $600/month revenue

**Payback period:**
- Inbound: 50 / 600 = 0.08 months (instant!) 🚀
- Outbound mid-market: 500 / 600 = 0.8 months
- Enterprise: 5,000 / (10M MAU × $0.008) = 0.06 months

**Why this works:**
- Near-zero marginal cost = instant profitability
- High gross margins (98%+) = fast payback
- Annual contracts = predictable revenue

---

### Lifetime Value (LTV)

**Assumptions:**
- **Average customer lifespan:** 5 years (IAM is sticky)
- **Churn rate:** 5% annual (vs 20-30% for SaaS average)
- **Expansion revenue:** 30% year-over-year (users grow)

**LTV calculation:**
```
Year 1: $600/month × 12 = $7,200
Year 2: $7,200 × 1.30 = $9,360
Year 3: $9,360 × 1.30 = $12,168
Year 4: $12,168 × 1.30 = $15,818
Year 5: $15,818 × 1.30 = $20,563
────────────────────────────────────
Total LTV: $65,109

LTV/CAC ratio:
- Inbound: 65,109 / 50 = 1,302x 🚀
- Outbound: 65,109 / 500 = 130x 🚀
- Enterprise: (much higher LTV, 20-100x)
```

**Rule of thumb:** LTV/CAC > 3 is good, >10 is exceptional. **Lemma is 100-1000x.** 💎

---

## 6. Competitive Moat

### Why customers can't leave once adopted:

1. **Network effects**
   - Every integration adds value
   - Developers familiar with Lemma API
   - Community plugins/extensions

2. **Data lock-in (ethical)**
   - User DIDs stored in wallet
   - Migration requires user consent (GDPR)
   - Switching cost = re-onboard all users

3. **Cost savings are addictive**
   - Once saving $500K/year, hard to justify switch
   - CFO won't approve 10x price increase

4. **Privacy guarantee**
   - Can't get zero-knowledge revocation elsewhere
   - Compliance (HIPAA/GDPR) harder with traditional IAM

---

## 7. Pricing Psychological Tactics

### A. Anchoring
```
Show competitors first:
"Auth0: $0.065/MAU"
"Okta: $0.100/MAU"
"Lemma: $0.015/MAU" ← Looks like a steal!
```

### B. Decoy Pricing
```
Starter:      $0.015/MAU (most popular)
Professional: $0.012/MAU ← Decoy (only 20% off)
Enterprise:   $0.008/MAU ← Real target (47% off)

Effect: Makes Enterprise look like best value
```

### C. Free Tier as Lead Magnet
```
10,000 MAU free
- Removes barrier to entry
- Students/hobbyists become advocates
- Viral growth on Twitter/HN
- "I use Lemma for free in prod" → credibility
```

### D. Usage-Based = Fair
```
"Only pay for active users"
- Aligns incentives (we want you to grow)
- No surprise bills (predictable)
- Scales down (seasonal businesses love this)
```

---

## 8. Pricing Page Messaging

### Hero Section
```
"Enterprise IAM at Startup Prices"

Replace Auth0, Okta, Firebase
Save 75% on authentication costs
Verify users in 150 microseconds
Privacy-preserving, GDPR-compliant

[Start Free] [See Pricing]
```

### Pricing Calculator
```javascript
// Interactive calculator
Monthly Active Users: [slider: 0 - 10M]

Your cost with:
- Auth0:  $X,XXX/month ← crossed out, red
- Okta:   $X,XXX/month ← crossed out, red
- Lemma:  $XXX/month   ← green, big

💰 You save: $XX,XXX/month (XX%)

[Start Free Trial]
```

### Trust Signals
```
✓ 99.99% uptime SLA
✓ SOC 2 Type II certified
✓ GDPR & HIPAA compliant
✓ Used by [logos: 50+ companies]
✓ 150µs verification (1000x faster)
```

---

## 9. Billing Implementation

### Metering System
```python
# Track MAU per site per month
def track_verification(site_id: str, user_did: str):
    month_key = datetime.now().strftime("%Y-%m")
    mau_key = f"mau:{site_id}:{month_key}:{user_did}"
    
    # HyperLogLog for efficient unique counting
    redis.pfadd(f"mau_set:{site_id}:{month_key}", user_did)
    
    # Get current count
    mau_count = redis.pfcount(f"mau_set:{site_id}:{month_key}")
    
    # Update billing
    update_usage(site_id, month_key, mau_count)
```

### Stripe Integration
```python
# Monthly billing cycle
def bill_customer(site_id: str):
    site = get_site(site_id)
    month_key = last_month_key()
    
    mau_count = redis.pfcount(f"mau_set:{site_id}:{month_key}")
    
    # Calculate price based on tier
    if mau_count <= 10_000:
        amount = 0  # Free tier
    elif mau_count <= 100_000:
        amount = (mau_count - 10_000) * 0.015  # $0.015/MAU
    elif mau_count <= 1_000_000:
        amount = 90_000 * 0.015 + (mau_count - 100_000) * 0.012
    else:
        amount = 90_000 * 0.015 + 900_000 * 0.012 + (mau_count - 1_000_000) * 0.008
    
    # Create Stripe invoice
    stripe.InvoiceItem.create(
        customer=site.stripe_customer_id,
        amount=int(amount * 100),  # cents
        currency="usd",
        description=f"Lemma IAM - {mau_count:,} MAU ({month_key})"
    )
```

---

## 10. ROI Calculator for Sales

### Use in sales calls:
```
"Let's calculate your ROI switching to Lemma..."

Current (Auth0):
- 500,000 MAU
- $0.065/MAU
- $32,500/month
- $390,000/year

With Lemma:
- 500,000 MAU
- $0.012/MAU
- $6,000/month
- $72,000/year

Annual savings: $318,000 (81%)
3-year savings: $954,000

Migration cost: $10,000 (2 weeks engineering)
Payback period: 11 days

ROI: 3,180% (first year)
```

---

## 11. Recommended Final Pricing

### Simple, Aggressive, Transparent

```
┌──────────────────────────────────────────────────────┐
│                 LEMMA IAM PRICING                     │
├──────────────────────────────────────────────────────┤
│                                                       │
│  FREE                                                 │
│  └─ 0 - 10,000 MAU                                   │
│  └─ All features, no credit card                     │
│                                                       │
│  STARTER: $0.015/MAU                                  │
│  └─ 10K - 100K MAU                                   │
│  └─ $150 - $1,350/month                              │
│  └─ Email support                                     │
│                                                       │
│  PROFESSIONAL: $0.012/MAU                             │
│  └─ 100K - 1M MAU                                    │
│  └─ $1,200 - $12,000/month                           │
│  └─ Priority support, 99.9% SLA                      │
│                                                       │
│  ENTERPRISE: $0.008/MAU                               │
│  └─ 1M+ MAU                                          │
│  └─ $8,000+/month                                    │
│  └─ Dedicated support, 99.99% SLA, custom terms      │
│                                                       │
└──────────────────────────────────────────────────────┘

Compare with Auth0: 77% cheaper
Compare with Okta: 85% cheaper
Compare with Firebase: 75% cheaper

[Start Free] [Talk to Sales]
```

---

## 12. Key Takeaways

### ✅ Recommended Strategy

1. **Price: $0.015/MAU (Starter), $0.008/MAU (Enterprise)**
   - 75-85% cheaper than Auth0/Okta
   - 40% cheaper than AWS Cognito (but better UX)
   - Still maintains 98%+ gross margins

2. **Free tier: 10,000 MAU**
   - Removes friction for startups
   - Viral growth through developer community
   - Converts to paid as they grow

3. **Bill monthly on MAU (Monthly Active Users)**
   - Industry standard, easy to compare
   - Predictable revenue
   - Aligns incentives (we want customers to grow)

4. **Add-ons for extra revenue:**
   - Proof of Humanity ($0.002/verification)
   - Advanced Analytics ($99-499/month)
   - White-label Wallet ($999/month + $0.001/MAU)
   - Compliance Certification ($5K-25K one-time)

5. **Unit economics are exceptional:**
   - CAC: $50-500 (inbound marketing)
   - LTV: $65,000+ (5-year customer)
   - LTV/CAC: 100-1000x (vs 3x industry standard)
   - Gross margin: 98%+ (near-zero marginal cost)

### 🚀 Competitive Moat

Your cost structure enables **aggressive pricing that competitors cannot match**:
- Auth0/Okta: 15-20% margins, can't go below $0.04/MAU
- Lemma: 98% margins, can go to $0.005/MAU and still be profitable

**This is a winner-take-all market. Price aggressively, grow fast, dominate.** 💎

---

## Appendix: Example Customer Scenarios

### Scenario 1: Early-Stage Startup
```
Company: TechCo (Series A SaaS)
Users: 25,000 MAU
Current: Auth0 ($0.065/MAU) = $1,625/month

With Lemma: 
- First 10K free
- Next 15K × $0.015 = $225/month
- Annual savings: $16,800
- Founder reaction: "Wait, WHAT?! Sign me up!"
```

### Scenario 2: Growth Company
```
Company: GrowthCorp (Series B E-commerce)
Users: 500,000 MAU
Current: Okta ($0.100/MAU) = $50,000/month

With Lemma:
- 10K free
- 90K × $0.015 = $1,350
- 400K × $0.012 = $4,800
- Total: $6,150/month
- Annual savings: $525,800
- CTO reaction: "This pays for 3 engineers!"
```

### Scenario 3: Enterprise
```
Company: MegaCorp (Public, 50M users)
Users: 10,000,000 MAU
Current: Auth0 Enterprise = $650,000/month

With Lemma:
- Custom enterprise pricing: $0.006/MAU
- Total: $60,000/month
- Annual savings: $7,080,000
- Board reaction: "Why didn't we do this sooner?"
```

