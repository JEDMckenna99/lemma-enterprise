# @lemma/verification-sdk

> Zero-config credential verification with 32.8µs performance

[![npm version](https://badge.fury.io/js/%40lemma%2Fverification-sdk.svg)](https://badge.fury.io/js/%40lemma%2Fverification-sdk)
[![TypeScript](https://img.shields.io/badge/TypeScript-Ready-blue.svg)](https://www.typescriptlang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🚀 **Quick Start**

### Installation
```bash
npm install @lemma/verification-sdk
```

### Basic Usage
```javascript
import { Lemma } from '@lemma/verification-sdk';

const lemma = new Lemma({
  apiKey: 'your-api-key'
});

// Verify any credential
const result = await lemma.verify(credentialData);
console.log('Verified:', result.verified);
console.log('Time:', result.timing.verification + 'µs');
```

### Zero-Config HTML Integration
```html
<!-- Single script tag -->
<script src="https://cdn.lemma.id/lemma-auto.js" data-api-key="your-key"></script>

<!-- Add verification buttons -->
<button data-lemma-verify="qr-scan">Verify Credential</button>
<div data-lemma-result></div>
```

## 🎯 **Features**

- **⚡ Ultra-fast**: 32.8µs verification time
- **🔒 Offline-first**: Zero network calls during verification
- **📱 Universal**: Works with all credential types
- **🎨 Zero-config**: Single script tag integration
- **🔧 TypeScript**: Full type support and IntelliSense
- **📊 Monitoring**: Built-in performance metrics
- **🔄 Resilient**: Automatic retry and error handling

## 📚 **API Reference**

### Constructor
```javascript
const lemma = new Lemma(config);
```

#### Configuration Options
```typescript
interface LemmaConfig {
  apiKey?: string;           // Your API key
  wasmPath?: string;         // Custom WASM path
  debug?: boolean;           // Enable debug logging
  retryAttempts?: number;    // Retry attempts (default: 3)
  timeout?: number;          // Timeout in ms (default: 10000)
  theme?: 'light' | 'dark';  // UI theme
  language?: string;         // Language code
  autoInit?: boolean;        // Auto-initialize (default: true)
}
```

### Methods

#### `verify(credentialData: string): Promise<VerificationResult>`
Verify a credential with cryptographic proof.

```javascript
const result = await lemma.verify(credentialData);
```

#### `scanQR(options?: QRScanOptions): Promise<QRScanResult>`
Scan and verify a QR code.

```javascript
const result = await lemma.scanQR();
```

#### `on(event: string, callback: Function): void`
Listen to SDK events.

```javascript
lemma.on('verification-complete', (result) => {
  console.log('Verification completed:', result);
});
```

### Events

| Event | Description | Data |
|-------|-------------|------|
| `ready` | SDK initialized | `void` |
| `verification-start` | Verification started | `void` |
| `verification-complete` | Verification completed | `VerificationResult` |
| `verification-error` | Verification failed | `Error` |
| `scan-start` | QR scan started | `void` |
| `scan-complete` | QR scan completed | `QRScanResult` |
| `scan-error` | QR scan failed | `Error` |

## 🎨 **Examples**

### Basic Verification
```javascript
import { Lemma } from '@lemma/verification-sdk';

const lemma = new Lemma({ apiKey: 'your-key' });

// Wait for SDK to be ready
lemma.on('ready', async () => {
  const credential = {
    credentialType: 'identity',
    isHuman: true,
    verificationLevel: 'high'
  };
  
  const result = await lemma.verify(JSON.stringify(credential));
  
  if (result.verified) {
    console.log('✅ Credential verified in', result.timing.verification + 'µs');
  } else {
    console.log('❌ Verification failed');
  }
});
```

### QR Code Scanning
```javascript
const lemma = new Lemma({ apiKey: 'your-key' });

// Scan QR code with camera
const result = await lemma.scanQR();
console.log('QR data:', result.data);
console.log('Verification:', result.verificationResult);
```

### Performance Monitoring
```javascript
const lemma = new Lemma({ apiKey: 'your-key', debug: true });

// Get performance metrics
const metrics = lemma.getPerformanceMetrics();
console.log('Average time:', metrics.averageVerificationTime + 'µs');
console.log('Cache hit rate:', metrics.cacheHitRate * 100 + '%');
```

### Error Handling
```javascript
const lemma = new Lemma({ apiKey: 'your-key' });

lemma.on('error', (event) => {
  console.error('SDK Error:', event.data.message);
});

try {
  const result = await lemma.verify(credentialData);
} catch (error) {
  if (error.code === 'VERIFICATION_ERROR') {
    console.log('Verification failed:', error.message);
  }
}
```

## 🔧 **Advanced Usage**

### Custom Configuration
```javascript
const lemma = new Lemma({
  apiKey: 'your-key',
  wasmPath: 'https://your-cdn.com/pkg/',
  debug: true,
  retryAttempts: 5,
  timeout: 15000,
  theme: 'dark'
});
```

### Event-Driven Architecture
```javascript
const lemma = new Lemma({ apiKey: 'your-key' });

lemma.on('verification-start', () => {
  showLoadingSpinner();
});

lemma.on('verification-complete', (result) => {
  hideLoadingSpinner();
  displayResult(result);
});

lemma.on('verification-error', (error) => {
  hideLoadingSpinner();
  showError(error.message);
});
```

### Cache Management
```javascript
const lemma = new Lemma({ apiKey: 'your-key' });

// Clear cache
lemma.clearCache();

// Check cache size
console.log('Cache size:', lemma.getCacheSize());

// Disable caching
lemma.setCacheEnabled(false);
```

## 📱 **Integration Examples**

### E-commerce Checkout
```javascript
// Age verification for restricted products
const identityResult = await lemma.verify(identityCredential);
if (identityResult.verified && identityResult.claims.age >= 21) {
  // Allow purchase
}

// Product authenticity verification
const productResult = await lemma.verify(productCredential);
if (productResult.verified) {
  // Display authenticity badge
}
```

### Event Ticketing
```javascript
// Ticket verification at entry
const ticketResult = await lemma.verify(ticketCredential);
if (ticketResult.verified) {
  const claims = ticketResult.claims;
  console.log('Event:', claims.eventName);
  console.log('Seat:', claims.seatNumber);
  // Allow entry
}
```

### Document Verification
```javascript
// Identity document verification
const docResult = await lemma.verify(documentCredential);
if (docResult.verified) {
  const claims = docResult.claims;
  console.log('Name:', claims.name);
  console.log('Country:', claims.country);
  // Process identity
}
```

## 🌍 **Browser Support**

| Browser | Version | Support |
|---------|---------|---------|
| Chrome | 80+ | ✅ Full |
| Firefox | 75+ | ✅ Full |
| Safari | 14+ | ✅ Full |
| Edge | 80+ | ✅ Full |
| Opera | 67+ | ✅ Full |

## 📊 **Performance**

- **Verification Time**: 32.8µs (cached) / 150µs (uncached)
- **Throughput**: 30,000+ verifications/second
- **Network Calls**: 0 (offline verification)
- **Memory Usage**: <50MB
- **Bundle Size**: ~2MB (including WASM)

## 🔐 **Security**

- **Ed25519 Signatures**: Cryptographic authenticity
- **OPRF Evaluation**: Privacy-preserving verification
- **Bloom Filter Revocation**: Efficient offline revocation
- **WebAssembly Isolation**: Sandboxed execution

## 🐛 **Troubleshooting**

### Common Issues

**WebAssembly failed to load**
```javascript
// Ensure you're using HTTPS or localhost
// Check browser console for detailed errors
```

**QR Scanner not working**
```javascript
// Grant camera permissions
// Use HTTPS (required for camera access)
```

**Verification timeout**
```javascript
// Increase timeout in configuration
const lemma = new Lemma({
  apiKey: 'your-key',
  timeout: 20000 // 20 seconds
});
```

## 📄 **License**

MIT License - see [LICENSE](LICENSE) for details.

## 🤝 **Contributing**

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 🔗 **Links**

- [Documentation](https://docs.lemma.id)
- [Live Examples](https://lemma.id/examples)
- [GitHub Repository](https://github.com/lemma-verification/sdk)
- [npm Package](https://www.npmjs.com/package/@lemma/verification-sdk)

## 💬 **Support**

- [GitHub Issues](https://github.com/lemma-verification/sdk/issues)
- [Discord Community](https://discord.gg/lemma)
- [Email Support](mailto:support@lemma.id)

---

**Made with ❤️ by the Lemma team** 