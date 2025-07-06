# CloudFlare Domain Issue Resolution Guide

## Issue Summary

**Problem**: `lemma.id` domain returns 403 Forbidden error while Heroku direct access works fine.

**Root Cause**: CloudFlare security settings are blocking requests with challenge mode enabled.

## Diagnosis Results

### ✅ Working Components
- DNS resolution: A records point to CloudFlare IPs (172.66.40.120, 172.66.43.136)
- Heroku app: Direct access to `lemma-enterprise-0f6ba17076c1.herokuapp.com` works perfectly
- SSL certificate: Valid certificate issued by Google Trust Services
- Static files: `/static/js/lemma-sdk-unified.js` loads successfully (200 OK)

### ❌ Blocked Components
- Main pages: `/` returns 403
- API endpoints: `/api/health` returns 403
- SDK demo: `/sdk-demo` returns 403
- CloudFlare headers: `cf-mitigated: challenge` indicates challenge mode active

## CloudFlare Configuration Issues

### 1. Challenge Mode Active
- **Header**: `cf-mitigated: challenge`
- **Impact**: Blocks automated and programmatic requests
- **Solution**: Disable "I'm Under Attack" mode

### 2. Security Rules Too Strict
- **Impact**: Blocking legitimate API requests
- **Solution**: Review and adjust security rules

### 3. SSL/TLS Mode Misconfiguration
- **Current**: Using Google Trust Services certificate
- **Issue**: May need CloudFlare's certificate or different SSL mode
- **Solution**: Verify SSL/TLS mode settings

## Step-by-Step Resolution

### Immediate Actions (CloudFlare Dashboard)

1. **Login to CloudFlare Dashboard**
   - Go to https://dash.cloudflare.com/
   - Select the `lemma.id` domain

2. **Disable Challenge Mode**
   - Navigate to **Security** → **Settings**
   - Set Security Level to **Medium** or **Low** (not High)
   - Disable **I'm Under Attack Mode** if enabled

3. **Review SSL/TLS Settings**
   - Navigate to **SSL/TLS** → **Overview**
   - Set SSL/TLS encryption mode to **Flexible** or **Full**
   - Avoid **Full (Strict)** unless you have proper certificates

4. **Check Security Rules**
   - Navigate to **Security** → **WAF**
   - Review Custom Rules for any blocking patterns
   - Temporarily disable aggressive rules

5. **Review Page Rules**
   - Navigate to **Rules** → **Page Rules**
   - Check for any redirect rules that might interfere

6. **Bot Fight Mode**
   - Navigate to **Security** → **Bots**
   - Ensure Bot Fight Mode is not overly aggressive
   - Consider allowing good bots

### DNS Configuration Verification

1. **Check DNS Records**
   - Navigate to **DNS** → **Records**
   - Verify A records point to CloudFlare IPs
   - Add CNAME record if needed: `CNAME lemma.id lemma-enterprise-0f6ba17076c1.herokuapp.com`

2. **Test DNS Propagation**
   - Use `nslookup lemma.id` or `dig lemma.id`
   - Verify records are propagating correctly

### Production Recommendations

1. **SSL/TLS Mode**: Use **Full** mode for production
2. **Security Level**: Set to **Medium** for balanced protection
3. **Cache Rules**: Configure appropriate caching for static assets
4. **Page Rules**: Set up caching rules for `/static/*` paths
5. **Security Rules**: Create allow-list for legitimate API endpoints

## Testing Commands

```bash
# Test domain access
curl -I https://lemma.id/

# Test specific endpoints
curl -I https://lemma.id/api/health
curl -I https://lemma.id/sdk-demo

# Test with different user agents
curl -I -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" https://lemma.id/

# Compare with Heroku direct
curl -I https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/health
```

## Expected Results After Fix

- `https://lemma.id/` → 200 OK
- `https://lemma.id/api/health` → 200 OK with JSON response
- `https://lemma.id/sdk-demo` → 200 OK with HTML page
- All static assets load correctly
- No CloudFlare challenge pages

## Validation Script

Run the diagnostic script to verify fixes:

```bash
python test_cloudflare_domain.py
```

Expected output after resolution:
- All endpoints return 200 OK
- No `cf-mitigated: challenge` headers
- CloudFlare headers present but allowing traffic

## Common Pitfalls

1. **SSL Mode Too Strict**: Full (Strict) mode requires valid certificates
2. **Cache Everything**: Can interfere with dynamic content
3. **Security Rules**: Overly broad rules blocking legitimate traffic
4. **Bot Protection**: Blocking API clients and SDKs
5. **Rate Limiting**: Aggressive limits affecting normal usage

## Support Resources

- CloudFlare Support: https://support.cloudflare.com/
- SSL/TLS Configuration: https://developers.cloudflare.com/ssl/
- Security Rules: https://developers.cloudflare.com/waf/

## Priority Actions

1. **🔥 CRITICAL**: Disable challenge mode immediately
2. **🔥 HIGH**: Set SSL/TLS to Flexible or Full mode
3. **🔥 HIGH**: Review and adjust security rules
4. **🔧 MEDIUM**: Optimize caching and page rules
5. **🔧 LOW**: Fine-tune bot protection settings

Once these changes are made, the domain should work correctly and serve the Lemma SDK properly. 