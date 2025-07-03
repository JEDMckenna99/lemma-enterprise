# 🛡️ Lemma Shield Integration Guide

**Simple, Production-Ready Integration in 3 Steps**

Integrate Lemma's three-flow verification circuit (CHECK → SHIELD → REVOCATION) with just a few lines of code.

## 📋 **Prerequisites**

1. **API Key**: Get your API key from [lemma.id/onboarding/api-keys](https://lemma.id/onboarding/api-keys)
2. **Domain Verification**: Verify your domain at [lemma.id/onboarding/domain-verification](https://lemma.id/onboarding/domain-verification)

## 🚀 **Basic Integration (5 Minutes)**

### **Step 1: Add HTML Container**

Add a container where the shield will appear:

```html
<!DOCTYPE html>
<html>
<head>
    <title>My Protected Site</title>
</head>
<body>
    <!-- Shield Container - Shows for unverified users -->
    <div id="lemma-shield"></div>
    
    <!-- Your protected content -->
    <div id="protected-content" class="protected-content lemma-protected">
        <h1>Welcome to my protected site!</h1>
        <p>This content is protected by Lemma Shield.</p>
    </div>
</body>
</html>
```

### **Step 2: Add CSS Protection (Optional)**

Add CSS to blur content until verified:

```css
/* Protection styling - content blurred until verified */
.protected-content {
    transition: opacity 0.3s ease, filter 0.3s ease;
}

.protected-content.lemma-protected {
    opacity: 0.3;
    filter: blur(2px);
    pointer-events: none;
}
```

### **Step 3: Initialize Lemma Shield**

Add the Lemma Shield script and initialize:

```html
<!-- Load Lemma Shield Widget -->
<script src="https://lemma.id/static/js/lemma-shield-widget.js"></script>

<script>
// Initialize Lemma Shield - PRODUCTION READY
document.addEventListener('DOMContentLoaded', function() {
    const protectedContent = document.getElementById('protected-content');
    
    // Initialize shield with your configuration
    window.lemmaShield = new LemmaShield({
        apiKey: 'your-api-key-here',
        apiBase: 'https://lemma.id',
        containerId: 'lemma-shield',
        debug: false, // Set to true for development
        
        // Configuration options
        offlineFirst: true,        // Try offline verification first
        fallbackEnabled: true,     // Allow API fallback
        forceShield: false,        // Set to true to always show shield
        
        // Event callbacks
        onVerified: function(result) {
            console.log('✅ User verified:', result);
            
            // Unlock protected content
            if (protectedContent) {
                protectedContent.classList.remove('lemma-protected');
            }
            
            // Your custom logic here
            enableProtectedFeatures();
        },
        
        onError: function(error) {
            console.error('❌ Verification error:', error);
            // Handle errors (optional)
        },
        
        onRevoked: function(result) {
            console.log('🚫 Credentials revoked:', result);
            
            // Re-protect content
            if (protectedContent) {
                protectedContent.classList.add('lemma-protected');
            }
            
            // Your custom logic here
            disableProtectedFeatures();
        },
        
        onShieldShown: function() {
            console.log('🛡️ Shield displayed for verification');
            // Shield is now visible to user
        },
        
        onShieldHidden: function() {
            console.log('👁️ Shield hidden - user verified');
            // User has been verified and shield is hidden
        }
    });
});

// Your custom functions
function enableProtectedFeatures() {
    // Enable protected functionality
    console.log('🎉 User has access to protected features');
}

function disableProtectedFeatures() {
    // Disable protected functionality
    console.log('🔒 User access revoked');
}
</script>
```

## 🎯 **Complete Working Example**

Here's a complete, copy-paste example:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lemma Protected Site</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f8f9fa;
        }
        
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }
        
        /* Protection styling */
        .protected-content {
            transition: opacity 0.3s ease, filter 0.3s ease;
        }
        
        .protected-content.lemma-protected {
            opacity: 0.3;
            filter: blur(2px);
            pointer-events: none;
        }
        
        .status-indicator {
            padding: 1rem;
            border-radius: 8px;
            margin: 1rem 0;
            font-weight: 600;
        }
        
        .status-verified {
            background: #d1fae5;
            color: #065f46;
            border: 1px solid #a7f3d0;
        }
        
        .status-protected {
            background: #fef3c7;
            color: #92400e;
            border: 1px solid #fde68a;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Shield Container -->
        <div id="lemma-shield"></div>
        
        <!-- Status Indicator -->
        <div id="status-indicator" class="status-indicator status-protected">
            🛡️ Content protected by Lemma Shield
        </div>
        
        <!-- Protected Content -->
        <div id="protected-content" class="protected-content lemma-protected">
            <h1>🎉 Welcome to Your Protected Site!</h1>
            <p>This content is now protected by Lemma's three-flow verification circuit:</p>
            
            <ul>
                <li><strong>✅ CHECK FLOW:</strong> Instant offline verification for returning users</li>
                <li><strong>🛡️ SHIELD FLOW:</strong> Human verification for new users</li>
                <li><strong>🚫 REVOCATION FLOW:</strong> Automatic security response</li>
            </ul>
            
            <h3>🔐 Features Unlocked:</h3>
            <ul>
                <li>No more captchas</li>
                <li>Offline verification</li>
                <li>Cross-site credentials</li>
                <li>Privacy-preserving</li>
            </ul>
            
            <div style="background: #f0f9ff; padding: 1rem; border-radius: 8px; margin: 1rem 0;">
                <h4>🧪 Test the System:</h4>
                <button onclick="testRevocation()" style="
                    background: #ef4444; 
                    color: white; 
                    border: none; 
                    padding: 8px 16px; 
                    border-radius: 6px; 
                    cursor: pointer;
                    font-weight: 600;
                ">
                    🚨 Test Credential Revocation
                </button>
                <p style="font-size: 14px; color: #6b7280; margin: 0.5rem 0 0 0;">
                    This will clear your credentials and trigger re-verification
                </p>
            </div>
        </div>
    </div>

    <!-- Lemma Shield Integration -->
    <script src="https://lemma.id/static/js/lemma-shield-widget.js"></script>
    <script>
        // Initialize Lemma Shield
        document.addEventListener('DOMContentLoaded', function() {
            const protectedContent = document.getElementById('protected-content');
            const statusIndicator = document.getElementById('status-indicator');
            
            // Initialize with your API key
            window.lemmaShield = new LemmaShield({
                apiKey: 'your-api-key-here', // Replace with your actual API key
                apiBase: 'https://lemma.id',
                containerId: 'lemma-shield',
                debug: true, // Set to false in production
                
                // Configuration
                offlineFirst: true,
                fallbackEnabled: true,
                
                // Event handlers
                onVerified: function(result) {
                    console.log('✅ User verified:', result);
                    
                    // Unlock content
                    protectedContent.classList.remove('lemma-protected');
                    
                    // Update status
                    statusIndicator.className = 'status-indicator status-verified';
                    statusIndicator.innerHTML = `✅ Verified via ${result.method} flow - Content unlocked!`;
                    
                    // Show success message
                    showMessage('🎉 Welcome to the Lemma Network!', 'success');
                },
                
                onError: function(error) {
                    console.error('❌ Verification error:', error);
                    showMessage('❌ Verification failed. Please try again.', 'error');
                },
                
                onRevoked: function(result) {
                    console.log('🚫 Credentials revoked:', result);
                    
                    // Re-protect content
                    protectedContent.classList.add('lemma-protected');
                    
                    // Update status
                    statusIndicator.className = 'status-indicator status-protected';
                    statusIndicator.innerHTML = '🛡️ Content protected - Verification required';
                    
                    showMessage('🔒 Credentials cleared. Please verify again.', 'info');
                },
                
                onShieldShown: function() {
                    console.log('🛡️ Shield displayed');
                    statusIndicator.innerHTML = '🛡️ Please complete verification to continue';
                },
                
                onShieldHidden: function() {
                    console.log('👁️ Shield hidden');
                }
            });
        });
        
        // Test function for credential revocation
        function testRevocation() {
            if (confirm('This will clear your credentials and require re-verification. Continue?')) {
                if (window.lemmaShield) {
                    window.lemmaShield.clearCredentials();
                    showMessage('🔄 Credentials cleared - shield should reappear', 'info');
                }
            }
        }
        
        // Helper function to show messages
        function showMessage(message, type) {
            const colors = {
                success: { bg: '#d1fae5', text: '#065f46', border: '#a7f3d0' },
                error: { bg: '#fee2e2', text: '#991b1b', border: '#fca5a5' },
                info: { bg: '#dbeafe', text: '#1e40af', border: '#93c5fd' }
            };
            
            const color = colors[type] || colors.info;
            
            const messageDiv = document.createElement('div');
            messageDiv.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: ${color.bg};
                color: ${color.text};
                border: 1px solid ${color.border};
                padding: 1rem;
                border-radius: 8px;
                font-weight: 600;
                z-index: 10000;
                max-width: 300px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                animation: slideIn 0.3s ease-out;
            `;
            
            messageDiv.innerHTML = message;
            document.body.appendChild(messageDiv);
            
            // Add animation
            const style = document.createElement('style');
            style.textContent = `
                @keyframes slideIn {
                    from { opacity: 0; transform: translateX(100%); }
                    to { opacity: 1; transform: translateX(0); }
                }
            `;
            document.head.appendChild(style);
            
            // Remove after 4 seconds
            setTimeout(() => {
                messageDiv.remove();
                style.remove();
            }, 4000);
        }
    </script>
</body>
</html>
```

## 🔧 **Configuration Options**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `apiKey` | string | **required** | Your Lemma API key |
| `apiBase` | string | `window.location.origin` | API base URL |
| `containerId` | string | `'lemma-shield'` | Container element ID |
| `debug` | boolean | `false` | Enable debug logging |
| `offlineFirst` | boolean | `true` | Try offline verification first |
| `fallbackEnabled` | boolean | `true` | Allow API fallback |
| `forceShield` | boolean | `false` | Always show shield (for testing) |

## 📋 **Event Callbacks**

| Event | When Triggered | Data Provided |
|-------|----------------|---------------|
| `onVerified` | User successfully verified | `{ verified: true, method: 'offline/api', credential: {...} }` |
| `onError` | Verification error occurred | `{ error: 'message', timestamp: number }` |
| `onRevoked` | Credentials were revoked | `{ action: 'credentials_revoked', timestamp: number }` |
| `onShieldShown` | Shield widget appears | None |
| `onShieldHidden` | Shield widget disappears | None |

## 🎯 **Three-Flow Circuit Behavior**

### **1. CHECK FLOW (95% of users)**
- **Offline verification** - Instant, zero API calls
- **API fallback** - If offline fails, checks with server
- **User experience** - Seamless, no interaction needed

### **2. SHIELD FLOW (New users)**
- **Human verification** - Stripe Identity integration
- **One-time process** - 30-60 seconds to complete
- **Credential creation** - Enables future offline verification

### **3. REVOCATION FLOW (Security events)**
- **Automatic clearing** - Removes compromised credentials
- **Shield reappearance** - Forces re-verification
- **Network updates** - Propagates security changes

## 🔐 **Security Features**

- **✅ GDPR Compliant** - No personal data stored
- **✅ Privacy-First** - Zero-knowledge proofs
- **✅ Offline Capable** - Works without network
- **✅ Cross-Site** - One verification works everywhere
- **✅ Revocation** - Instant security response

## 🚀 **Advanced Usage**

### **Custom API Key Management**

```javascript
// Dynamic API key loading
const lemmaConfig = {
    apiKey: await getApiKeyFromYourSystem(),
    // ... other options
};
```

### **Custom Event Handling**

```javascript
// Advanced event handling
window.lemmaShield = new LemmaShield({
    // ... config
    onVerified: function(result) {
        // Track analytics
        analytics.track('user_verified', {
            method: result.method,
            flow: result.flowType
        });
        
        // Update user interface
        updateUIForVerifiedUser(result);
        
        // Enable features based on verification level
        if (result.method === 'offline') {
            enableFastFeatures();
        }
    }
});
```

### **Manual Control Methods**

```javascript
// Manual control of the shield
window.lemmaShield.forceRecheck();      // Re-run verification
window.lemmaShield.clearCredentials();  // Clear and re-verify
window.lemmaShield.hide();              // Hide shield
window.lemmaShield.show();              // Show shield
window.lemmaShield.getMetrics();        // Get performance data
```

## 💡 **Best Practices**

1. **Always handle errors gracefully**
2. **Set debug: false in production**
3. **Provide user feedback during verification**
4. **Test the revocation flow**
5. **Monitor verification metrics**

## 🆘 **Troubleshooting**

### **Shield Not Appearing**
- Check API key is correct
- Verify container ID matches
- Check browser console for errors

### **Verification Fails**
- Ensure return URL is valid
- Check network connectivity
- Verify Stripe is accessible

### **Credentials Not Persisting**
- Check localStorage is enabled
- Verify domain matches registration
- Clear browser cache and retry

## 📞 **Support**

- **Documentation**: [lemma.id/docs](https://lemma.id/docs)
- **Email**: support@lemma.network
- **Status**: [status.lemma.id](https://status.lemma.id)

---

**🌟 That's it! Your site is now protected by Lemma's production-ready verification circuit.** 