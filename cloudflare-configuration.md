# CloudFlare Pro Configuration for Lemma Shield Enterprise

**Domain:** www.lemma.id  
**Heroku App:** lemma-enterprise.herokuapp.com  
**Target Performance:** <100ms global response times

---

## 🚨 **IMMEDIATE FIX: 403 "Just a moment..." Issue**

**Problem:** CloudFlare security is blocking legitimate API requests  
**Solution:** Configure specific firewall rules for Lemma API endpoints

### **🔧 STEP 1: Lower Security Level**
```
CloudFlare Dashboard → Security → Settings:
□ Security Level: MEDIUM (not High)
□ Challenge Passage: 30 minutes
□ Browser Integrity Check: ON
```

### **🔧 STEP 2: API Endpoint Whitelist Rules**
```
CloudFlare Dashboard → Security → WAF → Custom Rules:

Rule 1: Allow Lemma API Health Checks
□ Rule Name: "Lemma API Health Whitelist"
□ Expression: (http.request.uri.path eq "/api/health")
□ Action: Skip → All remaining custom rules, Rate limiting rules, Managed rules
□ Deploy

Rule 2: Allow Core API Endpoints  
□ Rule Name: "Lemma Core API Whitelist"
□ Expression: (http.request.uri.path contains "/api/shield/" or http.request.uri.path contains "/api/verify" or http.request.uri.path contains "/api/generate-challenge")
□ Action: Skip → Rate limiting rules, Managed rules (keep some security)
□ Deploy

Rule 3: Allow Static Assets
□ Rule Name: "Lemma Static Assets"
□ Expression: (http.request.uri.path contains "/static/")
□ Action: Skip → All remaining custom rules, Rate limiting rules, Managed rules
□ Deploy
```

### **🔧 STEP 3: Configure Bot Fight Mode**
```
CloudFlare Dashboard → Security → Bots:
□ Bot Fight Mode: ON
□ Super Bot Fight Mode: OFF (can interfere with APIs)
□ Add Custom Rule for APIs:
  - Rule Name: "Allow Lemma API Bots"
  - Expression: (http.request.uri.path contains "/api/")
  - Action: Allow
```

### **🔧 STEP 4: Rate Limiting (Instead of Blocking)**
```
CloudFlare Dashboard → Security → WAF → Rate limiting rules:

Rule 1: API General Protection
□ Rule Name: "Lemma API Rate Limit"
□ Expression: (http.request.uri.path contains "/api/" and not http.request.uri.path eq "/api/health")
□ Requests: 100 per minute
□ Action: Block for 60 seconds

Rule 2: Health Check - High Limit
□ Rule Name: "Health Check Rate Limit"  
□ Expression: (http.request.uri.path eq "/api/health")
□ Requests: 300 per minute
□ Action: Block for 10 seconds

Rule 3: Revocation Protection
□ Rule Name: "Revocation API Protection"
□ Expression: (http.request.uri.path contains "/api/shield/revoke-credential")
□ Requests: 10 per minute
□ Action: Block for 300 seconds
```

---

## 🚀 **CLOUDFLARE PRO SETUP CHECKLIST**

### ✅ **STEP 1: DNS CONFIGURATION**
```
CloudFlare Dashboard → DNS:
□ A Record: lemma.id → [Heroku IP] (☁️ Proxied)
□ CNAME: www → lemma.id (☁️ Proxied)  
□ CNAME: api → lemma.id (☁️ Proxied)
□ Orange cloud enabled for all records
```

### ✅ **STEP 2: SSL/TLS OPTIMIZATION**
```
CloudFlare Dashboard → SSL/TLS:
□ Encryption Mode: "Full (Strict)"
□ Always Use HTTPS: ON
□ Minimum TLS Version: TLS 1.2
□ TLS 1.3: Enabled
□ Automatic HTTPS Rewrites: ON
□ Certificate Authority Authorization (CAA): Allow CloudFlare
```

### ✅ **STEP 3: SPEED OPTIMIZATION**
```
CloudFlare Dashboard → Speed → Optimization:
□ Auto Minify JavaScript: ON
□ Auto Minify CSS: ON
□ Auto Minify HTML: ON
□ Brotli Compression: ON
□ Enhanced HTTP/2 Prioritization: ON (Pro)
□ HTTP/3 (QUIC): ON
□ Early Hints: ON (Pro)
```

### ✅ **STEP 4: CACHING RULES**
```
CloudFlare Dashboard → Caching → Cache Rules:

Rule 1: Static Assets
□ If URI Path matches /static/*
□ Cache Level: Cache Everything
□ TTL: 30 days

Rule 2: API Health  
□ If URI Path equals /api/health
□ Cache Level: Cache Everything
□ TTL: 5 minutes

Rule 3: Offline Assets
□ If URI Path matches /offline/*
□ Cache Level: Cache Everything  
□ TTL: 24 hours

Rule 4: API Bypass
□ If URI Path starts with /api/
□ Cache Level: Bypass
```

