# Stripe Billing Status for Lemma Shield Per-User Pricing

## Current Status: ⚠️ PARTIALLY IMPLEMENTED

The Stripe payment rails have been **partially set up** to handle your per-user pricing model ($0.10/user/month + $2 setup fee), but there are some limitations due to the current Stripe library version.

## ✅ What's Been Implemented

### 1. **Stripe Products Created**
- **Per-User Service**: `prod_SosqPFh2y10U2l` - For monthly per-user billing
- **Setup Fee Service**: `prod_SosqiMvANHprJ6` - For one-time setup fees

### 2. **Usage Billing API** (`api/usage_billing.py`)
- Cost estimation endpoint: `/api/billing/estimate`
- Customer creation endpoint: `/api/billing/create-customer`
- Invoice generation for setup fees and monthly usage
- Proper per-user cost calculations

### 3. **Updated Pricing Page**
- Interactive pricing calculator
- Integration with billing API
- "Start Protecting Your Site" button connects to billing system

### 4. **Flask Integration**
- New `usage_billing_bp` blueprint registered in `app.py`
- API endpoints available for frontend integration

## ⚠️ Current Limitations

### 1. **Stripe Library Version**
- **Current Version**: 6.7.0 (from requirements.txt)
- **Issue**: Newer Meter API for automated metered billing requires Stripe v8.0+
- **Workaround**: Manual invoice generation system implemented

### 2. **Manual Billing Process**
Instead of fully automated metered billing, the current system uses:
- Manual invoice creation for monthly usage
- Setup fee invoices for new users
- Cost estimation API for pricing calculator

### 3. **Missing Automated Features**
- Automatic monthly billing based on user count
- Real-time usage tracking via Stripe Meters
- Automated subscription management

## 🔧 What Needs to Be Done for Full Implementation

### Option 1: Upgrade Stripe Library (Recommended)
```bash
# Update requirements.txt
stripe>=8.0.0

# Then implement proper metered billing:
# - Create Stripe Meter for user tracking
# - Set up metered pricing with recurring billing
# - Implement usage event reporting
```

### Option 2: Keep Current Manual System
- Implement monthly billing job to generate invoices
- Add webhook handling for payment confirmations
- Create admin dashboard for usage tracking

## 🎯 Current User Experience

**For Customers:**
1. Visit pricing page at `/pricing`
2. Use calculator to estimate monthly costs
3. Click "Start Protecting Your Site" 
4. Get redirected to wallet with billing parameters
5. **Manual billing setup required** (not fully automated yet)

**For You:**
- API endpoints work for cost estimation
- Can manually create customers and invoices
- Need to implement recurring billing process

## 💰 Pricing Structure (Confirmed Working)

- **Monthly Cost**: $0.10 per verified user
- **Setup Fee**: $2.00 per new user (one-time)
- **Billing Method**: Monthly invoicing
- **Payment Processing**: Stripe (secure, PCI compliant)

## 📋 Next Steps

1. **Immediate**: Current system works for manual billing
2. **Short-term**: Upgrade Stripe library for automated metered billing
3. **Long-term**: Implement full subscription management dashboard

## 🚀 Bottom Line

**The pricing structure is correctly implemented** and the APIs work, but the billing process requires some manual intervention until we upgrade to the newer Stripe library version. The foundation is solid and can handle your per-user pricing model effectively.

**Customers can sign up and get accurate pricing estimates**, but you'll need to manually process the recurring monthly billing until the automation is fully implemented.