# 🚀 Final Deployment Checklist for Lemma Enterprise

## ✅ Current Status: READY FOR DEPLOYMENT
All tests are passing and core issues have been resolved.

## 🔴 CRITICAL: Deploy These Changes First

### 1. Deploy Updated Code
```bash
# Add and commit the fixes
git add .
git commit -m "Fix production dependencies and tests for deployment"
git push heroku main
```

### 2. Set Environment Variables in Heroku

Since you mentioned all variables are stored in Heroku, please verify these are set:

**Required for Core Functionality:**
```bash
# Verify these are set in your Heroku config
heroku config:get LEMMA_ADMIN_USER
heroku config:get LEMMA_ADMIN_PASS
heroku config:get LEMMA_SECRET_KEY
heroku config:get LEMMA_API_KEY

# Set Stripe TEST keys (to avoid costs during development/testing)
heroku config:set STRIPE_SECRET_KEY=sk_test_51RJNLBDIouMeOMablPrCc6aZzxvHYK2RDQcTAPFdBeeInO3Oo763Md4naHlIuD4f2fsw6TRgrN9AbAZbPym3KZrA00h5jdtmDA
heroku config:set STRIPE_PUBLISHABLE_KEY=pk_test_51RJNLBDIouMeOMab56ZoLLf7qyXOfw2dWq8dDnhihzcc9hOHhw2xqyvzEUXbfZDsYyAnZNa5ADkycRpqUvDzMr3G00CgiM8efu
```

**Required for Production Security:**
```bash
# Set these if not already configured
heroku config:set FLASK_ENV=production
heroku config:set DEBUG=false
heroku config:set LEMMA_FORCE_HTTPS=true
```

**OPRF Service Configuration:**
**Recommended - Disable OPRF for immediate deployment:**
```bash
heroku config:set LEMMA_ENABLE_OPRF=false
```

## 🟡 POST-DEPLOYMENT VERIFICATION

### 1. Check Application Health
```bash

curl https://lemma-enterprise.herokuapp.com/api/health
```
**Expected Response:**
```json
{
  "status": "ok",
  "service": "lemma-human-verification",
  "version": "1.0.0",
  "timestamp": 1640995200
}
```

### 2. Test CSRF Token Generation
```bash
curl https://lemma-enterprise.herokuapp.com/api/generate-csrf
```
**Expected Response:**
```json
{
  "csrf_token": "some-token-value"
}
```

### 3. Test Home Page
```bash

open https://lemma-enterprise.herokuapp.com
```
**Expected:** Home page loads without errors, shows "Verify Lemma" and "Access Protected Content" buttons.

### 4. Test Human Verification Flow (with Test Keys)
1. Click "Verify Lemma" button
2. **With Stripe test keys:** Should redirect to Stripe Identity verification (test mode)
3. **Test verification works but won't charge real money**

### 5. Check Heroku Logs
```bash
heroku logs --tail
```
**Expected:** No ERROR messages, INFO messages about Stripe test mode, no OPRF service errors.

## 🚨 TROUBLESHOOTING GUIDE


### Issue: "OPRF service connection failed"
**Solution:** Set `LEMMA_ENABLE_OPRF=false` (recommended for now).

### Issue: Application won't start
**Check:** 
1. All required environment variables are set
2. Heroku logs for specific error messages
3. No syntax errors in recent commits

## 🎯 CUSTOMER INTEGRATION TESTING

Once deployed, test these customer integration scenarios:

### 1. API Health Check
```bash
curl https://YOUR_APP_NAME.herokuapp.com/api/health
```

### 2. Credential Lookup (for customer sites)
```bash
curl https://YOUR_APP_NAME.herokuapp.com/api/credential-lookup/test_user_123
```

### 3. JavaScript Wallet Integration
Add these to a test customer site:
```html
<script src="https://YOUR_APP_NAME.herokuapp.com/static/js/lemma-wallet.js"></script>
<script src="https://YOUR_APP_NAME.herokuapp.com/static/js/lemma-wallet-init.js"></script>
```

## 📊 MONITORING SETUP

Set up monitoring for these endpoints:
- `GET /api/health` - Health checks
- `POST /api/verify-human` - Core verification
- `POST /api/verify-presentation` - Customer integrations
- `GET /api/credential-lookup/:user_id` - Customer lookups

## 🔒 SECURITY VERIFICATION

Confirm these security features are active:
- ✅ HTTPS enforcement
- ✅ CSRF protection
- ✅ Rate limiting
- ✅ Input validation
- ✅ Secure session handling

## 🎉 SUCCESS CRITERIA

Your software is production-ready when:
- ✅ Health endpoint returns 200 OK
- ✅ No critical errors in logs
- ✅ Home page loads correctly
- ✅ Stripe verification works (test mode)
- ✅ Customer integration APIs respond correctly
- ✅ All tests pass

## 📞 NEXT STEPS FOR CUSTOMER ONBOARDING

Once deployed, customers can integrate using:

1. **Health Check Integration:**
   ```
   GET https://YOUR_APP_NAME.herokuapp.com/api/health
   ```

2. **JavaScript Wallet Integration:**
   ```html
   <script src="https://YOUR_APP_NAME.herokuapp.com/static/js/lemma-wallet.js"></script>
   ```

3. **API Integration for Verification:**
   ```
   POST https://YOUR_APP_NAME.herokuapp.com/api/verify-human
   ```

## 🚀 DEPLOY NOW!

Execute these commands to deploy:

```bash
# 1. Deploy the code
git push heroku main

# 2. Set Stripe TEST keys (no cost)
heroku config:set STRIPE_SECRET_KEY=sk_test_YOUR_TEST_KEY
heroku config:set STRIPE_PUBLISHABLE_KEY=pk_test_YOUR_TEST_KEY

# 3. Set production security
heroku config:set FLASK_ENV=production DEBUG=false LEMMA_FORCE_HTTPS=true

# 4. Disable OPRF for immediate deployment
heroku config:set LEMMA_ENABLE_OPRF=false

# 5. Verify deployment
curl https://YOUR_APP_NAME.herokuapp.com/api/health

# 6. Check logs
heroku logs --tail
```

## 💰 COST-EFFECTIVE TESTING APPROACH

**Current Setup (Test Keys):**
- ✅ Full human verification flow works
- ✅ No charges for Stripe Identity verification
- ✅ Perfect for customer integration testing
- ✅ All APIs functional

**When Ready for Live Production:**
```bash
# Later, when you want to process real verifications:
heroku config:set STRIPE_SECRET_KEY=sk_live_YOUR_LIVE_KEY
heroku config:set STRIPE_PUBLISHABLE_KEY=pk_live_YOUR_LIVE_KEY
```

Your Lemma Enterprise software is now ready for customer site integration testing with no additional costs! 🎉 