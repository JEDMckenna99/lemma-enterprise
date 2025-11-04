# 🚀 Developer Platform Deployed - v1049

**Deployed:** November 4, 2025  
**Status:** ✅ Live at https://lemma.id/platform

---

## 📊 **WHAT'S DEPLOYED:**

### **Developer Platform Phase 1** (Complete)

**Route:** `/platform`

**Features:**
- ✅ Modern sidebar navigation
- ✅ Real-time statistics from database
- ✅ User management with email display
- ✅ Quick actions for common tasks
- ✅ Integration code snippets
- ✅ Permission-based access control

---

## 🗄️ **DATABASE ARCHITECTURE:**

### **Production Tables (From Migrations):**

**1. `permission_types`** - Permission definitions
- Columns: `id`, `site_id`, `name`, `type`, `description`, `config`
- Example: `beta-user`, `admin`, `super_admin`
- Auto-created on first use

**2. `permission_instances`** - User permission grants
- Columns: `id`, `permission_type_id`, `site_id`, `email`, `credential_did`, `granted_at`, `expires_at`, `revoked_at`, `metadata`
- **This is the source of truth for user counts**
- Populated when credentials are issued via email confirmation

**3. `sites`** - Registered sites
- Columns: `site_id`, `site_domain`, `company_name`, `admin_email`, `api_key`
- Currently: 1 site (lemma_platform)

**4. `iam_audit_log`** - Audit trail
- Columns: `id`, `site_id`, `event_type`, `actor`, `target`, `details`, `timestamp`
- Tracks all IAM operations

---

## 📈 **PLATFORM STATISTICS:**

### **Data Sources:**

**1. Monthly Active Users (MAU):**
- Source: Redis key `mau:lemma_platform:2025-11`
- Tracks unique users who verified credentials
- Resets monthly

**2. Total Verifications:**
- Source: Redis counter `verifications:lemma_platform`
- Increments on each verification
- Resets monthly

**3. Active Users:**
- Source: `permission_instances` table
- Query: `WHERE site_id='lemma_platform' AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > NOW())`
- **Currently: 1 user (legacy test user)**
- **Will increment as new users sign up** ✅

**4. Registered Sites:**
- Source: `sites` table
- Currently: 1 site

**5. Recent Activity:**
- Source: `permission_instances` + `permission_types` tables (JOIN)
- Shows last 5 permission grants with email, permission level, time ago

---

## 🔄 **USER SIGNUP FLOW (v1049):**

### **Complete Flow:**

**1. User enters email on login page**
```
POST /api/v1/iam/request-access
{
  site_id: 'lemma_platform',
  site_domain: 'lemma.id',
  user_email: 'user@example.com',
  permission_level: 'beta-user'
}
```

**2. Confirmation email sent**
- Token stored in Redis (24-hour TTL)
- Email via Mailgun

**3. User clicks confirmation link**
```
GET /confirm-access?token=xxx
```

**4. System processes:**
- ✅ Retrieves token from Redis
- ✅ Issues Ed25519-signed credential (~200µs)
- ✅ **NEW (v1049):** Creates `permission_instances` record
- ✅ **NEW (v1049):** Creates `permission_types` if needed
- ✅ Renders confirmation page

**5. Browser stores credential:**
- ✅ Auto-stores in encrypted wallet (browser-side)
- ✅ Auto-redirects to homepage

**6. Database records created:**
```sql
-- permission_types (if new)
INSERT INTO permission_types 
(site_id, name, type, description)
VALUES ('lemma_platform', 'beta-user', 'role', 'Beta-user access');

-- permission_instances (always)
INSERT INTO permission_instances
(permission_type_id, site_id, email, credential_did, granted_at, expires_at, metadata)
VALUES (1, 'lemma_platform', 'user@example.com', 'did:lemma:user_xxx', NOW(), NOW() + 90 days, {...});
```

**7. Platform stats update:**
- Active Users count increments immediately
- User visible in "Users & Permissions" section
- Recent Activity shows the grant

---

## 🎨 **PLATFORM SECTIONS:**

### **📊 Overview (Active):**
- 4 stat cards (MAU, Verifications, Active Users, Registered Sites)
- Quick actions (Issue Permission, Generate API Key, etc.)
- Recent activity feed (last 5 events)

### **👥 Users & Permissions (Active):**
- User table with search
- Columns: Email, Permission, Status, Granted, Expires
- Issue Permission modal
- Data from `permission_instances` table

### **🔑 API & Integration (Active):**
- API key management (placeholder)
- Quick integration code snippet
- Copy-paste ready SDK example

### **📈 Analytics (Placeholder):**
- Coming in Phase 2
- Will show MAU trends, charts, performance metrics

### **⚙️ Settings (Placeholder):**
- Coming in Phase 2
- Email templates, branding, webhooks

