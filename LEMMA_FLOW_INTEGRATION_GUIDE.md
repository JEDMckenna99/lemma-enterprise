# Lemma Three-Flow Integration Guide

This guide explains how to integrate Lemma's complete bot shield system with the three main flows: **Check**, **Bot Shield**, and **Revocation**.

## Overview

The Lemma bot shield system provides comprehensive protection through three coordinated flows:

1. **CHECK Flow** - Detects and verifies user credentials (offline → online → fallback)
2. **BOT SHIELD Flow** - Protects content until user verifies via Lemma API
3. **REVOCATION Flow** - Handles compromised credentials (OPRF → clear → shield)

## Quick Integration

### 1. Basic HTML Integration

```html
<!DOCTYPE html>
<html>
<head>
    <title>Protected Site</title>
</head>
<body>
    <!-- Your protected content -->
    <div id="protected-content">
        This content requires verification to access.
    </div>

    <!-- Lemma Scripts (order matters) -->
    <script src="https://lemma-enterprise-0f6ba17076c1.herokuapp.com/static/js/lemma-wallet-background.js"></script>
    <script src="https://lemma-enterprise-0f6ba17076c1.herokuapp.com/static/js/lemma-shield-flow-orchestrator.js"></script>
    <script src="https://lemma-enterprise-0f6ba17076c1.herokuapp.com/static/js/lemma-shield-widget.js"></script>

    <script>
        // The orchestrator will automatically handle all three flows
        // No additional configuration needed for basic use
    </script>
</body>
</html>
```

### 2. Advanced Configuration

```javascript
// Initialize with custom options
const orchestrator = LemmaShieldFlowOrchestrator.getInstance({
    apiBase: 'https://your-lemma-instance.com',
    updateInterval: 30000, // 30 seconds
    debug: true,
    onFlowChange: (flow) => {
        console.log('Flow changed to:', flow);
    },
    onCredentialUpdate: (credentials) => {
        console.log('Credentials updated:', credentials);
    }
});

// Listen for flow events
window.addEventListener('lemma-credential-revoked', (event) => {
    console.log('Credential revoked:', event.detail);
    // Handle revocation in your app
});

window.addEventListener('lemma-verification-complete', (event) => {
    console.log('Verification complete:', event.detail);
    // Handle successful verification
});
```

## The Three Flows Explained

### 1. CHECK Flow

**Purpose**: Detect if user has credentials and verify them
**Triggers**: Page load, periodic checks, manual recheck

```javascript
// Flow sequence:
// 1. Check wallet for credentials
// 2. If found, verify offline first (if supported)
// 3. If offline fails or unsupported, verify online
// 4. If valid: grant access
// 5. If revoked: trigger revocation flow
// 6. If none: trigger bot shield flow

// Manual trigger:
orchestrator.forceRecheck();
```

### 2. BOT SHIELD Flow

**Purpose**: Protect content until user completes verification
**Triggers**: No valid credentials found, manual trigger

```javascript
// Flow sequence:
// 1. Show shield widget overlay
// 2. User completes verification process
// 3. Store new credential in wallet
// 4. Hide shield and grant access
// 5. Emit verification complete event

// Manual trigger:
orchestrator.forceShield();
```

### 3. REVOCATION Flow

**Purpose**: Handle compromised or invalid credentials
**Triggers**: Revoked credential detected, manual revocation

```javascript
// Flow sequence:
// 1. Mark credential as revoked in OPRF cascade
// 2. Clear credential from local wallet
// 3. Add to local revocation list
// 4. Notify network of revocation
// 5. Trigger bot shield flow for re-verification

// Manual trigger (for testing):
window.dispatchEvent(new CustomEvent('lemma-credential-revoked', {
    detail: {
        credential_id: 'some-credential-id',
        reason: 'Test revocation',
        timestamp: new Date().toISOString()
    }
}));
```

## Network Synchronization

The system automatically synchronizes credential lists across integrated sites:

### Automatic Updates
- Checks for updates every 30 seconds (configurable)
- Downloads new revocation lists when available
- Updates local cache with latest credential status

### Manual Sync
```javascript
// Force network sync
await orchestrator.syncWithNetwork();

// Check current sync status
const status = orchestrator.getState();
console.log('Last sync:', status.lastCheck);
console.log('Version:', status.credentialListVersion);
```

### API Endpoints

The system provides these endpoints for network synchronization:

