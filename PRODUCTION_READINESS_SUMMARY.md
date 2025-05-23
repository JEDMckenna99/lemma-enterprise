# Lemma Enterprise Production Readiness Issues

## 🔴 CRITICAL ISSUES - Must Fix Before Production

### 1. Missing Production Dependencies ⚠️
**Issue:** Critical production cryptography package is missing
```bash
# Add to requirements.txt:
pyristretto255==1.3.3
```
**Current Impact:** System is using mock cryptography instead of production-grade OPRF
**Log Evidence:**
```
WARNING:lemma.core.cascaded_bloom:pyristretto255 not available, using mock implementation
```

### 2. OPRF Service Not Running ⚠️
**Issue:** OPRF revocation service is not deployed/running
**Current Impact:** Credential revocation system is completely non-functional
**Log Evidence:**
```
ERROR:lemma.core.cascaded_bloom:Failed to get OPRF public key: HTTPConnectionPool(host='localhost', port=8080): Max retries exceeded
```

**Required Actions:**
- Deploy the OPRF service (from `oprfservice/` directory)
- Set environment variable: `OPRF_SERVICE_URL=https://your-oprf-service.herokuapp.com`
- OR disable OPRF if not needed: `LEMMA_ENABLE_OPRF=false`

### 3. Stripe Identity Not Configured ⚠️
**Issue:** Human verification system is non-functional
**Current Impact:** Cannot verify humans - core feature is broken
**Log Evidence:**
```
WARNING:lemma:Stripe API key not configured, Identity verification will be unavailable
```

**Required Actions:**
In Heroku, set:
```bash
heroku config:set STRIPE_SECRET_KEY=sk_live_...  # Your live Stripe key
heroku config:set STRIPE_PUBLISHABLE_KEY=pk_live_...  # Your live publishable key
```

### 4. Test Failures ✅ FIXED
The API key validation tests were failing but have been fixed.

## 🟡 IMPORTANT ISSUES - Should Fix Before Production

### 5. Development Server Warning
**Issue:** Application is running in development mode
**Log Evidence:**
```
WARNING: This is a development server. Do not use it in a production deployment.
```

**Solution:** This is normal for local testing, but Heroku will use gunicorn in production.

### 6. Missing HTTPS Enforcement
**Solution:** Add to Heroku config:
```bash
heroku config:set LEMMA_FORCE_HTTPS=true
```

### 7. Debug Mode Enabled
**Solution:** Add to Heroku config:
```bash
heroku config:set FLASK_ENV=production
heroku config:set DEBUG=false
```

## 🟢 RECOMMENDED IMPROVEMENTS

### 8. Add Production Monitoring
**Recommendation:** Set up monitoring for:
- Health endpoint: `/api/health`
- Error rates and response times
- Uptime monitoring

### 9. External Storage for Keys
**Recommendation:** Configure external key storage for Heroku:
```bash
heroku config:set LEMMA_EXTERNAL_STORAGE_URL=s3://your-bucket/keys.json
heroku config:set AWS_ACCESS_KEY_ID=your_access_key
heroku config:set AWS_SECRET_ACCESS_KEY=your_secret_key
```

## IMMEDIATE ACTION PLAN

### Step 1: Fix Critical Dependencies
```bash
# Add pyristretto255 to requirements.txt
echo "pyristretto255==1.3.3" >> requirements.txt

# Deploy to Heroku
git add .
git commit -m "Add production cryptography dependency"
git push heroku main
```

### Step 2: Configure Stripe
```bash
heroku config:set STRIPE_SECRET_KEY=sk_live_YOUR_LIVE_KEY_HERE
heroku config:set STRIPE_PUBLISHABLE_KEY=pk_live_YOUR_LIVE_KEY_HERE
```

### Step 3: Deploy OPRF Service OR Disable It
**Option A - Deploy OPRF Service:**
```bash
# Deploy the oprfservice to a separate Heroku app
cd oprfservice/
heroku create your-oprf-service
git push heroku main
heroku config:set OPRF_SERVICE_URL=https://your-oprf-service.herokuapp.com
```

**Option B - Disable OPRF (Simpler):**
```bash
heroku config:set LEMMA_ENABLE_OPRF=false
```

### Step 4: Production Security Settings
```bash
heroku config:set FLASK_ENV=production
heroku config:set DEBUG=false
heroku config:set LEMMA_FORCE_HTTPS=true
```

### Step 5: Verify Deployment
```bash
# Test health endpoint
curl https://your-app.herokuapp.com/api/health

# Test human verification flow
# Visit your app and try the "Verify Lemma" button
```

## TESTING COMMANDS

### Test Locally Before Deploying:
```bash
# Install production dependency
pip install pyristretto255==1.3.3

# Set test environment variables
export STRIPE_SECRET_KEY=sk_test_YOUR_TEST_KEY
export LEMMA_ENABLE_OPRF=false

# Run tests
python -m pytest tests/ -v

# Test application startup
python app.py
```

### Test on Heroku After Deployment:
```bash
# Check logs for errors
heroku logs --tail

# Test health endpoint
curl https://your-app.herokuapp.com/api/health

# Test CSRF token generation
curl https://your-app.herokuapp.com/api/generate-csrf

# Test the web interface
open https://your-app.herokuapp.com
```

## SUCCESS CRITERIA

✅ **Application starts without errors**
✅ **No missing dependency warnings**
✅ **Stripe verification works**
✅ **Human verification flow completes successfully**
✅ **All API endpoints respond correctly**
✅ **HTTPS enforced**
✅ **Production security settings active**

## PRIORITY ORDER

1. **IMMEDIATE (Critical):** Fix pyristretto255 dependency
2. **IMMEDIATE (Critical):** Configure Stripe keys
3. **IMMEDIATE (Critical):** Deploy or disable OPRF service
4. **HIGH:** Set production security settings
5. **MEDIUM:** Add monitoring and external storage
6. **LOW:** Performance optimizations

Once these issues are resolved, your Lemma Enterprise software will be ready for customer site integration. 