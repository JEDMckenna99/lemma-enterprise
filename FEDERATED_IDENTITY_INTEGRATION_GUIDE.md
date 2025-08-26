# Lemma Federated Identity Network - Integration Guide

## Overview
The Lemma Federated Identity Network enables **verify once, access everywhere** authentication across multiple sites using cryptographic proofs. Users complete identity verification once and gain instant access to all network sites without re-verification.

## 🌐 Network Architecture

### Core Components
- **Primary Node**: `https://lemma.id` (Main verification and registry)
- **Federation Endpoints**: Network sites that share credentials
- **Demo Site**: `https://lemma-demo-network-6e372c0643c8.herokuapp.com`

### How It Works
1. User completes **one-time verification** on any network site (Stripe Identity)
2. **Cryptographic credentials** stored locally in browser
3. **Instant authentication** (~1-50µs) on all network sites
4. **Zero personal data** shared between sites (only cryptographic proofs)

---

## 🚀 Quick Integration (3 Steps)

### Step 1: Include Lemma SDK
```html
<!-- Add to your HTML <head> -->
<link rel="stylesheet" href="https://lemma.id/static/css/lemma-verification-card.css">
<script src="https://lemma.id/static/js/lemma-federated-wallet.js"></script>
<script src="https://lemma.id/static/js/lemma-bot-shield-simple.js"></script>
<script src="https://lemma.id/static/js/lemma-verification-card.js"></script>
```

### Step 2: Add Verification Card
```html
<!-- Add anywhere in your page -->
<div id="lemma-card" 
     data-lemma-card 
     data-theme="professional" 
     data-size="normal">
</div>
```

### Step 3: Initialize JavaScript
```javascript
document.addEventListener('DOMContentLoaded', async function() {
    // Initialize Verification Card
    const card = new LemmaVerificationCard('lemma-card', {
        apiKey: 'your-site-api-key',
        apiBase: 'https://lemma.id',
        theme: 'professional',
        onVerified: function(result) {
            console.log('✅ User verified:', result);
            // User is now part of federated network
            showProtectedContent();
        }
    });
    
    // Initialize Federated Wallet (checks for existing credentials)
    const wallet = new LemmaFederatedWallet({
        networkRegistryUrl: 'https://lemma.id/api/network'
    });
    
    await wallet.init();
    
    // Check for existing network credentials
    const hasCredentials = await wallet.hasValidCredentials();
    if (hasCredentials) {
        // User already verified on another network site
        console.log('✅ Network credentials found - instant access');
        showProtectedContent();
    }
});
```

---

## 🛠️ Complete Implementation

### Frontend Integration

#### HTML Structure
```html
<!DOCTYPE html>
<html>
<head>
    <title>Your Site - Lemma Network</title>
    
    <!-- Lemma SDK -->
    <link rel="stylesheet" href="https://lemma.id/static/css/lemma-verification-card.css">
    <script src="https://lemma.id/static/js/lemma-federated-wallet.js"></script>
    <script src="https://lemma.id/static/js/lemma-bot-shield-simple.js"></script>
    <script src="https://lemma.id/static/js/lemma-verification-card.js"></script>
</head>
<body>
    <!-- Network Status -->
    <div id="network-status"></div>
    
    <!-- Verification Card -->
    <div id="verification-card" 
         data-lemma-card 
         data-theme="professional" 
         data-size="normal">
    </div>
    
    <!-- Protected Content -->
    <div id="protected-content" style="display: none;">
        <h2>🎉 Welcome to the Network!</h2>
        <p>You have access to all federated sites.</p>
    </div>
</body>
</html>
```

