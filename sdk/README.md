# @lemma-network/verifier

**The official Lemma Verifier SDK - Add human verification to any website in 10 minutes**

[![npm version](https://badge.fury.io/js/@lemma-network%2Fverifier.svg)](https://www.npmjs.com/package/@lemma-network/verifier)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🚀 Quick Start

### Installation

```bash
npm install @lemma-network/verifier
```

### Basic Usage

```javascript
import { LemmaClient } from '@lemma-network/verifier';

const lemma = new LemmaClient({
  instanceUrl: 'https://your-lemma-instance.com'
});

// Verify a user
const result = await lemma.verify();
if (result.verified) {
  console.log('User is a verified human! 🎉');
}
```

## 🎯 Features

- **🤖 Bot Detection**: Fundamentally cut bots at their core
- **⚡ 10-Minute Integration**: Copy-paste setup for any website
- **🔒 Privacy-First**: Minimal data collection, maximum user privacy
- **📱 Cross-Platform**: Works in browsers and Node.js
- **⚛️ React Ready**: Built-in React hooks and components
- **🚀 Express Middleware**: Easy backend integration
- **📋 W3C Standards**: Full compliance with Verifiable Credentials
- **🌐 Network Effects**: Part of the Lemma Verified Network

## 📚 Documentation

### Table of Contents

1. [React Integration](#react-integration)
2. [Express Middleware](#express-middleware)
3. [Vanilla JavaScript](#vanilla-javascript)
4. [API Reference](#api-reference)
5. [Examples](#examples)

## ⚛️ React Integration

### Hook-based Usage

```tsx
import { useLemmaVerification } from '@lemma-network/verifier';

function MyComponent() {
  const { isVerified, isLoading, verify, error } = useLemmaVerification({
    instanceUrl: 'https://your-lemma-instance.com',
    autoVerify: true,
    onSuccess: (result) => console.log('User verified!', result),
    onError: (error) => console.error('Verification failed:', error)
  });

  if (isLoading) return <div>Verifying...</div>;
  if (error) return <div>Error: {error.message}</div>;
  if (!isVerified) return <button onClick={verify}>Verify with Lemma</button>;
  
  return <div>Welcome, verified human! 🎉</div>;
}
```

### Component-based Usage

```tsx
import { LemmaGate } from '@lemma-network/verifier';

function App() {
  return (
    <LemmaGate
      config={{ instanceUrl: 'https://your-lemma-instance.com' }}
      onVerified={(result) => console.log('Verified!', result)}
    >
      <div>This content is only visible to verified humans</div>
    </LemmaGate>
  );
}
```

### Higher-Order Component

```tsx
import { withLemmaVerification } from '@lemma-network/verifier';

const ProtectedComponent = withLemmaVerification(
  MyComponent,
  { instanceUrl: 'https://your-lemma-instance.com' },
  () => <div>Please verify to continue</div>
);
```

## 🚀 Express Middleware

### Basic Middleware

```javascript
const express = require('express');
const { lemmaMiddleware } = require('@lemma-network/verifier');

const app = express();

// Add Lemma verification to all routes
app.use(lemmaMiddleware({
  instanceUrl: 'https://your-lemma-instance.com',
  apiKey: 'your-api-key'
}));

// Protected route
app.get('/protected', (req, res) => {
  if (req.lemma?.isVerified) {
    res.send(`Welcome, verified human! User ID: ${req.lemma.userId}`);
  } else {
    res.redirect('/verify');
  }
});
```

### Required Verification

```javascript
const { requireLemmaVerification } = require('@lemma-network/verifier');

// This route requires human verification
app.get('/humans-only', 
  requireLemmaVerification({ 
    instanceUrl: 'https://your-lemma-instance.com',
    redirectTo: '/verify'
  }),
  (req, res) => {
    res.send('Welcome, verified human!');
  }
);
```

### Verification Callback Handler

```javascript
const { lemmaCallbackHandler } = require('@lemma-network/verifier');

app.post('/auth/lemma/callback', 
  lemmaCallbackHandler({ instanceUrl: 'https://your-lemma-instance.com' }),
  (req, res) => {
    if (req.lemma?.isVerified) {
      res.redirect('/dashboard');
    } else {
      res.redirect('/verify?error=verification_failed');
    }
  }
);
```

## 🌐 Vanilla JavaScript

### Basic Client

```html
<!-- Include the SDK -->
<script src="https://unpkg.com/@lemma-network/verifier/dist/index.js"></script>

<script>
const lemma = new LemmaVerifier.LemmaClient({
  instanceUrl: 'https://your-lemma-instance.com'
});

document.getElementById('verify-btn').addEventListener('click', async () => {
  try {
    const result = await lemma.verify();
    if (result.verified) {
      document.getElementById('status').textContent = 'Verified human! 🎉';
    }
  } catch (error) {
    console.error('Verification failed:', error);
  }
});
</script>
```

### Check Existing Verification

```javascript
// Check if user is already verified
const hasCredential = await lemma.hasCredential();
if (hasCredential) {
  const result = await lemma.verify();
  console.log('Verification status:', result.verified);
}
```

## 🔧 API Reference

### LemmaClient

#### Constructor

```typescript
new LemmaClient(config: LemmaConfig)
```

- `config.instanceUrl` (string): Your Lemma instance URL
- `config.apiKey` (string, optional): API key for backend operations
- `config.timeout` (number, optional): Request timeout in milliseconds (default: 30000)
- `config.debug` (boolean, optional): Enable debug logging (default: false)

#### Methods

##### `verify(redirectTo?: string): Promise<VerificationResult>`

Verify the user is human. If no credential exists, redirects to verification flow.

##### `hasCredential(): Promise<boolean>`

Check if user has a stored Lemma credential.

##### `getStoredCredential(): Promise<VerifiableCredential | null>`

Get the stored credential from browser storage.

##### `clearVerification(): Promise<void>`

Clear stored verification credential.

##### `importCredential(credentialJson: string): Promise<void>`

Import a credential from JSON (for cross-device use).

##### `exportCredential(): Promise<string | null>`

Export credential as JSON (for backup/transfer).

### React Hooks

#### `useLemmaVerification(config: LemmaConfig & UseLemmaVerificationOptions)`

Returns an object with:
- `isVerified: boolean` - Current verification status
- `isLoading: boolean` - Loading state
- `error: Error | null` - Error state
- `verify: () => Promise<VerificationResult>` - Trigger verification
- `clearVerification: () => void` - Clear verification
- `getCredential: () => Promise<VerifiableCredential | null>` - Get credential

### Express Middleware

#### `lemmaMiddleware(config: LemmaConfig, options?: LemmaMiddlewareOptions)`

Add Lemma verification to Express routes.

#### `requireLemmaVerification(config: LemmaConfig, options?: LemmaMiddlewareOptions)`

Require human verification for a route.

## 📊 Examples

### E-commerce Integration

```javascript
// Prevent bot purchases
app.post('/api/purchase', 
  requireLemmaVerification({ instanceUrl: process.env.LEMMA_URL }),
  async (req, res) => {
    // Only verified humans can make purchases
    const order = await processOrder(req.body, req.lemma.userId);
    res.json({ success: true, order });
  }
);
```

### Content Gating

```tsx
function PremiumContent() {
  const { isVerified, verify } = useLemmaVerification({
    instanceUrl: process.env.REACT_APP_LEMMA_URL
  });

  if (!isVerified) {
    return (
      <div className="verification-gate">
        <h3>Human Verification Required</h3>
        <p>Verify you're human to access premium content</p>
        <button onClick={verify} className="verify-btn">
          Verify with Lemma
        </button>
      </div>
    );
  }

  return <PremiumArticle />;
}
```

### Form Protection

```javascript
// Protect forms from bot submissions
app.use('/api/contact', lemmaMiddleware({
  instanceUrl: process.env.LEMMA_URL,
  required: true,
  redirectTo: '/verify'
}));

app.post('/api/contact', (req, res) => {
  // Only verified humans can submit
  sendContactEmail(req.body, req.lemma.userId);
  res.json({ success: true });
});
```

## 🔒 Security Features

- **End-to-End Encryption**: Credentials are cryptographically signed
- **Privacy by Design**: Only verifies humanness, no personal data
- **Offline Verification**: Works without internet connectivity
- **Revocation Support**: Real-time credential status checking
- **CSRF Protection**: Built-in security for all operations

## 🌍 Network Effects

When you integrate Lemma, you're joining the **Lemma Verified Network**:

- **Pre-verified Users**: Access users already verified across the network
- **Agent Support**: Perfect for verified agents working across platforms
- **Trust Inheritance**: Benefit from network-wide reputation data
- **Standards Compliance**: W3C-compliant verification that works everywhere

## 📈 Analytics & Monitoring

```javascript
import { lemmaAnalyticsMiddleware } from '@lemma-network/verifier';

// Log verification events
app.use(lemmaAnalyticsMiddleware({
  instanceUrl: process.env.LEMMA_URL
}));

// Get metrics
const metrics = await lemma.getMetrics();
console.log(`Verification rate: ${metrics.tokenReuseRate}%`);
console.log(`CAPTCHA seconds saved: ${metrics.captchaSecondsSaved}`);
```

## 🤝 Support

- **Documentation**: [https://docs.lemma.network](https://docs.lemma.network)
- **Issues**: [GitHub Issues](https://github.com/lemma-network/verifier-sdk/issues)
- **Discord**: [Community Discord](https://discord.gg/lemma)
- **Email**: support@lemma.network

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

**Ready to eliminate bots from your platform?** [Get started with Lemma today!](https://lemma.network) 