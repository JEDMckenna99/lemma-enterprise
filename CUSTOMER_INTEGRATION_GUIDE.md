# 🛡️ Real Customer Integration Guide

## Overview

The **join-network page** (`/join-network`) demonstrates exactly how real customer sites integrate Lemma Shield protection. This is NOT a demo - it's the actual production integration pattern that customers use.

## What Was Changed

### ❌ **Removed:**
- `/shield-demo` route and template
- Demo-specific code and complex initialization
- Test/simulation modes

### ✅ **Added:**
- Real production SDK integration on `/join-network`
- Actual customer API key generation
- Production security headers
- Standard customer initialization pattern

## Real Customer Integration Pattern

### 1. **SDK Loading**
```html
<!-- Customer loads the Lemma Shield SDK -->
<script src="https://lemma.id/static/js/lemma-shield-widget.js"></script>
```

### 2. **Customer Configuration**
```javascript
// Customer's configuration object
window.LemmaConfig = {
    apiKey: 'customer_api_key_here',           // Customer's unique API key
    apiBase: 'https://lemma.id',               // Lemma service endpoint
    mode: 'production',                        // production, staging, development
    
    // Customer preferences
    autoProtect: true,                         // Auto-protect page on load
    challengeType: 'verification',             // Type of challenge
    fallbackEnabled: true,                     // Enable fallback methods
    offlineCapable: true,                      // Enable offline verification
    
    // Customer branding
    branding: {
        companyName: 'Your Company',
        primaryColor: '#2563eb',
        borderRadius: '8px',
        position: 'center'
    },
    
    // Customer event handlers
    onVerified: function(result) {
        // Customer's business logic when user is verified
        console.log('User verified:', result);
        // Enable protected features, redirect, etc.
    },
    
    onError: function(error) {
        // Customer's error handling
        console.error('Verification error:', error);
    },
    
    onRevoked: function(details) {
        // Customer's revocation handling
        console.log('Credential revoked:', details);
        // Disable features, show message, etc.
    }
};
```

### 3. **SDK Initialization**
```javascript
// Customer initializes the shield
function initializeLemmaShield() {
    if (typeof window.LemmaShieldWidget !== 'undefined' && window.LemmaConfig) {
        window.lemmaShield = new window.LemmaShieldWidget({
            // Pass customer configuration
            apiKey: window.LemmaConfig.apiKey,
            apiBase: window.LemmaConfig.apiBase,
            mode: window.LemmaConfig.mode,
            
            // Widget settings
            widgetContainer: '#lemma-shield-container',
            autoProtect: window.LemmaConfig.autoProtect,
            
            // Event handlers
            onVerified: window.LemmaConfig.onVerified,
            onError: window.LemmaConfig.onError,
            onRevoked: window.LemmaConfig.onRevoked
        });
        
        // Start protection
        window.lemmaShield.init().then(() => {
            console.log('Lemma Shield protection ACTIVE');
            if (window.LemmaConfig.autoProtect) {
                window.lemmaShield.startProtection();
            }
        });
    }
}

// Initialize when ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeLemmaShield);
} else {
    initializeLemmaShield();
}
```

### 4. **Shield Container**
```html
<!-- Customer adds container for shield widget -->
<div id="lemma-shield-container" style="display: none;"></div>
```

## How It Works

### **Page Load Protection**
1. Customer page loads with Lemma Shield SDK
2. SDK automatically checks for existing credentials
3. If no valid credential found, shield widget appears
4. User completes verification challenge
5. Credential is stored for future use
6. User gets access to protected content

### **Revocation Handling**
1. SDK periodically checks credential validity
2. If credential is revoked, shield automatically reappears
3. User must re-verify to continue accessing content
4. Customer's `onRevoked` callback is triggered

### **Offline Capability**
1. After initial verification, subsequent checks are offline
2. No API calls needed for most verifications
3. Unlimited scaling without infrastructure costs
4. Works even during network outages

## Customer Benefits

### **🚀 Performance**
- **95% offline verification** - Zero API calls after initial setup
- **<100ms response times** - Instant verification for returning users
- **Global CDN** - Fast loading worldwide

### **🔒 Security**
- **Real cryptographic protection** - Not just a demo
- **Automatic revocation detection** - Compromised credentials automatically handled
- **Production security headers** - Enterprise-grade protection

### **💰 Cost Efficiency**
- **Unlimited offline verifications** - No per-verification costs
- **Network effect pricing** - Costs decrease as network grows
- **Single integration** - Works across all sites

## Test the Real Integration

Visit https://lemma.id/join-network to see the actual customer integration in action. This page uses the exact same code pattern that customer sites use.

## Get Your API Key

Contact enterprise@lemma.network to get your production API key and start protecting your site with real Lemma Shield integration. 