#### JavaScript Implementation
```javascript
class FederatedSiteManager {
    constructor() {
        this.wallet = null;
        this.card = null;
        this.isVerified = false;
    }
    
    async init() {
        try {
            // Initialize Federated Wallet
            this.wallet = new LemmaFederatedWallet({
                debug: true,
                networkRegistryUrl: 'https://lemma.id/api/network'
            });
            
            await this.wallet.init();
            
            // Check for existing credentials
            const hasCredentials = await this.wallet.hasValidCredentials();
            if (hasCredentials) {
                this.handleVerified();
                return;
            }
            
            // Initialize Verification Card
            this.card = new LemmaVerificationCard('verification-card', {
                apiKey: 'your-api-key',
                apiBase: 'https://lemma.id',
                theme: 'professional',
                onVerified: (result) => this.handleVerified(result),
                onError: (error) => this.handleError(error)
            });
            
            await this.card.init();
            
        } catch (error) {
            console.error('❌ Initialization error:', error);
            this.updateNetworkStatus(false);
        }
    }
    
    handleVerified(result = null) {
        this.isVerified = true;
        this.showProtectedContent();
        this.updateNetworkStatus(true);
        
        console.log('✅ User verified and connected to network');
    }
    
    handleError(error) {
        console.error('❌ Verification error:', error);
        this.updateNetworkStatus(false);
    }
    
    showProtectedContent() {
        document.getElementById('protected-content').style.display = 'block';
        // Add your protected content logic here
    }
    
    updateNetworkStatus(isConnected) {
        const statusEl = document.getElementById('network-status');
        if (isConnected) {
            statusEl.innerHTML = '✅ Connected to Lemma Network';
            statusEl.className = 'network-connected';
        } else {
            statusEl.innerHTML = '⚠️ Not connected to network';
            statusEl.className = 'network-disconnected';
        }
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    const siteManager = new FederatedSiteManager();
    siteManager.init();
});
```

### Backend Integration (Optional)

#### Flask Example
```python
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

@app.route('/api/verify-network-credential', methods=['POST'])
def verify_network_credential():
    """Verify a federated network credential"""
    credential = request.json.get('credential')
    
    # Verify with Lemma network
    response = requests.post('https://lemma.id/api/verify', {
        'credential': credential,
        'site_id': 'your-site-id'
    })
    
    if response.status_code == 200:
        return jsonify({'verified': True, 'user_id': response.json()['user_id']})
    else:
        return jsonify({'verified': False}), 400

@app.route('/api/protected-data')
def protected_data():
    """Endpoint that requires network verification"""
    # Check for network credential in request
    auth_header = request.headers.get('Authorization')
    
    if not auth_header or not verify_network_token(auth_header):
        return jsonify({'error': 'Network verification required'}), 401
    
    return jsonify({'data': 'Protected content for verified users'})
```

---

## 🔧 Configuration Options

### Verification Card Themes
```javascript
// Available themes
const themes = [
    'professional',  // Purple gradient (default)
    'minimal',      // Clean white
    'dark',         // Dark mode
    'branded'       // Your brand colors
];

// Custom theme
const customTheme = {
    container: 'background: #your-color; border: 2px solid #your-border;',
    button: 'background: #your-button-color;',
    // ... other styles
};
```

### Size Options
```javascript
const sizes = [
    'compact',   // Small card
    'normal',    // Default size
    'large'      // Prominent display
];
```

### Advanced Configuration
```javascript
const config = {
    apiKey: 'your-api-key',
    apiBase: 'https://lemma.id',
    theme: 'professional',
    size: 'normal',
    showStatus: true,
    showLogo: true,
    autoVerify: false,
    debugMode: true,
    networkTimeout: 5000,
    retryAttempts: 3
};
```

---

## 🌍 Network Registration

### Register Your Site
To join the federated network, your site needs to be added to the network registry:

1. **Contact Lemma**: Request network registration
2. **Provide Details**:
   - Site URL: `https://yoursite.com`
   - Site Name: "Your Site Name"
   - Contact Email: your-email@domain.com
   - Integration Type: "Federated Identity"

3. **Receive API Key**: You'll get a unique API key for your site
4. **Network Addition**: Your site will be added to the federation endpoints

### Current Network Sites
```javascript
const networkSites = [
    'https://lemma.id',                                    // Primary node
    'https://lemma-identity-network-2d96786d6ffb.herokuapp.com',  // Testing node
    'https://lemma-demo-network-6e372c0643c8.herokuapp.com'      // Demo site
    // Your site will be added here
];
```

---

## 🛡️ Security & Privacy

### Data Protection
- **Zero Personal Data Storage**: Only cryptographic proofs are shared
- **Local Credential Storage**: User credentials stored in browser only
- **No Cross-Site Tracking**: Sites cannot access other sites' data
- **Cryptographic Verification**: Mathematical proof of identity without revealing details

### Security Features
- **Ed25519 Signatures**: Industry-standard cryptographic signatures
- **Zero-Knowledge Proofs**: Prove identity without revealing information
- **OPRF (Oblivious PRF)**: Privacy-preserving verification
- **Bloom Filters**: Efficient revocation checking

### Performance
- **Microsecond Authentication**: ~1-50µs for network users
- **One-time Verification**: Initial verification ~500ms (Stripe Identity)
- **Offline Capable**: Credentials work without network connectivity
- **CDN Distributed**: Fast SDK loading worldwide

---

---

