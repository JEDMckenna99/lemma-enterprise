# Stripe Identity Billing Integration for Lemma Shield

## 🎯 Correct Billing Model

The Lemma Shield billing system now properly distinguishes between:

1. **Monthly Active Users (MAU)**: $0.10 per user per month
2. **Stripe Identity Verifications**: $2.00 per verification (only when required)

## 🔍 Key Distinction

### ❌ Old Understanding (Incorrect):
- Every new user pays $2.00 setup fee
- All users who visit the site for the first time get charged

### ✅ New Understanding (Correct):
- **$0.10/month**: Charged for each user who visits your site in a given month
- **$2.00 one-time**: Only charged when a user completes **Stripe Identity verification**

## 🛠 How Stripe Identity Verification Works

### When Stripe Identity is Required:
- High-risk transactions
- Enhanced KYC compliance
- Age verification
- Identity document validation
- Regulatory compliance requirements

### When Stripe Identity is NOT Required:
- Regular website visits
- Basic bot protection
- Standard user verification
- Low-risk interactions

## 📊 Billing Examples

### Example 1: Regular E-commerce Site
```
Month 1:
- 1000 users visit site → $100.00 (1000 × $0.10 MAU)
- 50 users complete Stripe Identity for high-value purchases → $100.00 (50 × $2.00)
- Total: $200.00

Month 2:
- 800 users visit site (600 returning, 200 new) → $80.00 (800 × $0.10 MAU)
- 20 new users complete Stripe Identity → $40.00 (20 × $2.00)
- Total: $120.00
```

### Example 2: Basic Content Site
```
Month 1:
- 5000 users visit site → $500.00 (5000 × $0.10 MAU)
- 0 users need Stripe Identity → $0.00
- Total: $500.00

Month 2:
- 4200 users visit site → $420.00 (4200 × $0.10 MAU)
- 0 users need Stripe Identity → $0.00
- Total: $420.00
```

## 🔧 Integration Guide

### 1. Track Regular User Activity (MAU)
```python
from api.mau_tracker import track_user_activity

# When user visits any page with Lemma Shield
track_user_activity(
    customer_id="cus_stripe_customer_id",
    user_id="user@example.com",
    stripe_identity_verified=False  # Just visiting, no identity verification
)
```

### 2. Track Stripe Identity Verification
```python
from api.mau_tracker import track_stripe_identity_verification

# When user completes Stripe Identity verification
track_stripe_identity_verification(
    customer_id="cus_stripe_customer_id",
    user_id="user@example.com"
)

# OR use the combined function
track_user_activity(
    customer_id="cus_stripe_customer_id",
    user_id="user@example.com",
    stripe_identity_verified=True  # User completed Stripe Identity
)
```

### 3. API Endpoints

#### Track Regular Activity
```bash
POST /api/mau/track
{
  "customer_id": "cus_stripe_customer_id",
  "user_id": "user@example.com",
  "stripe_identity_verified": false
}
```

#### Track Stripe Identity Verification
```bash
POST /api/mau/track/stripe-identity
{
  "customer_id": "cus_stripe_customer_id",
  "user_id": "user@example.com"
}
```

#### Get Billing Data
```bash
GET /api/mau/billing/cus_customer_id?month=2024-01
```

**Response:**
```json
{
  "success": true,
  "billing_data": {
    "customer_id": "cus_customer_id",
    "month": "2024-01",
    "mau_count": 1250,
    "mau_cost": 125.00,
    "stripe_identity_count": 75,
    "stripe_identity_cost": 150.00,
    "total_monthly_cost": 275.00,
    "billing_breakdown": {
      "mau_billing": "1250 users × $0.10 = $125.00",
      "identity_billing": "75 verifications × $2.00 = $150.00",
      "total": "$275.00"
    }
  }
}
```

## 🎛 Customer Dashboard Integration

### Billing Breakdown Display
```javascript
// Display billing information to customers
fetch('/api/mau/billing/cus_customer_id')
  .then(response => response.json())
  .then(data => {
    const billing = data.billing_data;
    console.log(`MAU: ${billing.mau_count} users = $${billing.mau_cost}`);
    console.log(`Identity: ${billing.stripe_identity_count} verifications = $${billing.stripe_identity_cost}`);
    console.log(`Total: $${billing.total_monthly_cost}`);
  });
```

## 🔒 Privacy & Security

### Salted User Tracking
Both MAU and Stripe Identity tracking use the same privacy-preserving salted identifiers:

```python
# Same user gets consistent hash across both tracking types
salted_id = create_salted_user_id("cus_customer", "user@example.com")
# → "salted_a1b2c3d4e5f6789a"

# Used for both:
# 1. MAU tracking (monthly visits)
# 2. Stripe Identity tracking (verification events)
```

## 📈 Analytics & Reporting

### Monthly Report Example
```json
{
  "customer_id": "cus_customer_id",
  "month": "2024-01",
  "summary": {
    "total_monthly_active_users": 1250,
    "stripe_identity_verifications": 75,
    "mau_cost": 125.00,
    "identity_cost": 150.00,
    "total_cost": 275.00
  },
  "breakdown": {
    "mau_percentage": 45.5,
    "identity_percentage": 54.5,
    "average_cost_per_user": 0.22
  }
}
```

## 🚀 Deployment Checklist

### For Existing Customers:
- [ ] Update tracking calls to specify `stripe_identity_verified=False` for regular visits
- [ ] Add `stripe_identity_verified=True` calls when Stripe Identity completes
- [ ] Test billing data accuracy with new breakdown
- [ ] Update customer dashboards to show separate line items

### For New Integrations:
- [ ] Implement MAU tracking on all protected pages
- [ ] Implement Stripe Identity tracking on verification completion
- [ ] Set up monthly billing automation
- [ ] Configure customer analytics dashboard

## 🎯 Key Benefits

✅ **Fair Billing**: Customers only pay for actual usage  
✅ **Transparent Costs**: Clear breakdown of MAU vs Identity fees  
✅ **Flexible Implementation**: Not all users need Stripe Identity  
✅ **Cost Optimization**: Most customers will have low Identity verification rates  
✅ **Compliance Ready**: Stripe Identity available when needed  

## 📋 Next Steps

1. **Update Integration Code**: Add Stripe Identity tracking calls
2. **Test Billing Accuracy**: Verify correct fee calculation
3. **Deploy Changes**: Roll out updated tracking system
4. **Monitor Usage**: Track MAU vs Identity verification rates
5. **Customer Communication**: Explain new billing model benefits

## 💡 Cost Optimization Tips for Customers

### Minimize Stripe Identity Usage:
- Only require for high-risk transactions
- Use for regulatory compliance only when needed
- Consider risk-based triggers
- Implement progressive verification (basic → enhanced)

### Example Implementation:
```javascript
// Basic verification for most users (MAU only)
if (transactionAmount < 100) {
  await lemmaShield.basicVerify(user);
  // Only MAU charge: $0.10/month
}

// Enhanced verification for high-value transactions
if (transactionAmount >= 100) {
  await lemmaShield.stripeIdentityVerify(user);
  // MAU + Identity charge: $0.10/month + $2.00 one-time
}
```

This approach ensures customers get the most cost-effective verification for their specific use case!