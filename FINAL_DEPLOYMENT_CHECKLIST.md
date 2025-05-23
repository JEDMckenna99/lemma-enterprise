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

### 2. Set Missing Environment Variables in Heroku

Since you mentioned all variables are stored in Heroku, please verify these are set:

**Required for Core Functionality:**
```bash
# Verify these are set in your Heroku config
heroku config:get STRIPE_SECRET_KEY        # Should be sk_live_... for production
heroku config:get STRIPE_PUBLISHABLE_KEY   # Should be pk_live_... for production
heroku config:get LEMMA_ADMIN_USER
heroku config:get LEMMA_ADMIN_PASS
heroku config:get LEMMA_SECRET_KEY
heroku config:get LEMMA_API_KEY
```

**Required for Production Security:**
```bash
# Set these if not already configured
heroku config:set FLASK_ENV=production
heroku config:set DEBUG=false
heroku config:set LEMMA_FORCE_HTTPS=true
```

**OPRF Service Configuration:**
Choose ONE of these options:

**Option A - Disable OPRF (Simpler, recommended for immediate deployment):**
```bash
heroku config:set LEMMA_ENABLE_OPRF=false
```

**Option B - Deploy OPRF Service (More complete, but requires additional setup):**
```bash
heroku config:set OPRF_SERVICE_URL=https://your-oprf-service.herokuapp.com
# Note: You'll need to deploy the oprfservice separately
```

## 🟡 POST-DEPLOYMENT VERIFICATION

### 1. Check Application Health
```bash
# Replace YOUR_APP_NAME with your actual Heroku app name
curl https://YOUR_APP_NAME.herokuapp.com/api/health
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
curl https://YOUR_APP_NAME.herokuapp.com/api/generate-csrf
```
**Expected Response:**
```json
{
  "csrf_token": "some-token-value"
}
```

### 3. Test Home Page
```bash
# Visit in browser
open https://YOUR_APP_NAME.herokuapp.com
```
**Expected:** Home page loads without errors, shows "Verify Lemma" and "Access Protected Content" buttons.

### 4. Test Human Verification Flow
1. Click "Verify Lemma" button
2. **If Stripe is configured:** Should redirect to Stripe Identity verification
3. **If Stripe not configured:** Should show error about Stripe configuration

### 5. Check Heroku Logs
```bash
heroku logs --tail
```
**Expected:** No ERROR messages, only INFO and WARNING messages about missing optional services.

## 🚨 TROUBLESHOOTING GUIDE

### Issue: "Stripe API key not configured"
**Solution:**
```bash
heroku config:set STRIPE_SECRET_KEY=sk_live_YOUR_LIVE_KEY
heroku config:set STRIPE_PUBLISHABLE_KEY=pk_live_YOUR_LIVE_KEY
```

### Issue: "pyristretto255 not available"
**Solution:** This is fixed in the updated code. Deploy the latest version.

### Issue: "OPRF service connection failed"
**Solution:** Set `LEMMA_ENABLE_OPRF=false` unless you need revocation features.

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
- ✅ Stripe verification works (if configured)
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

# 2. Set production security (if not already set)
heroku config:set FLASK_ENV=production DEBUG=false LEMMA_FORCE_HTTPS=true

# 3. Disable OPRF for immediate deployment (recommended)
heroku config:set LEMMA_ENABLE_OPRF=false

# 4. Verify deployment
curl https://YOUR_APP_NAME.herokuapp.com/api/health

# 5. Check logs
heroku logs --tail
```

Your Lemma Enterprise software is now ready for customer site integration! 🎉 