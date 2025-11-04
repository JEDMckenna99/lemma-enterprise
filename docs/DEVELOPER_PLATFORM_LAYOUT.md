# Lemma Developer Platform - Layout & Organization

## 🎯 **Platform Purpose**

Two distinct use cases:
1. **Developer Customers** - Integrate Lemma IAM into their apps
2. **Platform Admin (You)** - Manage lemma.id users and platform

---

## 📊 **RECOMMENDED NAVIGATION STRUCTURE**

### **Main Navigation (Sidebar/Top Nav)**

```
┌─ Lemma Developer Platform ──────────────────┐
│                                              │
│  📊 Overview                                 │
│  👥 Users & Permissions                      │
│  🔑 API & Integration                        │
│  📈 Analytics                                │
│  ⚙️  Settings                                │
│  📚 Documentation                            │
│                                              │
│  ─────────────────────────────              │
│  🛡️  Platform Admin (if admin permission)   │
│                                              │
└──────────────────────────────────────────────┘
```

---

## 1️⃣ **OVERVIEW (Dashboard Home)**

**Purpose:** Quick glance at system health and key metrics

### **Layout:**

```
┌─ Overview ─────────────────────────────────────┐
│                                                 │
│  📊 KEY METRICS (4 stat cards)                  │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐          │
│  │ MAU  │ │Verif │ │Users │ │Sites │          │
│  │ 1,234│ │15.2K │ │  156 │ │   3  │          │
│  └──────┘ └──────┘ └──────┘ └──────┘          │
│                                                 │
│  📈 VERIFICATION CHART (last 30 days)           │
│  ┌─────────────────────────────────────┐       │
│  │ Line chart: Verifications over time │       │
│  └─────────────────────────────────────┘       │
│                                                 │
│  🚀 QUICK ACTIONS                               │
│  [Issue Permission] [Revoke Permission]         │
│  [Generate API Key] [View Integration]          │
│                                                 │
│  📋 RECENT ACTIVITY (5 most recent events)      │
│  • User john@example.com verified (2 min ago)  │
│  • Permission issued to jane@site.com (1h ago) │
│                                                 │
└─────────────────────────────────────────────────┘
```

### **Components:**
- **Stat Cards:** MAU count, Total verifications, Active users, Registered sites
- **Chart:** Verifications/day over last 30 days (simple line chart)
- **Quick Actions:** Common tasks with modal popups
- **Activity Feed:** Last 5 audit log entries

---

## 2️⃣ **USERS & PERMISSIONS**

**Purpose:** Manage users and their access rights

### **Layout:**

```
┌─ Users & Permissions ───────────────────────────┐
│                                                  │
│  🔍 SEARCH & FILTERS                             │
│  ┌────────────────────────────────┐             │
│  │ Search: [email or domain      ]│ [Search]    │
│  │ Site: [All ▼] Permission: [All▼]│            │
│  └────────────────────────────────┘             │
│                                                  │
│  👥 USER LIST (table, sortable)                  │
│  ┌──────────────────────────────────────────┐   │
│  │Email         │Site     │Permission│Actions│   │
│  ├──────────────────────────────────────────┤   │
│  │user@site.com │site.com │admin     │[...]  │   │
│  │test@app.io   │app.io   │beta-user │[...]  │   │
│  └──────────────────────────────────────────┘   │
│  [← Prev] Page 1 of 12 [Next →]                 │
│                                                  │
│  📊 PERMISSION BREAKDOWN (pie chart)             │
│  Admin: 12 | Beta-User: 156 | Custom: 8         │
│                                                  │
│  [+ Issue New Permission]                        │
│                                                  │
└──────────────────────────────────────────────────┘
```

### **Features:**
- **Search:** Filter by email, domain, permission level
- **User Table:** 
  - Email, Site, Permission type, Issued date, Expires
  - Actions: View details, Revoke, Extend expiry
- **Bulk Actions:** Revoke multiple, Export CSV
- **Issue Permission Modal:** 
  - Email field
  - Site selector (dropdown of your registered sites)
  - Permission level (admin, beta-user, custom)
  - Expiry (never, 30 days, 90 days, 1 year)

