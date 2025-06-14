# Lemma Enterprise - Complete Site Map & Page Layout

## 🏠 **Main Entry Points**

### **Landing Page (`/`)**
- **File:** `templates/index.html`
- **Purpose:** Main marketing page and entry point
- **Key Actions:**
  - "Verify Lemma" → Human verification flow
  - "Access Protected Content" → Protected area access
  - "Customer Onboarding" → Business registration

---

## 👥 **Customer Onboarding Flow**

### **1. Onboarding Start (`/onboarding`)**
- **File:** `templates/onboarding/start.html`
- **Purpose:** Marketing landing for business customers
- **Features:** Pricing information, value propositions

### **2. Registration (`/onboarding/register`)**
- **File:** `templates/onboarding/register.html`
- **Purpose:** Business account registration
- **Form Fields:** Email, company name, domain
- **Validation:** Email format, domain verification

### **3. Domain Verification (`/onboarding/verify`)**
- **File:** `templates/onboarding/verify.html`
- **Purpose:** Verify domain ownership
- **Methods:**
  - DNS TXT record: `_lemma-verification.domain.com`
  - HTML meta tag on homepage
- **Features:** Auto-polling, real-time status updates

### **4. Customer Dashboard (`/onboarding/dashboard`)**
- **File:** `templates/onboarding/dashboard.html`
- **Purpose:** Main customer control panel
- **Sections:**
  - Usage statistics and costs
  - Quick start integration
  - Pricing calculator
  - Account management

### **5. API Key Management (`/onboarding/api-keys`)**
- **File:** `templates/onboarding/api_keys.html`
- **Purpose:** Secure API key management
- **Features:**
  - View/hide API keys
  - Regenerate keys
  - Integration examples
  - Security best practices

### **6. Usage Analytics (`/onboarding/usage`)**
- **File:** `templates/onboarding/usage.html`
- **Purpose:** Detailed usage tracking and analytics
- **Features:**
  - Daily/weekly/monthly breakdowns
  - Cost projections
  - Data export (CSV/JSON)
  - Usage insights

### **7. Integration Guide (`/onboarding/integration`)**
- **File:** `templates/onboarding/integration.html`
- **Purpose:** Complete developer integration guide
- **Sections:**
  - React integration (hooks, HOCs, components)
  - Express.js backend middleware
  - Raw API examples
  - Testing checklist

---

## 🔐 **Core Verification Flow**

### **Human Verification (`/verify`)**
- **File:** `templates/verify.html` (legacy, redirects to main flow)
- **Purpose:** Human verification process
- **Flow:** Stripe Identity → Credential issuance → Storage

### **Protected Content (`/protected`)**
- **Purpose:** Content requiring human verification
- **Features:**
  - Credential validation
  - Session management
  - Credential import/export

---

## 👨‍💼 **Admin Section**

### **Admin Login (`/admin/login`)**
- **File:** `templates/admin_login.html`
- **Purpose:** Secure admin authentication
- **Security:** Password hashing, CSRF protection

### **Admin Dashboard (`/admin`)**
- **File:** `templates/admin.html`
- **Purpose:** System administration
- **Features:**
  - Credential issuance
  - User management
  - System monitoring

---

## 💰 **Billing System**

### **Invoices (`/billing/invoices`)**
- **File:** `templates/billing/invoices.html`
- **Purpose:** Invoice management and viewing

### **Payment Methods (`/billing/payment-methods`)**
- **File:** `templates/billing/payment_methods.html`
- **Purpose:** Payment method management

### **Identity Complete (`/billing/identity-complete`)**
- **File:** `templates/billing/identity_complete.html`
- **Purpose:** Post-verification billing setup

---

## 🧪 **Demo & Testing Pages**

### **Gate Demo (`/gate-demo`)**
- **File:** `templates/gate_demo.html`
- **Purpose:** Agent network demonstration
- **Features:** Interactive agent verification demo

### **Widget Test (`/widget-test`)**
- **Purpose:** Integration widget testing
- **Features:** Live widget demonstration

### **API Documentation (`/api-docs`)**
- **Purpose:** Interactive API documentation
- **Features:** OpenAPI specification, live testing

---

## 🔧 **API Endpoints Structure**

### **Core API (`/api/*`)**
```
/api/health                    - System health check
/api/generate-challenge        - Authentication challenge
/api/verify-credential         - Credential verification
/api/issue-credential          - Credential issuance
/api/verify-presentation       - Presentation verification
/api/logout                    - Session management
/api/generate-csrf             - CSRF token generation
```

