# Lemma Background Security Checks - Developer Guide

**Configurable background credential verification for different security requirements**

## 🎯 Overview

Lemma's background security check system allows sites to continuously monitor credential validity without user interruption. Using local bloom filter caches, checks are performed in **~0.1µs** with zero user impact.

## 🛡️ Security Levels

### Predefined Security Levels

| Level | Interval | Use Case | Example Sites |
|-------|----------|----------|---------------|
| `low` | 30 minutes | Basic sites, blogs | Personal blogs, documentation |
| `medium` | 5 minutes | E-commerce (default) | Online stores, marketplaces |
| `high` | 2 minutes | Financial services | Investment platforms, fintech |
| `critical` | 1 minute | Banking, sensitive data | Banks, healthcare, government |
| `realtime` | 10 seconds | Ultra-high security | Military, classified systems |

### Custom Intervals

You can also set custom check intervals in milliseconds:

```javascript
// Every 30 seconds
customCheckInterval: 30000

// Every 2 minutes  
customCheckInterval: 120000
```

## 🚀 Quick Start

### Basic Integration

```javascript
// Simple e-commerce site (5-minute checks)
const shield = new LemmaBotShield({
    apiKey: 'your-api-key',
    securityLevel: 'medium'
});

shield.protect('#protected-content');
```

### Banking/Financial Site

```javascript
// High-security banking site (1-minute checks)
const shield = new LemmaBotShield({
    apiKey: 'your-api-key',
    securityLevel: 'critical',
    
    // Custom security event handler
    onSecurityEvent: (event) => {
        if (event.type === 'credential_revoked') {
            // Immediately log out user
            window.location.href = '/logout?reason=security';
        }
    }
});

shield.protect('#banking-dashboard');
```

### Custom High-Frequency Checks

```javascript
// Ultra-secure system (30-second checks)
const shield = new LemmaBotShield({
    apiKey: 'your-api-key',
    customCheckInterval: 30000, // 30 seconds
    
    // Check on all sensitive events
    checkOnEvents: ['entry', 'checkout', 'transfer', 'admin_action', 'data_access'],
    
    onSecurityEvent: (event) => {
        console.warn('Security Event:', event);
        
        // Site-specific security responses
        switch(event.type) {
            case 'credential_revoked':
                showSecurityAlert('Access revoked');
                break;
            case 'security_check_failed':
                increaseSecurity();
                break;
        }
    }
});
```

## 📊 Event-Triggered Checks

### E-commerce Checkout Example

```javascript
// Check credentials before processing payment
async function processPayment(paymentData) {
    // Trigger security check before sensitive operation
    const securityCheck = await shield.checkOnEvent('checkout');
    
    if (!securityCheck.passed) {
        throw new Error('Security check failed - cannot process payment');
    }
    
    // Proceed with payment
    return await chargeCard(paymentData);
}
```

### Banking Transfer Example

```javascript
// Check credentials before money transfer
async function initiateTransfer(transferData) {
    const securityCheck = await shield.checkOnEvent('sensitive_action');
    
    if (!securityCheck.passed) {
        alert('Security verification required before transfer');
        redirectToReVerification();
        return;
    }
    
    return await processTransfer(transferData);
}
```

## 🔧 Dynamic Security Configuration

### Adjust Security During Runtime

```javascript
// Start with medium security
const shield = new LemmaBotShield({
    apiKey: 'your-api-key',
    securityLevel: 'medium'
});

// Increase security for admin section
function enterAdminMode() {
    shield.updateSecurityLevel('critical'); // 1-minute checks
}

// Custom intervals for special events
function enableHighSecurity() {
    shield.setCheckInterval(15000); // 15-second checks
}

// Disable during maintenance
function maintenanceMode() {
    shield.setBackgroundChecks(false);
}
```

## 📈 Monitoring & Status

### Check Current Security Status

```javascript
const status = shield.getSecurityStatus();
console.log('Security Status:', {
    level: status.securityLevel,
    interval: status.checkInterval / 1000 + 's',
    lastCheck: new Date(status.lastCheck),
    isHealthy: status.isHealthy,
    nextCheckIn: status.nextCheckIn / 1000 + 's'
});
```

### API Monitoring

```javascript
// Get detailed security metrics
fetch('/api/sdk/security-status', {
    headers: { 'Authorization': 'Bearer your-api-key' }
})
.then(r => r.json())
.then(data => {
    console.log('Security Metrics:', {
        checksPerHour: data.security_metrics.checks_in_last_hour,
        averageCheckTime: data.security_metrics.average_check_time_ms + 'ms',
        revokedDetected: data.security_metrics.revoked_credentials_detected
    });
});
```