---

## 3️⃣ **API & INTEGRATION**

**Purpose:** SDK setup, API keys, code examples

### **Layout:**

```
┌─ API & Integration ──────────────────────────────┐
│                                                   │
│  🔑 API KEYS                                      │
│  ┌──────────────────────────────────────────┐    │
│  │ Name         │Created  │Last Used │[...]│    │
│  ├──────────────────────────────────────────┤    │
│  │ Production   │Jan 2025 │2 hours ago│[⚙️]│    │
│  │ Development  │Dec 2024 │3 days ago │[⚙️]│    │
│  └──────────────────────────────────────────┘    │
│  [+ Create New API Key]                           │
│                                                   │
│  🌐 REGISTERED SITES                              │
│  ┌──────────────────────────────────────────┐    │
│  │ myapp.com         │ Active │ [Settings] │    │
│  │ staging.myapp.com │ Active │ [Settings] │    │
│  └──────────────────────────────────────────┘    │
│  [+ Register New Site]                            │
│                                                   │
│  💻 QUICK INTEGRATION (tabs)                      │
│  [JavaScript SDK] [React] [Node.js] [Python]      │
│                                                   │
│  ╔════════════════════════════════════════╗      │
│  ║ HTML/JavaScript Example:               ║      │
│  ║                                        ║      │
│  ║ <script src="https://lemma.id/sdk...  ║      │
│  ║ const auth = new LemmaSignIn({        ║      │
│  ║   siteId: 'myapp.com',                ║      │
│  ║   apiKey: 'your-key-here'             ║      │
│  ║ });                                   ║      │
│  ║ auth.init();                          ║      │
│  ╚════════════════════════════════════════╝      │
│  [Copy Code]                                      │
│                                                   │
│  📚 [View Full Documentation →]                   │
│                                                   │
└───────────────────────────────────────────────────┘
```

### **Features:**
- **API Key Management:**
  - Create, revoke, rotate keys
  - Show last 4 chars only (click to reveal)
  - Usage stats per key
- **Site Registration:**
  - Domain verification (DNS TXT record or meta tag)
  - CORS configuration
  - Email template customization
- **Code Examples:**
  - Tabs for different languages/frameworks
  - Copy-paste ready snippets
  - Links to full docs

---

## 4️⃣ **ANALYTICS**

**Purpose:** Usage insights and verification metrics

### **Layout:**

```
┌─ Analytics ──────────────────────────────────────┐
│                                                   │
│  📅 DATE RANGE: [Last 30 days ▼]                  │
│                                                   │
│  📊 USAGE METRICS                                 │
│  ┌────────────────────────────────────────┐      │
│  │ Monthly Active Users (MAU)             │      │
│  │ ━━━━━━━━━━━━━━━━━━━━━ 1,234          │      │
│  │ Chart: MAU growth over time            │      │
│  └────────────────────────────────────────┘      │
│                                                   │
│  ┌────────────────────────────────────────┐      │
│  │ Total Verifications: 15,234            │      │
│  │ Avg verification time: 68µs            │      │
│  │ Success rate: 99.8%                    │      │
│  └────────────────────────────────────────┘      │
│                                                   │
│  🌍 VERIFICATION BY SITE                          │
│  ┌────────────────────────────────────────┐      │
│  │ myapp.com        │ 12,456 │ 81.8%      │      │
│  │ staging.myapp.com│  2,778 │ 18.2%      │      │
│  └────────────────────────────────────────┘      │
│                                                   │
│  ⏱️  PERFORMANCE TIMELINE                         │
│  ┌────────────────────────────────────────┐      │
│  │ Chart: Avg verification time (µs)      │      │
│  │ Shows 63µs - 180µs range               │      │
│  └────────────────────────────────────────┘      │
│                                                   │
│  [Export Data (CSV)] [Download Report (PDF)]     │
│                                                   │
└───────────────────────────────────────────────────┘
```