### ✅ **STEP 5: PAGE RULES (Pro Feature)**
```
CloudFlare Dashboard → Page Rules:

Rule 1: Static Performance
□ URL: lemma.id/static/*
□ Cache Level: Cache Everything
□ Edge Cache TTL: 1 month
□ Browser Cache TTL: 1 week

Rule 2: API Optimization
□ URL: lemma.id/api/*  
□ Cache Level: Bypass
□ Disable Performance Features (if needed)

Rule 3: Homepage Cache
□ URL: lemma.id/
□ Cache Level: Cache Everything
□ Edge Cache TTL: 2 hours
```

### ✅ **STEP 6: SECURITY SETTINGS (UPDATED)**
```
CloudFlare Dashboard → Security:
□ Security Level: MEDIUM (not High - this was causing 403)
□ Bot Fight Mode: ON but with API exceptions
□ Rate Limiting: Configured above (not blocking)
□ WAF: ON with Custom Rules for API whitelist
□ DDoS Protection: Automatic (included)
□ Challenge Passage: 30 minutes
```

### ✅ **STEP 7: FIREWALL RULES (UPDATED)**
```
CloudFlare Dashboard → Security → WAF → Custom Rules:

PRIORITY 1: API Whitelist (Allow)
□ Rule Name: "Lemma API Whitelist"
□ Expression: (http.request.uri.path contains "/api/")
□ Action: Skip → Managed rules (keep rate limiting)

PRIORITY 2: Static Assets (Allow)  
□ Rule Name: "Static Assets Allow"
□ Expression: (http.request.uri.path contains "/static/")
□ Action: Skip → All security rules

PRIORITY 3: Admin Protection
□ Rule Name: "Admin Area Protection"
□ Expression: (http.request.uri.path contains "/admin")
□ Action: Managed Challenge (extra security)
```

### ✅ **STEP 8: NETWORK OPTIMIZATION**
```
CloudFlare Dashboard → Network:
□ HTTP/3: ON
□ 0-RTT Connection Resumption: ON
□ gRPC: ON
□ WebSockets: ON  
□ Pseudo IPv4: ON
□ IP Geolocation: ON
```

### ✅ **STEP 9: ARGO SMART ROUTING (Optional +$5/month)**
```
CloudFlare Dashboard → Traffic → Argo:
□ Argo Smart Routing: ON
□ Benefits: 30% performance improvement
□ Intelligent routing optimization
```

### ✅ **STEP 10: ANALYTICS & MONITORING**
```
CloudFlare Dashboard → Analytics:
□ Web Analytics: ON
□ Core Web Vitals: Monitor
□ Cache Performance: Track hit rates
□ Security Events: Monitor threats
```

---

## 🎯 **EXPECTED PERFORMANCE IMPROVEMENTS**

### **Before CloudFlare Pro:**
- Global Response Time: 400-700ms
- Security: Basic HTTPS
- Caching: None

### **After CloudFlare Pro:**
- Global Response Time: <100-150ms (70-80% improvement)
- Security: Enterprise-grade WAF + DDoS
- Caching: Intelligent edge caching
- Reliability: 99.99% uptime

---

## 🔧 **LEMMA-SPECIFIC OPTIMIZATIONS**

### **Offline Verification Optimization:**
```
Cache Rule for Offline Assets:
□ Cache /offline/* for 24 hours
□ Preload verification data at edge
□ Enable HTTP/3 for faster initial loads
```

### **API Performance:**
```
Rate Limiting for APIs:
□ /api/verify-offline: 100 req/min (local operation)
□ /api/shield/*: 100 req/min per IP
□ /api/revoke-credential: 10 req/min per IP
□ /api/health: 300 req/min (monitoring)
```

### **Security for Identity System:**
```
Enhanced Protection:
□ Block known bot networks (with API exceptions)
□ Rate limit authentication endpoints  
□ Monitor for credential stuffing attacks
□ Enable Browser Integrity Check (with API bypass)
```

---

## 🚨 **CRITICAL CONFIGURATIONS**

### **Must Enable:**
1. **Full (Strict) SSL** - Required for identity verification
2. **Always HTTPS** - Security compliance
3. **API Whitelist Rules** - Fix 403 errors
4. **Medium Security Level** - Balance security and access

### **Recommended:**
1. **Argo Smart Routing** - 30% performance boost
2. **Early Hints** - Faster page loads
3. **HTTP/3** - Latest protocol benefits

---

## 🧪 **TESTING YOUR CONFIGURATION**

After implementing the above rules, test with:

```bash
# Test API health (should return 200)
curl -v https://lemma.id/api/health

# Test with API key (should work)  
curl -H "X-API-Key: your-key" https://lemma.id/api/shield/status

# Test static assets (should be fast)
curl -I https://lemma.id/static/js/lemma-shield-widget.js
```

Expected results:
- ✅ HTTP 200 responses (not 403)
- ✅ Fast response times (<200ms)
- ✅ Proper cache headers on static assets

---

## 📞 **TROUBLESHOOTING**

If still getting 403 errors:
1. **Check Rule Order**: Whitelist rules must be PRIORITY 1
2. **Verify Expressions**: Use CloudFlare's Expression Editor
3. **Test Gradually**: Start with Security Level "Low", then increase
4. **Monitor Firewall Events**: CloudFlare Dashboard → Security → Events

**Need Help?** The rules above should resolve the 403 issue while maintaining security. 