#### Network Sync
```bash
POST /api/network/sync
Content-Type: application/json

{
    "version": 123456789,
    "force": false
}
```

#### Batch Credential Status
```bash
POST /api/credential/status-batch
Content-Type: application/json

{
    "credential_ids": ["cred1", "cred2", "cred3"]
}
```

## Event System

### Events Emitted

| Event | When | Detail |
|-------|------|--------|
| `lemma-flow-ready` | Orchestrator initialized | `{}` |
| `lemma-credential-revoked` | Credential revoked | `{credential_id, reason, timestamp}` |
| `lemma-verification-complete` | User verified successfully | `{verified, userId, credential, timestamp}` |
| `lemma-shield-required` | Shield needs to show | `{reason}` |
| `lemma-network-update` | Network sync completed | `{revoked_credentials, version}` |

### Events Listened

| Event | Trigger | Action |
|-------|---------|--------|
| `lemma-credential-revoked` | External revocation | Start revocation flow |
| `lemma-credential-updated` | New credential | Recheck credentials |
| `lemma-shield-required` | External shield request | Show bot shield |

## Testing the Flows

### Test Page
Visit `/flow-test` for an interactive test page that demonstrates all three flows.

### Manual Testing

```javascript
// Test CHECK flow
orchestrator.forceRecheck();

// Test BOT SHIELD flow  
orchestrator.forceShield();

// Test REVOCATION flow
window.dispatchEvent(new CustomEvent('lemma-credential-revoked', {
    detail: {
        credential_id: 'test-credential',
        reason: 'Manual test',
        timestamp: new Date().toISOString()
    }
}));

// Clear all credentials (will trigger shield)
localStorage.removeItem('lemma_revoked_credentials');
if (window.lemmaWallet) {
    await window.lemmaWallet.clearAll();
}
orchestrator.forceRecheck();
```

## Troubleshooting

### Common Issues

1. **Shield not appearing**
   - Check if orchestrator is initialized: `window.lemmaFlowOrchestrator`
   - Check if shield widget is loaded: `window.LemmaShieldWidget`
   - Check console for initialization errors

2. **Credentials not syncing**
   - Check network connectivity
   - Verify API endpoints are accessible
   - Check console for sync errors

3. **Revocation not working**
   - Ensure credential ID is correct
   - Check if revocation event is properly dispatched
   - Verify OPRF cascade is working

### Debug Information

```javascript
// Get orchestrator state
const state = orchestrator.getState();
console.log('Current flow:', state.currentFlow);
console.log('Credential status:', state.credentialStatus);

// Check available components
console.log('Orchestrator:', !!window.lemmaFlowOrchestrator);
console.log('Wallet:', !!window.lemmaWallet);
console.log('Shield Widget:', !!window.LemmaShieldWidget);

// Check local storage
const revoked = localStorage.getItem('lemma_revoked_credentials');
console.log('Local revocations:', revoked ? JSON.parse(revoked) : []);
```

## Production Deployment

### Required Scripts
```html
<!-- Core wallet (background only) -->
<script src="https://lemma-enterprise-0f6ba17076c1.herokuapp.com/static/js/lemma-wallet-background.js"></script>

<!-- Flow orchestrator (required) -->
<script src="https://lemma-enterprise-0f6ba17076c1.herokuapp.com/static/js/lemma-shield-flow-orchestrator.js"></script>

<!-- Shield widget (required) -->
<script src="https://lemma-enterprise-0f6ba17076c1.herokuapp.com/static/js/lemma-shield-widget.js"></script>
```

### Configuration
```javascript
// Production configuration
const orchestrator = LemmaShieldFlowOrchestrator.getInstance({
    apiBase: 'https://your-production-lemma-instance.com',
    updateInterval: 60000, // 1 minute in production
    debug: false,
    onFlowChange: (flow) => {
        // Analytics tracking
        analytics.track('lemma_flow_change', { flow });
    }
});
```

### Monitoring
```javascript
// Monitor orchestrator health
setInterval(() => {
    const state = orchestrator.getState();
    if (state.updateInProgress && Date.now() - state.lastCheck > 300000) {
        // Alert: Sync has been stuck for 5+ minutes
        console.error('Lemma sync appears stuck');
    }
}, 60000);
```

## Support

- **Documentation**: Visit `/docs` for detailed API documentation
- **Test Page**: Visit `/flow-test` for interactive testing
- **Debug Mode**: Add `?debug=true` to any page for enhanced logging
- **Contact**: support@lemma.network for integration assistance 