## ✅ **CORS Issues Fixed!**

**Previous Issue**: Cross-origin requests to federated network APIs were blocked by CORS policy.

**Resolution**: All critical network API endpoints now include proper CORS headers:
- `/api/network/sync/check-shared-identity` ✅ 
- `/api/privacy/generate-ppid` ✅
- `/api/network/did-registry` ✅
- `/api/network/sync/add-identity-lemma` ✅

**Result**: Identity lemmas can now be shared and verified across all federated network sites!

---

## 🚨 Troubleshooting

### Common Issues

#### SDK Not Loading
```javascript
// Check if scripts loaded
if (typeof LemmaVerificationCard === 'undefined') {
    console.error('❌ LemmaVerificationCard not loaded');
    // Fallback or retry logic
}
```

#### Network Connection Issues
```javascript
// Test network connectivity
async function testNetworkConnection() {
    try {
        const response = await fetch('https://lemma.id/api/health');
        return response.ok;
    } catch (error) {
        console.error('❌ Network connection failed:', error);
        return false;
    }
}
```

#### Credential Verification Failures
```javascript
// Handle verification errors
const card = new LemmaVerificationCard('card', {
    onError: function(error) {
        console.error('❌ Verification failed:', error);
        
        if (error.code === 'NETWORK_TIMEOUT') {
            // Retry logic
        } else if (error.code === 'INVALID_CREDENTIAL') {
            // Clear stored credentials and restart
        }
    }
});
```

### Debug Mode
```javascript
// Enable debug logging
const config = {
    debugMode: true,
    // ... other config
};

// Check browser console for detailed logs:
// 🚀 Initializing Lemma...
// ✅ Network credentials found
// 🔧 Verification card rendered
// 🛡️ Bot Shield active
```

---

## 📚 API Reference

### LemmaVerificationCard
```javascript
class LemmaVerificationCard {
    constructor(elementId, config);
    async init();
    async verify();
    destroy();
    
    // Events
    onVerified(callback);
    onError(callback);
    onStatusChange(callback);
}
```

### LemmaFederatedWallet
```javascript
class LemmaFederatedWallet {
    constructor(options);
    async init();
    async hasValidCredentials();
    async storeCredential(credential);
    async getCredential();
    async clearCredentials();
    
    // Network methods
    async syncWithNetwork();
    async checkNetworkStatus();
}
```

### LemmaBotShield
```javascript
class LemmaBotShield {
    constructor(options);
    async init();
    async protect(element);
    async verify();
    
    // Security levels
    setSecurityLevel('low' | 'medium' | 'high');
}
```

---

## 🎯 Example Use Cases

### E-commerce Site
```javascript
// Protect checkout process
const shield = new LemmaBotShield({
    securityLevel: 'high',
    protectedRoutes: ['/checkout', '/account']
});

// Show instant checkout for verified users
if (await wallet.hasValidCredentials()) {
    showExpressCheckout();
}
```

### Content Platform
```javascript
// Protect premium content
document.querySelectorAll('.premium-content').forEach(element => {
    if (!isVerified) {
        element.style.display = 'none';
        showVerificationCard();
    }
});
```

### SaaS Application
```javascript
// Skip lengthy signup for network users
if (await wallet.hasValidCredentials()) {
    const userProfile = await wallet.getNetworkProfile();
    autoCreateAccount(userProfile);
    redirectToDashboard();
} else {
    showSignupForm();
}
```

---

## 🔗 Resources

### Documentation
- **Main Docs**: https://lemma.id/docs
- **API Reference**: https://lemma.id/docs/api
- **Network Status**: https://lemma.id/network/status

### Support
- **GitHub Issues**: Report bugs and feature requests
- **Email**: support@lemma.id
- **Demo Site**: https://lemma-demo-network-6e372c0643c8.herokuapp.com

### Network Statistics
- **Authentication Speed**: ~1-50µs
- **Network Uptime**: 99.9%+
- **Active Sites**: Growing federated network
- **Verification Success Rate**: >99%

---

## ✅ Integration Checklist

- [ ] Include Lemma SDK scripts in HTML
- [ ] Add verification card to your page
- [ ] Initialize JavaScript components
- [ ] Handle verified/unverified states
- [ ] Test cross-site authentication
- [ ] Register site with network
- [ ] Configure protected content
- [ ] Add error handling
- [ ] Test in production environment
- [ ] Monitor network connectivity

---

**Ready to join the federated identity network? Follow this guide and your users will experience seamless, privacy-preserving authentication across all network sites!** 🚀
