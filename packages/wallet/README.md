# lemma-wallet-sdk

Passkey-protected credential wallet SDK for decentralized authentication.

**🔐 Local-first** - Wallet operations require no server calls  
**🛡️ Passkey-protected** - Biometric/PIN unlock via WebAuthn  
**📴 Offline-capable** - Works without network connectivity  
**⚡ Fast** - Credentials stored in IndexedDB for instant access

## Installation

```bash
npm install lemma-wallet-sdk
```

Or via CDN:

```html
<script src="https://unpkg.com/lemma-wallet-sdk/dist/lemma-wallet.min.js"></script>
```

## Quick Start

```javascript
import { LemmaWallet } from 'lemma-wallet-sdk';

// Create and initialize wallet
const wallet = new LemmaWallet();
await wallet.init();

// Check if passkey is registered
const info = await wallet.getWalletInfo();

if (!info.hasPasskey) {
  // First time: Register passkey
  await wallet.registerPasskey();
} else {
  // Returning user: Unlock with passkey
  await wallet.unlock();
}

// Store credentials
await wallet.storeCredential({
  id: 'cred_123',
  issuer: 'did:web:example.com',
  claims: { role: 'member' }
});

// Get credentials
const creds = await wallet.getCredentials();
```

## API Reference

### Initialization

```javascript
const wallet = new LemmaWallet({
  debug: false,    // Enable console logging
  autoSync: true   // Auto-sync revocations on init
});

await wallet.init();
```

### Passkey Registration & Unlock

```javascript
// Register new passkey (first time setup)
const result = await wallet.registerPasskey();
// { success: true, credentialId: '...', walletSecret: '...' }

// Unlock with existing passkey
const unlockResult = await wallet.unlock();
// { success: true, expiresAt: 1234567890, walletSecret: '...' }

// Lock wallet
await wallet.lock();

// Check status
wallet.isUnlocked();  // boolean
wallet.getAuthState(); // { state: 'unlocked', authenticated: true, ... }
```

### Credential Management

```javascript
// Store credential
await wallet.storeCredential({
  id: 'cred_unique_id',
  issuer: 'did:web:example.com',
  claims: { userId: '123', role: 'admin' },
  expiresAt: Date.now() + 86400000 // 24 hours
});

// Get all credentials
const all = await wallet.getCredentials();

// Get by type
const permissions = await wallet.getCredentials('permission');

// Remove credential
await wallet.removeCredential('cred_unique_id');
```

### Verification

```javascript
// Verify credential locally
const result = await wallet.verifyCredential(credential);
// { valid: true } or { valid: false, reason: 'Expired' }

// Check revocation status
const status = await wallet.isRevoked('cred_id');
// { revoked: false, unchecked: false }

// Sync revocation list
await wallet.syncRevocations();
```

### Wallet Info & Export

```javascript
// Get wallet info
const info = await wallet.getWalletInfo();
// { hasPasskey: true, isUnlocked: true, credentialCount: 5, ... }

// Get wallet secret (for PPID derivation)
const secret = await wallet.getWalletSecret();

// Export for backup
const backup = await wallet.export();

// Import from backup
await wallet.import(backup);
```

## TypeScript Support

Full TypeScript definitions included:

```typescript
import { LemmaWallet, Credential, AuthState } from 'lemma-wallet-sdk';

const wallet = new LemmaWallet();
const state: AuthState = wallet.getAuthState();
```

## Browser Support

- Chrome 67+
- Firefox 60+
- Safari 14+
- Edge 79+

Requires WebAuthn/Passkey support for registration and unlock.

## Security Model

- **Passkeys** use device biometrics (FaceID, TouchID, Windows Hello)
- **Credentials** stored encrypted in IndexedDB
- **No passwords** transmitted or stored
- **Offline-first** - works without network connectivity
- **PPID derivation** provides privacy-preserving user identification

## License

MIT © [Lemma](https://lemma.id)
