# Lemma Sign-In SDK

**5-Minute Integration for Any Website**

Add passwordless authentication to your site with Lemma IAM in just 3 lines of code.

---

## Quick Start

### 1. Add SDK to Your Site

```html
<!-- Load Lemma Sign-In SDK -->
<script src="https://lemma.id/static/js/lemma-signin-sdk.js"></script>

<script>
  // Initialize SDK
  const lemmaAuth = new LemmaSignIn({
    siteId: 'yoursite.com',
    onSignIn: (user) => {
      console.log('User signed in:', user.email);
      // Redirect to dashboard or update UI
      window.location.href = '/dashboard';
    }
  });
  
  // Auto-check for existing credentials
  lemmaAuth.init();
</script>
```

**That's it!** Users with valid credentials auto-sign-in. New users get redirected to Lemma for credential issuance.

---

## Configuration Options

```javascript
const lemmaAuth = new LemmaSignIn({
  // Required: Your site identifier
  siteId: 'yoursite.com',
  
  // Optional: Lemma API base (default: https://lemma.id)
  apiBase: 'https://lemma.id',
  
  // Optional: Auto sign-in if credential exists (default: true)
  autoSignIn: true,
  
  // Optional: Require specific permission level
  requiredPermission: 'admin_access', // or null for any permission
  
  // Optional: Enable debug logging
  debug: true,
  
  // Callbacks
  onSignIn: (user) => {
    // Called when user signs in successfully
    // user = {email, role, permissionId, credential}
  },
  
  onSignOut: () => {
    // Called when user signs out
  },
  
  onError: (error) => {
    // Called on authentication errors
  },
  
  // UI Customization
  buttonText: 'Sign in with Lemma',
  buttonStyle: 'default', // or 'minimal', 'custom'
  containerElement: '#signin-container' // Where to render button
});
```

---

## API Methods

### `auth.init()`
Initialize SDK and check for existing credentials.

```javascript
await lemmaAuth.init();
```

### `auth.getCurrentUser()`
Get currently signed-in user.

```javascript
const user = lemmaAuth.getCurrentUser();
// Returns: {email, role, permissionId, credential} or null
```

### `auth.isSignedIn()`
Check if user is signed in.

```javascript
if (lemmaAuth.isSignedIn()) {
  // User has valid credential
}
```

### `auth.signOut()`
Sign out current user.

```javascript
await lemmaAuth.signOut();
```

### `auth.verifyCredential()`
Verify current credential is still valid.

```javascript
const isValid = await lemmaAuth.verifyCredential();
```

### `auth.showSignInButton(container)`
Render sign-in button.

```javascript
lemmaAuth.showSignInButton('#signin-container');
```

---

## Complete Example

```html
<!DOCTYPE html>
<html>
<head>
  <title>My App with Lemma Auth</title>
</head>
<body>
  <div id="app">
    <div id="signin-section">
      <h1>Sign In Required</h1>
      <div id="signin-button"></div>
    </div>
    
    <div id="dashboard-section" style="display: none;">
      <h1>Welcome, <span id="user-email"></span>!</h1>
      <button id="signout-btn">Sign Out</button>
    </div>
  </div>

  <script src="https://lemma.id/static/js/lemma-signin-sdk.js"></script>
  <script>
    const lemmaAuth = new LemmaSignIn({
      siteId: 'myapp.com',
      debug: true,
      
      onSignIn: (user) => {
        // Update UI for signed-in user
        document.getElementById('signin-section').style.display = 'none';
        document.getElementById('dashboard-section').style.display = 'block';
        document.getElementById('user-email').textContent = user.email;
      },
      
      onSignOut: () => {
        // Update UI for signed-out user
        document.getElementById('signin-section').style.display = 'block';
        document.getElementById('dashboard-section').style.display = 'none';
      }
    });
    
    // Initialize and check for existing credentials
    lemmaAuth.init();
    
    // Show sign-in button for users without credentials
    if (!lemmaAuth.isSignedIn()) {
      lemmaAuth.showSignInButton('#signin-button');
    }
    
    // Handle sign-out
    document.getElementById('signout-btn').addEventListener('click', () => {
      lemmaAuth.signOut();
    });
  </script>
</body>
</html>
```

---

## How It Works

1. **SDK loads** and checks browser wallet for valid permission credential
2. **If credential exists** → Auto-sign-in, trigger `onSignIn` callback
3. **If no credential** → User can click "Sign in with Lemma" button
4. **User redirected to Lemma** → Email-based authentication
5. **Credential issued** → Stored in browser wallet
6. **Return to your site** → Auto-signed in

---

## Security Features

- Client-side credential storage (encrypted with browser fingerprint)
- Zero server-side session management needed
- Cryptographic verification (Ed25519 signatures)
- No passwords to manage
- Multi-device sync via QR codes
- Revocation support

---

## Cost

**$0.00/month** - Fully client-side verification, no API calls after credential issuance.

---

## Support

Questions? Email: support@lemma.id
Docs: https://lemma.id/docs/sdk

