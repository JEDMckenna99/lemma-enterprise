# Lemma Error Codes Reference

Complete guide to all error codes, causes, and solutions.

---

## 🔴 **Authentication Errors (401)**

### `invalid_api_key`
**HTTP:** 401  
**Message:** "Invalid or missing API key"

**Causes:**
- API key not provided in Authorization header
- API key is incorrect
- API key has been revoked

**Solution:**
```javascript
// Check your API key
const auth = new LemmaAuth({
    apiKey: 'lemma_abc123...',  // Verify this is correct
    siteId: 'your_site'
});

// Get API key from: https://lemma.id/dashboard
```

---

### `unauthorized`
**HTTP:** 401  
**Message:** "Unauthorized access"

**Causes:**
- No credential provided
- Credential invalid
- Not authenticated

**Solution:**
```javascript
// Check if user is authenticated first
const isAuth = await auth.isAuthenticated();
if (!isAuth) {
    // Redirect to login
    showLoginForm();
}
```

---

## 🚫 **Permission Errors (403)**

### `nonce_reused`
**HTTP:** 403  
**Message:** "Nonce already used (possible replay attack)"

**Causes:**
- Same nonce used twice (network retry, replay attack)
- Request duplicated

**Solution:**
```javascript
// Always generate fresh nonce
const nonce = crypto.getRandomValues(new Uint8Array(32));

// Don't reuse nonces!
// ❌ Bad: const nonce = "hardcoded";
// ✅ Good: Generate new nonce each time
```

---

### `timestamp_old`
**HTTP:** 403  
**Message:** "Timestamp too old (>5 minutes)"

**Causes:**
- System clock is wrong
- Request took too long to send
- Network delay

**Solution:**
```javascript
// Use current timestamp
timestamp: Date.now()  // Current time in milliseconds

// Check system clock if this persists
```

---

### `credential_expired`
**HTTP:** 403  
**Message:** "Credential expired"

**Causes:**
- Credential past 90-day expiration date

**Solution:**
```javascript
// Request new credential
await auth.sendLoginEmail(user.email);
alert('Your credential expired. Check your email to renew.');
```

---

### `credential_revoked`
**HTTP:** 403  
**Message:** "Credential revoked by administrator"

**Causes:**
- Admin revoked this user's access
- Propagated in <100ms via event-driven sync

**Solution:**
```javascript
// User needs to request access again
if (error.includes('revoked')) {
    alert('Your access has been revoked. Contact administrator.');
    await auth.logout();  // Clear revoked credential
    redirectToLogin();
}
```

---

### `domain_mismatch`
**HTTP:** 403  
**Message:** "Site domain mismatch"

**Causes:**
- Credential for site A, used on site B
- siteDomain in credential doesn't match current domain

**Solution:**
```javascript
// Each site needs its own credentials
// Credential for "app.example.com" won't work on "admin.example.com"

// Solution: Request separate credentials for each domain
await auth.sendLoginEmail(email, {
    site_domain: window.location.hostname  // Use current domain
});
```

---

### `invalid_signature`
**HTTP:** 403  
**Message:** "Ed25519 signature verification failed"

**Causes:**
- Credential tampered with
- Credential corrupted
- Wrong issuer key

**Solution:**
```javascript
// Request fresh credential
await auth.logout();  // Clear corrupted credential
await auth.sendLoginEmail(email);  // Get new one
```

---

## 📭 **Request Errors (400)**

### `missing_required_field`
**HTTP:** 400  
**Message:** "Missing required field: [field_name]"

**Causes:**
- Required parameter not provided

**Solution:**
```javascript
// Ensure all required fields are provided
const result = await auth.sendLoginEmail(email, {
    role: 'user',  // Optional but recommended
    redirectUrl: window.location.href  // Where to return after confirmation
});
```

---

### `invalid_email`
**HTTP:** 400  
**Message:** "Invalid email address"

**Causes:**
- Email format incorrect
- Missing @ or domain

**Solution:**
```javascript
// Validate email before sending
function isValidEmail(email) {
    return email.includes('@') && email.includes('.');
}

if (!isValidEmail(email)) {
    alert('Please enter a valid email address');
    return;
}
```

---

## 🚦 **Rate Limit Errors (429)**

### `rate_limit_exceeded`
**HTTP:** 429  
**Message:** "Rate limit exceeded"

**Limits:**
- 5 email confirmations per user per hour
- 100 API requests per minute per API key
- Unlimited client-side verifications

**Solution:**
```javascript
if (error.status === 429) {
    alert('Too many attempts. Please wait 1 hour and try again.');
    
    // Show countdown timer
    showCountdown(3600);  // 1 hour
}
```

---

## 💥 **Server Errors (500)**

### `email_delivery_failed`
**HTTP:** 500  
**Message:** "Failed to send confirmation email"

**Causes:**
- Email service temporarily down
- Invalid email address
- Network issue

**Solution:**
```javascript
// Retry with exponential backoff
async function sendWithRetry(email, maxRetries = 3) {
    for (let i = 0; i < maxRetries; i++) {
        try {
            const result = await auth.sendLoginEmail(email);
            if (result.success) return result;
        } catch (error) {
            if (i === maxRetries - 1) throw error;
            await sleep(1000 * Math.pow(2, i));  // 1s, 2s, 4s
        }
    }
}
```

---

## 📋 **Quick Reference**

| Error Code | HTTP | Retry? | User Action |
|------------|------|--------|-------------|
| `invalid_api_key` | 401 | No | Check API key in dashboard |
| `nonce_reused` | 403 | Yes | Generate fresh nonce |
| `timestamp_old` | 403 | Yes | Use current timestamp |
| `credential_expired` | 403 | No | Request new credential |
| `credential_revoked` | 403 | No | Contact administrator |
| `rate_limit_exceeded` | 429 | Yes | Wait 1 hour |
| `email_delivery_failed` | 500 | Yes | Retry after delay |

---

**For complete debugging guide, see:** [INTEGRATION_CHECKLIST.md](./INTEGRATION_CHECKLIST.md)

