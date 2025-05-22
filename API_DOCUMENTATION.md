# Lemma API Documentation

*Version 2.1.0 - May 2025*

This document provides comprehensive documentation for integrating with the Lemma Human Verification System API. Lemma provides a secure, privacy-preserving way to verify that users are human without collecting personal information.

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [API Endpoints](#api-endpoints)
   - [Health Check](#health-check)
   - [Credential Issuance](#credential-issuance)
   - [Credential Verification](#credential-verification)
   - [Presentation Creation and Verification](#presentation-creation-and-verification)
   - [Human Verification](#human-verification)
   - [Session Management](#session-management)
   - [CSRF Protection](#csrf-protection)
4. [Client-Side Integration](#client-side-integration)
   - [Lemma Wallet Integration](#lemma-wallet-integration)
   - [Verification Widget](#verification-widget)
   - [Cross-Origin Support](#cross-origin-support)
5. [Error Handling](#error-handling)
6. [Rate Limiting](#rate-limiting)
7. [Security Considerations](#security-considerations)
8. [Example Implementations](#example-implementations)
9. [Webhooks](#webhooks)
10. [OPRF Revocation](#oprf-revocation)

## Overview

The Lemma API enables third-party applications to:

1. Verify that users are human without collecting personal information
2. Issue and verify W3C standard Verifiable Credentials
3. Create and verify Verifiable Presentations
4. Check credential revocation status using privacy-preserving OPRF technology
5. Integrate with the Lemma wallet for credential management

All API endpoints return JSON responses and use standard HTTP status codes. The API is designed to be RESTful and follows best practices for web API design.

## Authentication

Most API endpoints that modify data require an API key for authentication. Include the API key in the `X-API-Key` header:

```
X-API-Key: your_api_key_here
```

You can obtain an API key by contacting the Lemma administrator or through the admin dashboard.

### CSRF Protection

For endpoints that modify data and are called from a browser context, you must include a CSRF token. You can obtain a CSRF token using the `/api/generate-csrf-token` endpoint.

Include the CSRF token in one of the following ways:
- In the `X-CSRF-Token` header
- In a `csrf_token` field in the request body (for JSON requests)
- In a `csrf_token` field in the form data (for form submissions)

## API Endpoints

### Health Check

#### GET /api/health

Check if the API is operational.

**Request:**
```http
GET /api/health
```

**Response:**
```json
{
  "status": "ok",
  "version": "2.1.0",
  "timestamp": 1716403200
}
```

### Credential Issuance

#### POST /api/issue-credential

Issue a new credential for a user.

**Authentication Required:** Yes (API Key)

**Request:**
```http
POST /api/issue-credential
Content-Type: application/json
X-API-Key: your_api_key_here
X-CSRF-Token: csrf_token_here

{
  "user_id": "user_123",
  "expiration_days": 365,
  "attributes": {
    "isHuman": true
  }
}
```

**Response:**
```json
{
  "status": "success",
  "credential": {
    "id": "urn:uuid:3e4fc296-88c5-4081-a9ec-c131e9c9b120",
    "@context": [
      "https://www.w3.org/2018/credentials/v1"
    ],
    "type": ["VerifiableCredential", "HumanVerificationCredential"],
    "issuer": "did:lemma:issuer",
    "issuanceDate": "2025-05-22T12:00:00Z",
    "expirationDate": "2026-05-22T12:00:00Z",
    "credentialSubject": {
      "id": "did:user:user_123",
      "isHuman": true
    },
    "proof": {
      "type": "Ed25519Signature2020",
      "created": "2025-05-22T12:00:00Z",
      "verificationMethod": "did:lemma:issuer#keys-1",
      "proofPurpose": "assertionMethod",
      "jws": "eyJhbGciOiJFZERTQSIsImI2NCI6ZmFsc2UsImNyaXQiOlsiYjY0Il19..signature"
    }
  }
}
```

### Credential Verification

#### POST /api/verify-credential

Verify a credential.

**Request:**
```http
POST /api/verify-credential
Content-Type: application/json

{
  "credential": {
    // Credential object from issue-credential response
  }
}
```

**Response:**
```json
{
  "status": "success",
  "valid": true,
  "verification_result": {
    "credential_valid": true,
    "signature_valid": true,
    "issuer_valid": true,
    "not_expired": true,
    "not_revoked": true
  }
}
```

### Presentation Creation and Verification

#### POST /api/presentation

Create a presentation from a credential.

**Request:**
```http
POST /api/presentation
Content-Type: application/json
X-CSRF-Token: csrf_token_here

{
  "credential": {
    // Credential object from issue-credential response
  },
  "challenge": "random_challenge_string"
}
```

**Response:**
```json
{
  "status": "success",
  "presentation": {
    "@context": [
      "https://www.w3.org/2018/credentials/v1"
    ],
    "type": ["VerifiablePresentation"],
    "verifiableCredential": [
      // Credential object
    ],
    "holder": "did:user:user_123",
    "proof": {
      "type": "Ed25519Signature2020",
      "created": "2025-05-22T12:05:00Z",
      "challenge": "random_challenge_string",
      "proofPurpose": "authentication",
      "verificationMethod": "did:lemma:issuer#keys-1",
      "jws": "eyJhbGciOiJFZERTQSIsImI2NCI6ZmFsc2UsImNyaXQiOlsiYjY0Il19..signature"
    }
  }
}
```

#### POST /api/verify-presentation

Verify a presentation.

**Request:**
```http
POST /api/verify-presentation
Content-Type: application/json

{
  "presentation": {
    // Presentation object from presentation response
  },
  "challenge": "random_challenge_string"
}
```

**Response:**
```json
{
  "status": "success",
  "valid": true,
  "verification_result": {
    "presentation_valid": true,
    "credentials_valid": true,
    "challenge_valid": true,
    "holder_valid": true
  }
}
```

### Human Verification

#### POST /api/verify-human

Verify a human presentation and set session.

**Request:**
```http
POST /api/verify-human
Content-Type: application/json
X-CSRF-Token: csrf_token_here

{
  "presentation": {
    // Presentation object from presentation response
  },
  "challenge": "random_challenge_string"
}
```

**Response:**
```json
{
  "status": "success",
  "verified": true,
  "user_id": "user_123",
  "session_expires": "2025-05-22T13:05:00Z"
}
```

#### GET /api/credential-lookup/{user_id}

Get a user's credential (auto-issues if not found).

**Request:**
```http
GET /api/credential-lookup/user_123
```

**Response:**
```json
{
  "status": "success",
  "credential": {
    // Credential object
  },
  "is_new": false
}
```

### Session Management

#### POST /api/logout

Clear the verification session.

**Request:**
```http
POST /api/logout
Content-Type: application/json
X-CSRF-Token: csrf_token_here

{}
```

**Response:**
```json
{
  "status": "success",
  "message": "Session cleared"
}
```

### CSRF Protection

#### GET /api/generate-csrf-token

Generate a CSRF token for secure form submission.

**Request:**
```http
GET /api/generate-csrf-token
```

**Response:**
```json
{
  "csrf_token": "random_csrf_token_string"
}
```

## Client-Side Integration

### Lemma Wallet Integration

The Lemma wallet provides client-side storage and management of credentials. To integrate with the Lemma wallet, include the following scripts on your page:

```html
<script src="https://your-lemma-instance.com/static/js/lemma-wallet.js"></script>
<script src="https://your-lemma-instance.com/static/js/lemma-wallet-init.js"></script>
```

Then, you can interact with the wallet using the global `lemmaWallet` object:

```javascript
// Check if wallet is available
if (window.lemmaWallet) {
  // Get credentials
  const credentials = await window.lemmaWallet.getAllCredentials();
  
  // Create a presentation
  const challenge = "random_challenge";
  const presentation = await window.lemmaWallet.createPresentation(credentials[0], challenge);
  
  // Verify the presentation
  const result = await fetch('/api/verify-human', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrfToken
    },
    body: JSON.stringify({
      presentation: presentation,
      challenge: challenge
    })
  }).then(res => res.json());
  
  if (result.verified) {
    // User is verified
  }
}
```

### Verification Widget

For a simpler integration, you can use the Lemma verification widget:

```html
<div id="lemma-widget-container"></div>

<script src="https://your-lemma-instance.com/static/js/lemma-wallet.js"></script>
<script src="https://your-lemma-instance.com/static/js/lemma-wallet-init.js"></script>
<script src="https://your-lemma-instance.com/static/js/lemma-api-widget.js"></script>

<script>
  // Initialize the widget
  window.LemmaWidget.init({
    containerId: 'lemma-widget-container',
    userId: 'user_123',
    callbackUrl: '/protected',
    buttonText: 'Verify Human',
    description: 'Verify you are human to access protected content',
    onSuccess: function(result) {
      console.log('Verification successful:', result);
    },
    onFailure: function(error) {
      console.error('Verification failed:', error);
    }
  });
</script>
```

### Cross-Origin Support

The Lemma wallet supports cross-origin requests, allowing you to verify users across different domains. To enable cross-origin support:

1. Configure your Lemma instance to allow cross-origin requests from your domain:

```python
# In your Lemma instance configuration
CORS_ALLOWED_ORIGINS = ['https://your-site.com']
```

2. Use the `apiBase` option when initializing the widget or calling `proveALemma`:

```javascript
window.proveALemma({
  userId: 'user_123',
  apiBase: 'https://your-lemma-instance.com',
  onSuccess: function(result) {
    console.log('Verification successful:', result);
  }
});
```

## Error Handling

All API endpoints return standard HTTP status codes:

- `200 OK`: The request was successful
- `400 Bad Request`: The request was invalid
- `401 Unauthorized`: Authentication is required
- `403 Forbidden`: The request is not allowed
- `404 Not Found`: The requested resource was not found
- `500 Internal Server Error`: An error occurred on the server

Error responses include a JSON object with an `error` field describing the error:

```json
{
  "status": "error",
  "error": "Invalid credential format",
  "details": "Missing required field: credentialSubject"
}
```

## Rate Limiting

API endpoints are rate-limited to prevent abuse. The rate limits are as follows:

- Public endpoints: 60 requests per minute per IP address
- Authenticated endpoints: 300 requests per minute per API key

When a rate limit is exceeded, the API returns a `429 Too Many Requests` status code with a `Retry-After` header indicating when the client can retry the request.

## Security Considerations

When integrating with the Lemma API, consider the following security best practices:

1. **Always use HTTPS** for all API requests
2. **Protect your API key** and never expose it in client-side code
3. **Validate all user input** before sending it to the API
4. **Use CSRF tokens** for all requests that modify data
5. **Set secure and HttpOnly flags** on cookies
6. **Implement proper error handling** to avoid exposing sensitive information
7. **Use Content Security Policy (CSP)** to prevent XSS attacks
8. **Regularly rotate API keys** to minimize the impact of key compromise

## Example Implementations

### Python

```python
import requests
import json

# Configuration
LEMMA_API_URL = "https://your-lemma-instance.com/api"
API_KEY = "your_api_key_here"

# Issue a credential
def issue_credential(user_id):
    response = requests.post(
        f"{LEMMA_API_URL}/issue-credential",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY
        },
        json={
            "user_id": user_id,
            "expiration_days": 365,
            "attributes": {
                "isHuman": True
            }
        }
    )
    
    return response.json()

# Verify a credential
def verify_credential(credential):
    response = requests.post(
        f"{LEMMA_API_URL}/verify-credential",
        headers={
            "Content-Type": "application/json"
        },
        json={
            "credential": credential
        }
    )
    
    return response.json()

# Example usage
user_id = "user_123"
result = issue_credential(user_id)

if result["status"] == "success":
    credential = result["credential"]
    verification = verify_credential(credential)
    
    if verification["status"] == "success" and verification["valid"]:
        print(f"User {user_id} is verified human")
    else:
        print("Verification failed")
else:
    print(f"Error: {result.get('error')}")
```

### JavaScript

```javascript
// Configuration
const LEMMA_API_URL = "https://your-lemma-instance.com/api";
const API_KEY = "your_api_key_here";

// Get CSRF token
async function getCsrfToken() {
  const response = await fetch(`${LEMMA_API_URL}/generate-csrf-token`, {
    credentials: 'include'
  });
  const data = await response.json();
  return data.csrf_token;
}

// Verify a human
async function verifyHuman(userId) {
  try {
    // Get CSRF token
    const csrfToken = await getCsrfToken();
    
    // Check if user has a credential
    const lookupResponse = await fetch(`${LEMMA_API_URL}/credential-lookup/${userId}`, {
      credentials: 'include'
    });
    
    const lookupResult = await lookupResponse.json();
    
    if (lookupResult.status !== "success") {
      throw new Error(lookupResult.error || "Failed to lookup credential");
    }
    
    // Generate a random challenge
    const challenge = Array.from(crypto.getRandomValues(new Uint8Array(16)))
      .map(b => b.toString(16).padStart(2, '0')).join('');
    
    // Create a presentation
    const presentationResponse = await fetch(`${LEMMA_API_URL}/presentation`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken
      },
      credentials: 'include',
      body: JSON.stringify({
        credential: lookupResult.credential,
        challenge: challenge
      })
    });
    
    const presentationResult = await presentationResponse.json();
    
    if (presentationResult.status !== "success") {
      throw new Error(presentationResult.error || "Failed to create presentation");
    }
    
    // Verify the presentation
    const verifyResponse = await fetch(`${LEMMA_API_URL}/verify-human`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken
      },
      credentials: 'include',
      body: JSON.stringify({
        presentation: presentationResult.presentation,
        challenge: challenge
      })
    });
    
    const verifyResult = await verifyResponse.json();
    
    if (verifyResult.status === "success" && verifyResult.verified) {
      return {
        verified: true,
        userId: verifyResult.user_id
      };
    } else {
      throw new Error(verifyResult.error || "Verification failed");
    }
  } catch (error) {
    console.error("Error verifying human:", error);
    return {
      verified: false,
      error: error.message
    };
  }
}

// Example usage
verifyHuman("user_123").then(result => {
  if (result.verified) {
    console.log(`User ${result.userId} is verified human`);
  } else {
    console.log(`Verification failed: ${result.error}`);
  }
});
```

## Webhooks

Lemma supports webhooks to notify your application of important events. To configure webhooks, contact the Lemma administrator or use the admin dashboard.

### Webhook Events

- `credential.issued`: A new credential has been issued
- `credential.verified`: A credential has been verified
- `credential.revoked`: A credential has been revoked
- `human.verified`: A human has been verified

### Webhook Payload

```json
{
  "event": "human.verified",
  "timestamp": "2025-05-22T12:05:00Z",
  "data": {
    "user_id": "user_123",
    "credential_id": "urn:uuid:3e4fc296-88c5-4081-a9ec-c131e9c9b120",
    "verification_method": "presentation"
  }
}
```

### Webhook Security

Webhook requests include a signature in the `X-Lemma-Signature` header. To verify the signature:

1. Concatenate the webhook timestamp and the request body
2. Compute an HMAC-SHA256 using your webhook secret
3. Compare the computed signature with the `X-Lemma-Signature` header

```python
import hmac
import hashlib

def verify_webhook_signature(payload, timestamp, signature, secret):
    message = f"{timestamp}.{payload}"
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)
```

## OPRF Revocation

Lemma uses Oblivious Pseudorandom Functions (OPRF) for privacy-preserving credential revocation. The OPRF service allows checking if a credential has been revoked without revealing the credential ID.

### OPRF Endpoints

#### GET /oprf/health

Check if the OPRF service is operational.

**Request:**
```http
GET /oprf/health
```

**Response:**
```json
{
  "status": "ok",
  "service": "lemma-oprf-service",
  "version": "1.0.0",
  "timestamp": 1716403200,
  "epoch": "2025-05-22"
}
```

#### POST /oprf/evaluate

Evaluate a blinded input using the OPRF function.

**Request:**
```http
POST /oprf/evaluate
Content-Type: application/json

{
  "blinded": "base64_encoded_blinded_data"
}
```

**Response:**
```json
{
  "evaluated": "base64_encoded_evaluated_data",
  "key_id": "current_key_id",
  "epoch": "2025-05-22"
}
```

#### GET /oprf/cascade

Get the current revocation cascade.

**Request:**
```http
GET /oprf/cascade
```

**Response:**
```json
{
  "epoch": "2025-05-22",
  "cascade": {
    "levels": [
      {
        "size": 1000,
        "bits": "base64_encoded_bits"
      },
      {
        "size": 10000,
        "bits": "base64_encoded_bits"
      }
    ],
    "metadata": {
      "total_revoked": 100,
      "false_positive_rate": 0.001
    }
  }
}
```

### Client-Side OPRF Integration

The Lemma wallet includes built-in support for OPRF revocation checking. To use it:

```javascript
// Check if a credential is revoked
async function checkRevocation(credentialId) {
  if (!window.lemmaWallet) {
    throw new Error("Lemma wallet not available");
  }
  
  // Get the OPRF client from the wallet
  const oprfClient = window.lemmaWallet.getOPRFClient();
  
  // Check if the credential is revoked
  const isRevoked = await oprfClient.checkRevocation(credentialId);
  
  return isRevoked;
}

// Example usage
checkRevocation("urn:uuid:3e4fc296-88c5-4081-a9ec-c131e9c9b120").then(isRevoked => {
  if (isRevoked) {
    console.log("Credential is revoked");
  } else {
    console.log("Credential is valid");
  }
});
```

For more information on the OPRF revocation system, see the [OPRF_REVOCATION_README.md](./OPRF_REVOCATION_README.md) file.