### **Features:**
- **Date Range Selector:** Last 7/30/90 days, custom range
- **MAU Tracking:** Current month + trend graph
- **Verification Stats:**
  - Total verifications
  - Success vs failed
  - Avg verification time
  - Peak usage times
- **Site Breakdown:** Metrics per registered domain
- **Export:** CSV for raw data, PDF for reports

---

## 5️⃣ **SETTINGS**

**Purpose:** Platform configuration and account management

### **Layout:**

```
┌─ Settings ───────────────────────────────────────┐
│                                                   │
│  [Account] [Security] [Email Templates]           │
│  [Branding] [Billing] [Advanced]                  │
│                                                   │
│  ═══ ACCOUNT TAB ═══════════════════════════      │
│                                                   │
│  👤 PROFILE                                       │
│  Email: [jedmckenna@lemma.id]                     │
│  Company: [Lemma Inc.]                            │
│  [Save Changes]                                   │
│                                                   │
│  🔐 SECURITY                                      │
│  Two-Factor Auth: [Enabled ✓] [Configure]        │
│  Password: [••••••••] [Change]                    │
│  Active Sessions: 2 devices [View All]            │
│                                                   │
│  📧 EMAIL TEMPLATES                               │
│  ┌─────────────────────────────────────┐         │
│  │ Confirmation Email:                 │         │
│  │ [Edit Template]                     │         │
│  │ Preview: "Welcome to {site_name}..."│         │
│  └─────────────────────────────────────┘         │
│                                                   │
│  🎨 BRANDING                                      │
│  Logo: [Upload] (shows in email/wallet)           │
│  Primary Color: [#667eea]                         │
│  [Save Branding]                                  │
│                                                   │
│  💳 BILLING (Beta: FREE)                          │
│  Current Plan: Beta (Unlimited)                   │
│  Pricing after beta: $0.08-$0.10 per MAU          │
│  (1/3 the cost of Auth0 Professional)             │
│  [Add Payment Method] (for post-beta)             │
│                                                   │
│  ⚙️  ADVANCED                                     │
│  Webhook URL: [https://myapp.com/lemma-webhook]   │
│  Revocation Sync: [Enabled] Every 7 days          │
│  Debug Mode: [Disabled]                           │
│                                                   │
└───────────────────────────────────────────────────┘
```

### **Features:**
- **Account:** Basic profile info
- **Security:** 2FA, password, session management
- **Email Templates:** Customize confirmation emails
- **Branding:** Logo and colors for wallet/emails
- **Billing:** Payment methods (inactive during beta)
- **Advanced:** Webhooks, sync intervals, debug settings

---

## 6️⃣ **DOCUMENTATION**

**Purpose:** Help developers integrate successfully

### **Layout:**

```
┌─ Documentation ──────────────────────────────────┐
│                                                   │
│  🚀 QUICK START                                   │
│  1. Register your site                            │
│  2. Get your API key                              │
│  3. Add SDK to your HTML                          │
│  4. Initialize and go!                            │
│  [Step-by-step Guide →]                           │
│                                                   │
│  📚 GUIDES                                        │
│  • Email Confirmation Flow                        │
│  • Permission Levels Explained                    │
│  • Local Verification (Offline)                   │
│  • Revocation & Security                          │
│  • Migration from Auth0/Okta                      │
│                                                   │
│  🔌 SDK REFERENCE                                 │
│  • JavaScript SDK                                 │
│  • React Components                               │
│  • Node.js Backend                                │
│  • Python Backend                                 │
│                                                   │
│  🛠️  API REFERENCE                                │
│  • REST API Endpoints                             │
│  • WebSocket Events                               │
│  • Rate Limits                                    │
│  • Error Codes                                    │
│                                                   │
│  💡 EXAMPLES                                      │
│  • Simple Login Page                              │
│  • Protected Dashboard                            │
│  • Multi-Site Setup                               │
│  • Custom Permission Levels                       │
│                                                   │
│  🆘 SUPPORT                                       │
│  [Contact Support] [Community Forum]              │
│                                                   │
└───────────────────────────────────────────────────┘
```

---

## 🛡️ **PLATFORM ADMIN (Your Use Case)**