### **🛡️ Platform Admin (Conditional):**
- Only visible if `super_admin` permission
- Manage all platform users
- Coming in Phase 2

---

## 🎯 **HEADER NAVIGATION:**

**Updated (v1043):**
- **Platform** → `/platform` (developer dashboard)
- **Wallet** → `/wallet` (credential storage)
- **Docs** → `/docs` (documentation)

**Removed:**
- Old "Dashboard" (now redirects to /platform)
- "IAM" (redundant with platform)
- "API Playground" (will add back later)

---

## 💰 **PRICING (Updated v1041):**

**Post-Beta Pricing:** `$0.08-$0.10 per MAU`
- 1/3 the cost of Auth0 Professional ($0.24/MAU)
- 67% cheaper than competition
- Sustainable for operations

**Free Tier (Beta):**
- Currently: Unlimited users
- After beta: Up to 1,000 MAU free

---

## ✅ **WHAT'S WORKING (v1049):**

**Complete Email-to-Credential Flow:**
1. ✅ Email confirmation (Redis tokens, 24h expiry)
2. ✅ Credential issuance (Ed25519, ~200µs)
3. ✅ Encrypted wallet storage (browser-side, AES-256)
4. ✅ **Database tracking** (permission_instances table)
5. ✅ **Platform stats** (real-time counts)
6. ✅ **Auto-sign-in** (local verification, 63µs)

**Developer Platform:**
1. ✅ Permission-based access (requires lemma.id credential)
2. ✅ Real-time stats from database + Redis
3. ✅ User list with email addresses
4. ✅ Issue permission modal (sends email confirmation)
5. ✅ Recent activity feed
6. ✅ Integration code snippets

**Header Navigation:**
1. ✅ Clean 3-link nav (Platform, Wallet, Docs)
2. ✅ Dashboard redirects to Platform
3. ✅ Consistent across admin/customer

---

## 📊 **CURRENT STATS (Real Data):**

**From Database:**
- **Active Users:** 1 (legacy test user from October 28)
- **Registered Sites:** 1 (lemma_platform)

**From Redis:**
- **MAU:** 0 (nobody verified credentials this month yet)
- **Verifications:** 0 (counter resets monthly)

**Your 5 beta users:**
- ❌ Not in database (signed up before v1049)
- ✅ Have credentials in encrypted wallets
- ✅ Can auto-sign-in
- ℹ️ **Decision:** Count forward from v1049 only

---

## 🧪 **TEST THE COMPLETE FLOW:**

### **New User Signup:**

**1. Visit:** https://lemma.id/login

**2. Enter email:** `test@example.com`

**3. Check email → click confirmation link**

**4. Verify database record created:**
```bash
heroku pg:psql -a lemma-enterprise -c "SELECT email, pt.name FROM permission_instances pi JOIN permission_types pt ON pi.permission_type_id = pt.id WHERE site_id='lemma_platform'"
```

**5. Check platform:**
- Visit: https://lemma.id/platform
- **Active Users** should increment by 1
- **Users & Permissions** should show the new email

---

## 🔍 **DEBUGGING:**

### **Check Platform Stats API:**

**Browser console:**
```javascript
fetch('/api/platform/stats')
  .then(r => r.json())
  .then(data => console.log('📊 Stats:', data));
```

**Expected response:**
```json
{
  "success": true,
  "stats": {
    "mau": 0,
    "total_verifications": 0,
    "active_users": 1,
    "registered_sites": 1
  },
  "recent_activity": [
    {
      "user": "testuser@example.com",
      "permission": "premium_tier_1",
      "time_ago": "1mo ago"
    }
  ]
}
```

### **Check Heroku Logs:**
```bash
heroku logs --tail -a lemma-enterprise | grep -i "platform\|tracked permission"
```

---

## 🚀 **WHAT'S NEXT (Phase 2):**

### **Week 2-3:**
1. **Analytics Charts:**
   - MAU trends over time
   - Verification performance graphs
   - User growth chart

2. **Settings Page:**
   - Email template customization
   - Branding (logo, colors)
   - Webhook configuration

3. **API Key Management:**
   - Generate real API keys
   - Usage tracking per key
   - Revoke/rotate keys

4. **Platform Admin Section:**
   - Manage ALL lemma.id users (if super_admin)
   - Beta program management
   - System-wide analytics

---

## ✅ **PHASE 1 COMPLETE (v1041-1049):**

**Deployed:**
- ✅ Developer platform UI with sidebar nav
- ✅ Real database integration (permission_instances)
- ✅ Stats API (MAU, users, verifications, sites)
- ✅ User list with email addresses
- ✅ Issue permission modal
- ✅ Database tracking on email confirmation
- ✅ Updated pricing ($0.08-$0.10/MAU)
- ✅ Simplified header navigation

**Ready for beta users to start signing up and be counted!** 🎯

---

**Platform is live and tracking from v1049 forward!** New signups will increment the user count automatically.