### **SRE Monitoring (`/api/sre/*`)**
```
/api/sre/dashboard/metrics     - Main SRE dashboard
/api/sre/metrics/latency       - Performance metrics
/api/sre/metrics/errors        - Error tracking
/api/sre/metrics/prometheus    - Prometheus export
/api/sre/alerts/current        - Active alerts
/api/sre/alerts/history        - Alert history
/api/sre/collect/*             - Metrics collection
```

### **Billing API (`/api/billing/*`)**
```
/api/billing/usage/monthly     - Monthly usage metrics
/api/billing/usage/daily       - Daily usage metrics
/api/billing/invoice/*         - Invoice management
/api/billing/webhook/*         - Webhook handlers
/api/billing/disputes          - Dispute management
/api/billing/health            - Billing system health
```

### **Compliance API (`/api/compliance/*`)**
```
/api/compliance/dashboard      - Compliance overview
/api/compliance/api-keys       - Key lifecycle management
/api/compliance/data-protection - GDPR/CCPA compliance
/api/compliance/incidents      - Incident response
/api/compliance/audits         - Audit management
/api/compliance/reports/*      - Compliance reporting
```

### **Sandbox API (`/api/sandbox/*`)**
```
/api/sandbox/status            - Sandbox health
/api/sandbox/credentials       - Test credentials
/api/sandbox/kyc/verify        - Test KYC verification
/api/sandbox/revocation/*      - Test revocation events
/api/sandbox/test-scenarios    - Test scenario management
```

---

## 🎯 **User Journey Flows**

### **Business Customer Journey**
1. **Discovery:** Landing page (`/`)
2. **Registration:** Onboarding start (`/onboarding`)
3. **Account Setup:** Registration (`/onboarding/register`)
4. **Domain Verification:** Verify ownership (`/onboarding/verify`)
5. **Dashboard Access:** Main control panel (`/onboarding/dashboard`)
6. **Integration:** API keys and guides (`/onboarding/api-keys`, `/onboarding/integration`)
7. **Monitoring:** Usage analytics (`/onboarding/usage`)

### **End User Journey**
1. **Entry:** Customer's website with Lemma integration
2. **Verification:** Human verification (`/verify`)
3. **Access:** Protected content (`/protected`)
4. **Credential Management:** Import/export, cross-device use

### **Developer Journey**
1. **Documentation:** API docs (`/api-docs`)
2. **Testing:** Widget demo (`/gate-demo`, `/widget-test`)
3. **Integration:** Code samples and guides
4. **Sandbox:** Test environment (`/api/sandbox/*`)

### **Admin Journey**
1. **Authentication:** Admin login (`/admin/login`)
2. **Management:** Admin dashboard (`/admin`)
3. **Operations:** Credential issuance, user management
4. **Monitoring:** System health and metrics

---

## 🎨 **Layout & Design System**

### **Base Layout (`templates/layout.html`)**
- **Stripe-inspired design system**
- **Responsive mobile-first design**
- **WCAG accessibility compliance**
- **Common components:** Navigation, footer, alerts

### **Design Components**
- **Colors:** Stripe palette (#635bff primary)
- **Typography:** System-UI fonts, 16px base
- **Spacing:** 8-point grid system
- **Components:** 44px buttons, focus rings, cards
- **Motion:** "Swift out" easing, 150ms hovers

---

## 🔒 **Security & Error Handling**

### **Error Pages (`/error`)**
- **File:** `templates/error.html`
- **Purpose:** Centralized error handling
- **Features:** Clean error messaging, proper HTTP codes

### **Security Features**
- **CSRF Protection:** All forms protected
- **Input Validation:** Comprehensive validation
- **Rate Limiting:** API endpoint protection
- **Session Management:** Secure session handling
- **API Authentication:** API key validation

---

## 📊 **Analytics & Monitoring**

### **Client-Side Tracking**
- **Wallet performance monitoring**
- **Error collection and reporting**
- **User interaction analytics**

### **Server-Side Metrics**
- **SRE observability dashboard**
- **Performance monitoring**
- **Error rate tracking**
- **Business metrics (MAH, billing)**

---

## 🌐 **Network Effect Features**

### **Agent Network Support**
- **Cross-platform credential portability**
- **Professional agent workflows**
- **Reputation system foundation**
- **Network-wide verification standard**

This comprehensive site map shows the complete structure of your Lemma Enterprise application, from customer onboarding to enterprise monitoring, all designed to support the vision of becoming the internet's trust infrastructure. 