# Lemma.id Platform Restructure Plan

## Overview

Restructuring the Lemma.id platform from a monolithic Flask/Jinja application into a unified, well-organized design with clear separation between:
1. **Public/Marketing** - Landing pages, pricing, docs
2. **Wallet** - User wallet management (accessible to all users)
3. **Developer Platform** - Site management, API keys, integration (for developers)
4. **Admin Platform** - Platform administration (for Lemma staff)

## Progress Summary

### Day 1: Developer Platform Split - COMPLETED

**Files Created:**
- `templates/developer/layout.html` - Shared layout with sidebar navigation
- `templates/developer/overview.html` - Dashboard with stats, getting started
- `templates/developer/sites/list.html` - Sites list with create modal
- `templates/developer/sites/detail.html` - Site dashboard with tabs
- `static/css/developer.css` - Developer platform styles
- `api/developer_api.py` - Backend API for developer data

**Routes Added:**
- `/developer` - Overview dashboard
- `/developer/sites` - Sites list
- `/developer/sites/<site_id>` - Site detail (overview)
- `/developer/sites/<site_id>/integration` - Integration guide
- `/developer/sites/<site_id>/keys` - API keys
- `/developer/sites/<site_id>/users` - Users
- `/developer/sites/<site_id>/settings` - Settings
- `/developer/usage` - Usage analytics
- `/developer/billing` - Billing (redirects to pricing)
- `/developer/settings` - Account settings
- `/platform` → `/developer` (legacy redirect)

**Status:** Deployed to production (lemma.id)

---

## Remaining Work

### Day 2: Wallet Enhancement - COMPLETED

**Goal:** Keep wallet as a unified "control center" - improve UX without segmentation

**Design Philosophy:**
The wallet is intentionally a single-page experience for non-technical users:
- Everything visible at a glance
- No navigation complexity
- Simple, clear actions

**Completed:**
- [x] Extracted inline CSS to `static/css/wallet.css` (193 lines → external file)
- [x] Added responsive styles for mobile
- [x] Preserved all functionality (no backend changes)
- [x] Tested locally and on production

**Files Changed:**
- `templates/wallet_simple.html` - Removed inline styles, added CSS link
- `static/css/wallet.css` - New external stylesheet

**Status:** Deployed to production (lemma.id/wallet)

---

### Day 3: Admin Dashboard

**Goal:** Create proper admin platform for Lemma staff

**Current State:**
- `templates/admin/platform_monitoring.html` - Basic monitoring
- `templates/modern/admin_bootstrap.html` - Bootstrap page

**Target Structure:**
```
templates/admin/
├── layout.html          # Admin layout with sidebar
├── dashboard.html       # Overview (platform stats, health)
├── users.html           # All platform users
├── sites.html           # All registered sites
├── analytics.html       # Platform-wide analytics
├── logs.html            # Audit logs
└── settings.html        # Platform settings
```

**Tasks:**
- [ ] Create `templates/admin/layout.html` with admin navigation
- [ ] Create admin dashboard page
- [ ] Create users management page
- [ ] Create sites overview page
- [ ] Create `static/css/admin.css` for admin-specific styles
- [ ] Update routes in app.py
- [ ] Ensure admin routes require admin lemma

---

### Day 4: Marketing Polish

**Goal:** Clean up public-facing pages

**Current State:**
- `templates/modern/index.html` (~500 lines) - Homepage
- `templates/modern/pricing_new.html` - Pricing page
- `templates/modern/docs_iam.html` - Documentation

**Target Structure:**
```
templates/marketing/
├── layout.html          # Marketing layout (different from app layouts)
├── index.html           # Homepage (simplified)
├── pricing.html         # Pricing page
├── features.html        # Features overview
├── about.html           # About Lemma
└── contact.html         # Contact page

templates/docs/
├── layout.html          # Docs layout with sidebar
├── getting-started.html # Getting started guide
├── sdk-reference.html   # SDK documentation
├── api-reference.html   # API documentation
└── examples.html        # Code examples
```

**Tasks:**
- [ ] Simplify index.html (remove bloat)
- [ ] Create proper docs site with navigation
- [ ] Ensure consistent styling across marketing pages
- [ ] Update footer links and navigation

---

### Day 5: Routes & Testing

**Goal:** Clean up routes and test all flows

**Tasks:**
- [ ] Audit all routes in app.py
- [ ] Remove deprecated routes
- [ ] Update navigation links across all pages
- [ ] Test all user flows:
  - [ ] Anonymous → Marketing pages
  - [ ] Anonymous → Wallet creation
  - [ ] User → Wallet management
  - [ ] Developer → Developer platform
  - [ ] Admin → Admin platform