## 🚨 Security Event Handling

### Global Event Listener

```javascript
// Listen for security events across the site
window.addEventListener('lemma-security-event', (event) => {
    const { type, details, securityLevel } = event.detail;
    
    // Log security events
    console.warn(`Security Event [${securityLevel}]:`, type, details);
    
    // Site-specific responses
    switch(type) {
        case 'credential_revoked':
            handleRevokedCredential(details);
            break;
        case 'security_check_failed':
            handleSecurityFailure(details);
            break;
    }
});
```

## ⚡ Performance Impact

### Zero User Impact
- **Background checks**: Run silently without user interaction
- **Local caching**: ~0.1µs bloom filter lookups  
- **Network efficiency**: Only sync when needed
- **Battery friendly**: Minimal CPU usage

### Performance Metrics
```
Local Bloom Filter Check: ~0.1µs
Network Revocation Sync: ~45ms (every 5 minutes)
Memory Usage: <1MB for millions of revocations
CPU Impact: <0.1% during background checks
```

## 🔒 Use Case Examples

### 1. E-commerce Site (Medium Security)
```javascript
const shield = new LemmaBotShield({
    apiKey: 'ecommerce-key',
    securityLevel: 'medium', // 5-minute background checks
    checkOnEvents: ['entry', 'checkout'], // Check before payment
});
```

### 2. Banking Site (Critical Security)
```javascript
const shield = new LemmaBotShield({
    apiKey: 'bank-key', 
    securityLevel: 'critical', // 1-minute background checks
    checkOnEvents: ['entry', 'transfer', 'admin_action'],
    
    onSecurityEvent: (event) => {
        // Immediate security response
        if (event.type === 'credential_revoked') {
            logoutUser();
            redirectToSecurityPage();
        }
    }
});
```

### 3. Blog Site (Low Security)
```javascript
const shield = new LemmaBotShield({
    apiKey: 'blog-key',
    securityLevel: 'low', // 30-minute background checks
    checkOnEvents: ['entry'], // Only check on entry
});
```

### 4. Government Site (Ultra Security)
```javascript
const shield = new LemmaBotShield({
    apiKey: 'gov-key',
    customCheckInterval: 5000, // 5-second checks
    checkOnEvents: ['entry', 'document_access', 'data_export', 'admin_action'],
    
    onSecurityEvent: (event) => {
        // Strict security enforcement
        logSecurityEvent(event);
        if (event.type === 'credential_revoked') {
            immediateLogout();
            notifySecurityTeam(event);
        }
    }
});
```

## 🛠️ API Reference

### Configuration Options
```typescript
interface LemmaBotShieldConfig {
    apiKey: string;
    securityLevel?: 'low' | 'medium' | 'high' | 'critical' | 'realtime';
    customCheckInterval?: number; // milliseconds
    checkOnEvents?: string[]; // ['entry', 'checkout', 'sensitive_action']
    backgroundChecks?: boolean; // default: true
    onSecurityEvent?: (event: SecurityEvent) => void;
}
```

### Methods
```typescript
// Dynamic configuration
shield.updateSecurityLevel(level: string): void
shield.setCheckInterval(intervalMs: number): void
shield.setBackgroundChecks(enabled: boolean): void

// Event-triggered checks
shield.checkOnEvent(eventType: string): Promise<CheckResult>

// Status monitoring
shield.getSecurityStatus(): SecurityStatus
```

### API Endpoints
```
POST /api/sdk/security-config  - Update security configuration
GET  /api/sdk/security-status  - Get security metrics
POST /api/sdk/trigger-check    - Manual security check
```

## 💡 Best Practices

1. **Choose appropriate security level** for your site's risk profile
2. **Use event-triggered checks** for sensitive operations
3. **Implement custom security event handlers** for your specific needs
4. **Monitor security metrics** to ensure proper operation
5. **Test security configurations** in development before production
6. **Have fallback plans** for security check failures

## 🚀 Getting Started

1. **Install**: Include the Lemma bot shield in your site
2. **Configure**: Choose your security level
3. **Protect**: Add `shield.protect('#content')` 
4. **Monitor**: Check security status and metrics
5. **Customize**: Add event handlers and custom intervals as needed

With Lemma's background security checks, you can provide the exact level of security your platform needs without any impact on user experience!