**Purpose:** Manage lemma.id platform users and beta program

### **Separate Admin Section (Requires super_admin permission)**

```
┌─ Platform Admin ─────────────────────────────────┐
│                                                   │
│  📊 PLATFORM OVERVIEW                             │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐            │
│  │ Total│ │ Beta │ │Active│ │Sites │            │
│  │Users │ │Users │ │ MAU  │ │  125 │            │
│  │ 1,456│ │  892 │ │4,234 │ │      │            │
│  └──────┘ └──────┘ └──────┘ └──────┘            │
│                                                   │
│  👥 ALL LEMMA.ID USERS                            │
│  ┌─────────────────────────────────────────┐     │
│  │Email           │Permission│Joined │[...]│     │
│  ├─────────────────────────────────────────┤     │
│  │user@gmail.com  │beta-user │Jan 15│[⚙️] │     │
│  │dev@company.com │beta-user │Jan 14│[⚙️] │     │
│  └─────────────────────────────────────────┘     │
│                                                   │
│  [+ Issue Admin Credential]                       │
│  [Bulk Actions ▼] [Export All Users]             │
│                                                   │
│  📈 PLATFORM ANALYTICS                            │
│  • Total verifications across all sites           │
│  • Top sites by usage                             │
│  • Geographic distribution                        │
│  • Performance metrics                            │
│                                                   │
│  ⚙️  PLATFORM SETTINGS                            │
│  • Beta program config                            │
│  • Default permission levels                      │
│  • System-wide announcements                      │
│  • Feature flags                                  │
│                                                   │
└───────────────────────────────────────────────────┘
```

### **Admin Features:**
- **View all users** across the platform (not just your sites)
- **Issue/revoke admin permissions** for lemma.id
- **Manage beta program**:
  - Approve beta signups
  - Set beta limits
  - Send beta announcements
- **Platform analytics**:
  - System-wide MAU
  - Total sites using Lemma
  - Performance benchmarks
- **System configuration**:
  - Default settings for new users
  - Feature flags (enable/disable features)

---

## 🎨 **VISUAL DESIGN SYSTEM**

### **Colors (Consistent with lemma.css):**
- Primary: `#667eea` (solid, no gradients)
- Success: `#10b981`
- Warning: `#f59e0b`
- Danger: `#ef4444`
- Background: `#ffffff` (cards), `#f9fafb` (page)

### **Typography:**
- Headings: Inter/System fonts, bold
- Body: 16px, line-height 1.5
- Code: Monospace, `#1e293b` on `#f1f5f9` background

### **Layout:**
- Sidebar nav (240px) + main content area
- Card-based UI (border-radius: 12px)
- Consistent spacing (8px grid)
- Responsive breakpoints: 768px (tablet), 1024px (desktop)

---

## 🚀 **IMPLEMENTATION PRIORITY**

### **Phase 1: Beta Launch (This Week)**
1. ✅ Overview page (basic stats)
2. ✅ Users & Permissions (list + issue)
3. ✅ API Keys (create/view)
4. ✅ Quick Integration code snippet

### **Phase 2: Post-Beta (Next 2 Weeks)**
5. Analytics page
6. Settings (email templates, branding)
7. Documentation pages
8. Platform Admin section (for you)

### **Phase 3: Scale Features (Month 2)**
9. Advanced analytics (charts, export)
10. Bulk operations
11. Webhook configuration
12. Billing integration (Stripe)

---

## 📝 **KEY FEATURES TO INCLUDE**

✅ **Must Have (Beta):**
- User list with search
- Issue/revoke permissions
- API key generation
- Basic usage stats
- Integration code snippet

⏱️ **Should Have (Post-Beta):**
- Charts and visualizations
- Email template customization
- Webhook setup
- Detailed analytics

🎯 **Nice to Have (Later):**
- Real-time dashboards
- A/B testing features
- Custom permission types builder
- Migration tools from other auth providers

---

**Next Steps:** Shall I implement the Phase 1 dashboard (Overview + Users & Permissions + API Keys + Integration)?

