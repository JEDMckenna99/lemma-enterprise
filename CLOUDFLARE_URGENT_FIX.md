# 🚨 URGENT: Fix CloudFlare 403 "Just a moment..." Issue

**Status:** lemma.id is returning 403 errors due to aggressive CloudFlare security  
**Solution:** 5-minute fix to whitelist API endpoints while maintaining security

---

## ⚡ **IMMEDIATE ACTIONS (5 minutes)**

### **Step 1: Lower Security Level**
```
1. Go to CloudFlare Dashboard → Security → Settings
2. Change "Security Level" from "High" to "MEDIUM"
3. Save changes
```

### **Step 2: Create API Whitelist Rule**
```
1. Go to CloudFlare Dashboard → Security → WAF
2. Click "Create custom rule"
3. Rule Name: "Lemma API Whitelist"
4. Expression: (http.request.uri.path contains "/api/")
5. Action: "Skip" → Select "All remaining custom rules"
6. Deploy rule
```

### **Step 3: Create Static Assets Rule**
```
1. Still in WAF → "Create custom rule"
2. Rule Name: "Lemma Static Assets Whitelist"  
3. Expression: (http.request.uri.path contains "/static/")
4. Action: "Skip" → Select "All remaining custom rules"
5. Deploy rule
```

### **Step 4: Test the Fix**
```bash
# Should return HTTP 200 (not 403)
curl -v https://lemma.id/api/health

# Should return JSON response
python -c "import requests; r = requests.get('https://lemma.id/api/health', timeout=10); print(f'Status: {r.status_code}'); print(f'Response: {r.text[:100]}')"
```

---

## 🔧 **EXPECTED RESULTS**

**Before Fix:**
- ❌ Status: 403
- ❌ Response: "Just a moment..."
- ❌ CloudFlare challenge page

**After Fix:**
- ✅ Status: 200
- ✅ Response: {"status":"ok","service":"lemma-human-verification","version":"1.0.0"}
- ✅ Normal API functionality

---

## 📋 **COMPLETE SETUP (Optional - 15 minutes)**

If you want the full CloudFlare Pro optimization, follow the complete checklist in `cloudflare-configuration.md`:

- Rate limiting rules for API protection
- Caching rules for performance
- Bot Fight Mode configuration
- SSL/TLS optimization
- Performance enhancements

---

## 🧪 **VERIFICATION**

Once fixed, test these URLs:
- ✅ https://lemma.id/api/health (should return 200)
- ✅ https://lemma.id/ (should load normally)
- ✅ https://lemma.id/join-network (should work)
- ✅ https://lemma.id/static/js/lemma-shield-widget.js (should load fast)

---

## 🎯 **PRIORITY ORDER**

1. **URGENT (5 min):** Steps 1-3 above to fix 403 errors
2. **Important (15 min):** Rate limiting rules from main config  
3. **Performance (30 min):** Full caching and optimization setup

The first 3 steps will immediately fix the 403 issue and make lemma.id fully functional! 