# Lemma Enterprise Production Readiness Checklist

## 🔴 Critical - Must Fix Before Production

### 1. Environment Variables Configuration
Set the following required environment variables:

```bash
# Core Configuration
LEMMA_ADMIN_USER=your_admin_username
LEMMA_ADMIN_PASS=your_secure_password_here
LEMMA_SECRET_KEY=your_random_secret_key_256_bits
LEMMA_API_KEY=your_api_key_for_customers

# DID Configuration
DID=did:lemma:production
DID_METHOD=key  # or web, ethr, lemma

# Security Configuration
LEMMA_ENABLE_P2P=true
LEMMA_HARDWARE_SECURITY=true

# Human Verification (Required for Core Feature)
STRIPE_SECRET_KEY=sk_live_...  # Live key for production
STRIPE_PUBLISHABLE_KEY=pk_live_...

# External Storage (Recommended for Production)
LEMMA_EXTERNAL_STORAGE_URL=s3://your-bucket/lemma-keys.json
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key

# Optional Enhanced Features
OPRF_SERVICE_URL=https://your-oprf-service.com
LEMMA_ENABLE_METRICS=true
LEMMA_LOG_LEVEL=INFO
```

### 2. Fix Failing Tests
Current failing tests that need to be resolved:
- ✅ **FIXED**: Presentation validation (now returns proper 400 status codes)
- ✅ **FIXED**: API key validation tests (now properly test without test mode)

### 3. Deploy OPRF Service (Critical for Revocation)
The current system shows:
```
ERROR: Failed to get OPRF public key: HTTPConnectionPool(host='localhost', port=8080)
WARNING: pyristretto255 not available, using mock implementation
```

**Action Required:**
- Deploy the OPRF service to a production URL
- Set `OPRF_SERVICE_URL` environment variable
- Install `pyristretto255` for production crypto: `pip install pyristretto255`

### 4. Configure Stripe Identity
For human verification to work in production:
```bash
# Set your Stripe live keys (not test keys)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
```

## 🟡 Important - Should Fix Before Production

### 5. Database/Storage Strategy
Current: File-based storage (`.lemma_enterprise/`)
**Recommended for Production:**
- Configure external storage (S3, Azure Blob, etc.)
- Set up database backup strategy
- Consider Redis for session storage at scale

### 6. SSL/HTTPS Configuration
Ensure HTTPS is enforced:
```bash
# For production deployment
LEMMA_FORCE_HTTPS=true
LEMMA_SECURE_COOKIES=true
```

### 7. Rate Limiting Configuration
Configure appropriate rate limits for production:
```python
# In production config
RATE_LIMIT_DEFAULT = "100/hour"
RATE_LIMIT_VERIFIED_USERS = "1000/hour"
```

### 8. Monitoring & Alerting
Set up monitoring for:
- Health endpoint: `/api/health`
- Error rates and response times
- Storage usage
- Certificate expiration

## 🟢 Nice to Have - Production Enhancements

### 9. Performance Optimizations
- Enable caching for frequently accessed data
- Configure CDN for static assets
- Optimize database queries

### 10. Security Enhancements
- Set up Web Application Firewall (WAF)
- Configure DDoS protection
- Enable audit logging
- Set up intrusion detection

### 11. Scalability
- Configure horizontal scaling
- Set up load balancing
- Implement connection pooling

## Deployment Commands

### For Heroku:
```bash
# Set all environment variables
heroku config:set LEMMA_ADMIN_USER=admin
heroku config:set LEMMA_ADMIN_PASS=your_secure_password
heroku config:set LEMMA_SECRET_KEY=your_secret_key
heroku config:set LEMMA_API_KEY=your_api_key
heroku config:set STRIPE_SECRET_KEY=sk_live_...
heroku config:set STRIPE_PUBLISHABLE_KEY=pk_live_...
heroku config:set DID=did:lemma:production

# Deploy
git push heroku main
```

### For Docker:
```bash
docker build -t lemma-enterprise .
docker run -d \
  -e LEMMA_ADMIN_USER=admin \
  -e LEMMA_ADMIN_PASS=your_secure_password \
  -e LEMMA_SECRET_KEY=your_secret_key \
  -e STRIPE_SECRET_KEY=sk_live_... \
  -p 5000:5000 \
  lemma-enterprise
```

### For AWS/Azure:
Use the environment variable configuration above with your cloud provider's secret management system.

## Pre-Deployment Testing

### 1. Run All Tests
```bash
python -m pytest tests/ -v
```

### 2. Test Production Configuration Locally
```bash
# Set production-like environment variables
export LEMMA_ADMIN_USER=admin
export LEMMA_ADMIN_PASS=test_password
export LEMMA_SECRET_KEY=test_secret_key_32_bytes_long
export STRIPE_SECRET_KEY=sk_test_...  # Use test key for local testing

# Run the application
python app.py

# Test key endpoints
curl http://localhost:5000/api/health
curl -X POST http://localhost:5000/api/generate-csrf-token
```

### 3. Customer Integration Test
Test the customer integration flow:
```javascript
// Test the JavaScript wallet integration
// Include lemma-wallet.js and lemma-wallet-init.js
// Verify credential issuance and verification works
```

## Post-Deployment Verification

### 1. Check Health Endpoint
```bash
curl https://your-domain.com/api/health
```

### 2. Verify Stripe Integration
```bash
# Should not show warnings about missing Stripe keys
# Check application logs
```

### 3. Test Customer Integration APIs
```bash
# Test credential lookup
curl https://your-domain.com/api/credential-lookup/test_user

# Test presentation verification
curl -X POST https://your-domain.com/api/verify-human \
  -H "Content-Type: application/json" \
  -d '{"presentation": {...}, "challenge": "test"}'
```

## Production Monitoring

Monitor these metrics:
- Response times for `/api/health`, `/api/verify-human`
- Error rates on verification endpoints
- OPRF service availability
- Storage usage
- SSL certificate expiration

## Security Checklist

- [ ] All environment variables set securely
- [ ] HTTPS enforced
- [ ] Secure cookies enabled
- [ ] Rate limiting configured
- [ ] API keys rotated regularly
- [ ] Access logs monitored
- [ ] Security headers configured
- [ ] Regular security scans performed

## Support & Troubleshooting

### Common Issues:

1. **OPRF Service Connection Failed**
   - Check `OPRF_SERVICE_URL` configuration
   - Verify service is running and accessible
   - Install `pyristretto255` package

2. **Stripe Identity Not Working**
   - Verify Stripe keys are live keys (not test)
   - Check Stripe webhook configuration
   - Ensure HTTPS is enabled

3. **Credential Verification Failing**
   - Check DID configuration
   - Verify key storage is accessible
   - Check external storage connectivity

4. **Performance Issues**
   - Monitor database/storage performance
   - Check rate limiting configuration
   - Review caching strategy

For additional support, check the application logs and the GitHub repository issues. 