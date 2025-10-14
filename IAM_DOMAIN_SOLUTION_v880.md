# ✅ IAM Domain Solution - Use lemma.id Directly!

## 🎯 **THE SOLUTION**

Since `lemma.id` already points to your Heroku app, just use `lemma.id` for everything!

---

## 🔐 **Issue Your Admin Credential on lemma.id**

### **1. Visit Bootstrap Page on lemma.id**:
```
https://lemma.id/admin/bootstrap
```

### **2. Your API Key**:
```
e663a17fe6a8b1501c768ad88c9ceb072d2ef6eecaa51d84b38a89edfe07d5db
```

### **3. Issue Credential**
- Fill in the form (pre-filled)
- Enter API key
- Click "Issue Admin Credential"

### **4. View Wallet on lemma.id**:
```
https://lemma.id/wallet
```

**Result**: ✅ Both PoH and Permission lemmas will appear!

---

## 📊 **Why This Works**

### **DNS Configuration** ✅:
```
lemma.id        → Heroku app (via ALIAS)
www.lemma.id    → Heroku app (via CNAME)
```

### **Same Backend** ✅:
- All domains serve the same Heroku dyno
- Same APIs
- Same crypto engine
- Same database

### **Different localStorage** ⚠️:
- `lemma.id` → Has its own encrypted storage
- `www.lemma.id` → Has its own encrypted storage  
- `lemma-enterprise...herokuapp.com` → Has its own encrypted storage

**Each domain needs its own credential issuance!**

---

## 🎯 **Production Recommendation**

### **Use lemma.id Exclusively**:

**Admin Bootstrap**:
```
https://lemma.id/admin/bootstrap
```

**Wallet**:
```
https://lemma.id/wallet
```

**Dashboard**:
```
https://lemma.id/dashboard
```

**API Endpoints**:
```
https://lemma.id/api/v1/iam/admin/self-issue
https://lemma.id/api/v1/sites/register
https://lemma.id/api/v1/auth/verify
```

---

## ✅ **What You Need to Do**

### **Step 1: Issue Credential on lemma.id**
Visit: `https://lemma.id/admin/bootstrap`
API Key: `e663a17fe6a8b1501c768ad88c9ceb072d2ef6eecaa51d84b38a89edfe07d5db`

### **Step 2: View Wallet on lemma.id**
Visit: `https://lemma.id/wallet`

### **Step 3: Check Console**
You should see:
```
🔐 Loading from encrypted storage: 2 credentials found
✅ Decrypted credential 1/2: ... (identity)
✅ Decrypted credential 2/2: ... (permission)
📊 Wallet contents: {poh: 1, permissions: 1, total: 2}
```

---

## 📋 **Marketing Update Needed**

Since you're using `lemma.id` as production, update all documentation/marketing to use:
- ❌ ~~`lemma-enterprise-0f6ba17076c1.herokuapp.com`~~
- ✅ `lemma.id`

The Heroku URL is just the underlying infrastructure - customers see `lemma.id`!

---

## 🚀 **Next Steps**

1. **Visit** `https://lemma.id/admin/bootstrap`
2. **Issue** your admin credential there
3. **View** `https://lemma.id/wallet`
4. **See** both PoH and Permission lemmas!

**Use lemma.id for everything - that's your production domain!** 🎯