- [ ] Performance testing
- [ ] Mobile responsiveness check

---

## URL Structure

### Public (No Auth)
| URL | Description |
|-----|-------------|
| `/` | Homepage |
| `/pricing` | Pricing page |
| `/docs` | Documentation hub |
| `/docs/getting-started` | Getting started guide |
| `/docs/sdk` | SDK reference |
| `/docs/api` | API reference |
| `/terms` | Terms of service |
| `/privacy` | Privacy policy |

### Wallet (Wallet Auth)
| URL | Description |
|-----|-------------|
| `/wallet` | **Single-page control center** (credentials, devices, security, settings) |
| `/wallet/unlock` | Unlock page (redirect flow - returns to requesting site) |
| `/wallet/link` | Device linking (scanned from QR code) |
| `/wallet/bridge` | Cross-origin bridge (iframe for third-party sites) |
| `/wallet/popup` | Popup unlock (alternative to redirect) |

*Note: The wallet is intentionally NOT split into multiple pages. Non-technical users benefit from a unified view where everything is accessible without navigation.*

### Developer Platform (Developer Credential)
| URL | Description |
|-----|-------------|
| `/developer` | Overview dashboard |
| `/developer/sites` | Sites list |
| `/developer/sites/new` | Create site |
| `/developer/sites/:id` | Site dashboard |
| `/developer/sites/:id/integration` | Integration guide |
| `/developer/sites/:id/keys` | API keys |
| `/developer/sites/:id/users` | Site users |
| `/developer/sites/:id/settings` | Site settings |
| `/developer/usage` | Usage analytics |
| `/developer/billing` | Billing |
| `/developer/settings` | Account settings |

### Admin Platform (Admin Credential)
| URL | Description |
|-----|-------------|
| `/admin` | Admin dashboard |
| `/admin/users` | All platform users |
| `/admin/sites` | All sites |
| `/admin/analytics` | Platform analytics |
| `/admin/logs` | Audit logs |
| `/admin/settings` | Platform settings |
| `/admin/bootstrap` | Admin credential bootstrap |

---

## Access Control Summary

| Page Type | Required Credential | Notes |
|-----------|-------------------|-------|
| Marketing | None | Public access |
| Wallet | Wallet unlocked | Passkey-protected |
| Developer | Developer permission or site owner | PPID-based |
| Admin | Admin/super_admin permission | Lemma staff only |

---

## Files to Clean Up (After Restructure)

These files can be removed or deprecated once the restructure is complete:

- `templates/developer/platform.html` (2986 lines) → Replaced by split pages
- Old dashboard templates (if any)
- Duplicate CSS files
- Unused JavaScript files

---

## Technical Notes

### Authentication Flow
1. All pages extend `modern/layout.html` which loads the wallet SDK
2. SDK auto-attaches auth headers to fetch requests
3. Backend decorators check credentials:
   - `@require_wallet_ppid` - Requires wallet unlock
   - `@require_permission_lemma` - Requires specific permission
   - `@require_site_admin` - Requires admin credential

### CSS Architecture
- `static/css/lemma.css` - Global styles (colors, typography, base components)
- `static/css/developer.css` - Developer platform specific
- `static/css/wallet.css` - Wallet specific (to be created)
- `static/css/admin.css` - Admin specific (to be created)
- `static/css/marketing.css` - Marketing specific (to be created)

### API Structure
- `/api/developer/*` - Developer platform APIs
- `/api/wallet/*` - Wallet APIs  
- `/api/admin/*` - Admin APIs
- `/api/v1/*` - Public SDK APIs

---

## Estimated Timeline

| Phase | Effort | Status |
|-------|--------|--------|
| Day 1: Developer Platform | 4 hours | ✅ COMPLETED |
| Day 2: Wallet Enhancement | 1 hour | ✅ COMPLETED |
| Day 3: Admin Dashboard | 3 hours | Pending |
| Day 4: Marketing Polish | 2 hours | Pending |
| Day 5: Routes & Testing | 2 hours | Pending |

**Total estimated remaining: ~7 hours**

---

## Next Steps

1. **Wallet Enhancement (Day 2):**
   - Review `wallet_simple.html` for cleanup opportunities
   - Extract inline styles to `static/css/wallet.css`
   - Improve visual organization (sections, collapsibles)
   - Keep as single-page control center

2. **Priority Order:**
   - Wallet polish (users interact with this most)
   - Admin pages (internal tooling)
   - Marketing polish (lower priority)
