# Lemma Enterprise Security Features

## Overview

Lemma Enterprise is designed with enterprise-grade security features to protect sensitive data and prevent common web vulnerabilities. This document outlines the security measures implemented in the system, with a focus on CSRF protection, authentication, and secure session management.

## CSRF Protection

Cross-Site Request Forgery (CSRF) protection is implemented throughout the application to prevent attackers from tricking users into performing unwanted actions.

### Implementation Details

1. **Global CSRF Protection**: All forms and state-changing endpoints are protected by CSRF tokens.

2. **Exempt Routes**: API endpoints that use API key authentication are exempt from CSRF protection, as they use a different security model.

3. **CSRF Token Delivery**:
   - HTML forms include a hidden CSRF token field
   - JavaScript can access the CSRF token via a secure cookie
   - AJAX requests should include the token in the `X-CSRF-Token` header

4. **Testing Compatibility**: CSRF protection can be disabled in test environments using the `SKIP_AUTH_IN_TESTS` configuration option.

### Using CSRF Protection in Frontend Code

When making AJAX requests to protected endpoints, include the CSRF token as follows:

```javascript
// Get the CSRF token from the cookie
const csrfToken = document.cookie
  .split('; ')
  .find(row => row.startsWith('csrf_token='))
  ?.split('=')[1];

// Include it in your fetch request
fetch('/api/verify-presentation', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRF-Token': csrfToken
  },
  body: JSON.stringify(data)
});
```

## Secure Session Management

Sessions are configured with the following security features:

1. **Secure Cookies**: Session cookies are marked as secure (HTTPS only) and HTTP-only.

2. **SameSite Policy**: Cookies use 'Lax' SameSite attribute to prevent CSRF attacks.

3. **Session Timeout**: Sessions expire after 2 hours of inactivity.

4. **IP Binding**: Sessions are bound to the user's IP address to prevent session hijacking.

## API Security

API endpoints are protected using multiple layers of security:

1. **API Key Authentication**: Sensitive operations require a valid API key.

2. **Rate Limiting**: All API endpoints have rate limiting to prevent abuse.

3. **CSRF Protection**: Session-modifying endpoints require a valid CSRF token.

4. **Input Validation**: All input is validated and sanitized to prevent injection attacks.

## Authentication

The system uses multiple authentication mechanisms:

1. **Admin Authentication**: Password-based authentication with secure password hashing.

2. **Credential Verification**: Cryptographic verification of user credentials using Ed25519 signatures.

3. **API Key Authentication**: For programmatic access to the API.

## Production Security Considerations

When deploying to production, ensure the following:

1. **HTTPS**: Always use HTTPS in production environments.

2. **Environment Variables**: Set secure values for all security-related environment variables:
   - `LEMMA_SECRET_KEY`: A strong, random secret key
   - `LEMMA_ADMIN_USER` and `LEMMA_ADMIN_PASS`: Secure admin credentials
   - `LEMMA_API_KEY`: A strong, random API key
   - `LEMMA_TRUSTED_ORIGINS`: Comma-separated list of trusted origins for CORS

3. **CORS Configuration**: In production, restrict CORS to trusted origins only.

4. **Regular Updates**: Keep all dependencies updated to patch security vulnerabilities.

## Testing Security Features

Security features are designed to work seamlessly with the test suite. The following mechanisms ensure tests can run without compromising security in production:

### CSRF Protection in Tests

1. **Automatic Bypass**: When `TESTING=True` and `SKIP_AUTH_IN_TESTS=True` are set in the configuration, CSRF checks are automatically bypassed for testing purposes.

2. **Test CSRF Token**: In test environments, a dummy CSRF token (`test-csrf-token`) is used, which is automatically set in the test client's session.

3. **Session Configuration**: For tests, secure cookie settings are relaxed to allow testing without HTTPS:
   ```python
   # In test environments
   app.config['SESSION_COOKIE_SECURE'] = False
   app.config['SESSION_COOKIE_HTTPONLY'] = False
   app.config['SESSION_COOKIE_SAMESITE'] = None
   ```

### Testing Protected Routes

When testing routes that require authentication or verification:

1. **Session Setup**: Set up the session directly in tests:
   ```python
   with client.session_transaction() as session:
       session['verified_user_id'] = user_id
       session['verified_credential'] = credential
       session['verification_time'] = current_time
       session['verification_expiry'] = expiry_time
   ```

2. **API Testing**: When testing API endpoints that require CSRF tokens, include the token in headers:
   ```python
   headers = {
       'Content-Type': 'application/json',
       'X-CSRF-Token': 'test-csrf-token'
   }
   response = client.post('/api/endpoint', json=data, headers=headers)
   ```

This approach allows tests to run without needing to generate valid CSRF tokens or authentication credentials, while ensuring that these security features are still enforced in production.
