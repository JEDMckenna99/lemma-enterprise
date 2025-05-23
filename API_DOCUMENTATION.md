# Lemma Enterprise API Documentation

This document provides comprehensive documentation for integrating with the Lemma Enterprise API, which enables verification of human identity using decentralized identifiers (DIDs) and verifiable credentials.

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [API Endpoints](#api-endpoints)
4. [Credential Issuance](#credential-issuance)
5. [Credential Verification](#credential-verification)
6. [Error Handling](#error-handling)
7. [Rate Limiting](#rate-limiting)
8. [Example Implementations](#example-implementations)
9. [Webhooks](#webhooks)
10. [OPRF Revocation](#oprf-revocation)
11. [Deployment Architecture](#deployment-architecture)

## Overview

The Lemma Enterprise API allows third-party applications to verify that users are human without collecting personally identifiable information (PII). It uses W3C Verifiable Credentials and Decentralized Identifiers (DIDs) to provide privacy-preserving identity verification.

Key features:
- Privacy-first human verification
- Cryptographically secure credentials
- Revocation checking via OPRF (Oblivious Pseudorandom Function)
- Cross-site credential presentation

## Authentication

All API requests must include authentication using one of the following methods:

### API Key Authentication

Include your API key in the request header:

```
Authorization: Bearer YOUR_API_KEY
```

API keys can be obtained by contacting the Lemma Enterprise administrator.

### JWT Authentication

For client-side applications, use JWT authentication:

1. Obtain a JWT token by calling the `/api/auth/token` endpoint with your API key
2. Include the JWT token in subsequent requests:

```
Authorization: Bearer YOUR_JWT_TOKEN
```

JWT tokens expire after 1 hour and must be refreshed.

## API Endpoints

### Base URL

All API endpoints are relative to the base URL:

```
https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api
```

### Available Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/token` | POST | Obtain a JWT token |
| `/credentials/issue` | POST | Issue a new credential |
| `/credentials/verify` | POST | Verify a credential presentation |
| `/credentials/status` | GET | Check credential status |
| `/oprf/evaluate` | POST | Evaluate an OPRF for revocation checking |
| `/oprf/status` | GET | Check OPRF service status |

## Credential Issuance

Credentials are issued to users after they complete the verification process. The process involves:

1. User initiates verification
2. User completes identity verification
3. Credential is issued to user's wallet
4. User can present credential to verifiers

### Issue Credential Request

```http
POST /api/credentials/issue
Content-Type: application/json
Authorization: Bearer YOUR_API_KEY

{
  "subject_id": "did:web:example.com:users:123",
  "credential_type": "HumanCredential",
  "expiration": "2026-01-01T00:00:00Z",
  "attributes": {
    "isHuman": true,
    "verificationLevel": "basic"
  }
}
```

### Issue Credential Response

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "credential_id": "urn:uuid:123e4567-e89b-12d3-a456-426614174000",
  "issuer": "did:web:lemma-enterprise-0f6ba17076c1.herokuapp.com",
  "issuance_date": "2025-05-22T15:30:45Z",
  "credential": {
    "@context": [
      "https://www.w3.org/2018/credentials/v1",
      "https://lemma.example/contexts/human/v1"
    ],
    "type": ["VerifiableCredential", "HumanCredential"],
    "issuer": "did:web:lemma-enterprise-0f6ba17076c1.herokuapp.com",
    "issuanceDate": "2025-05-22T15:30:45Z",
    "expirationDate": "2026-01-01T00:00:00Z",
    "credentialSubject": {
      "id": "did:web:example.com:users:123",
      "isHuman": true,
      "verificationLevel": "basic"
    },
    "proof": {
      "type": "Ed25519Signature2020",
      "created": "2025-05-22T15:30:45Z",
      "verificationMethod": "did:web:lemma-enterprise-0f6ba17076c1.herokuapp.com#key-1",
      "proofPurpose": "assertionMethod",
      "proofValue": "z58DAdFfa9SkqZMVPxAQpic7ndSayn5NBc2QcbPTsRPtH..."
    }
  }
}
```

## Credential Verification

Verifiers can request and verify credential presentations from users.

### Verify Credential Request

```http
POST /api/credentials/verify
Content-Type: application/json
Authorization: Bearer YOUR_API_KEY

{
  "presentation": {
    "@context": [
      "https://www.w3.org/2018/credentials/v1",
      "https://lemma.example/contexts/human/v1"
    ],
    "type": ["VerifiablePresentation"],
    "verifiableCredential": [{
      "@context": [
        "https://www.w3.org/2018/credentials/v1",
        "https://lemma.example/contexts/human/v1"
      ],
      "type": ["VerifiableCredential", "HumanCredential"],
      "issuer": "did:web:lemma-enterprise-0f6ba17076c1.herokuapp.com",
      "issuanceDate": "2025-05-22T15:30:45Z",
      "expirationDate": "2026-01-01T00:00:00Z",
      "credentialSubject": {
        "id": "did:web:example.com:users:123",
        "isHuman": true,
        "verificationLevel": "basic"
      },
      "proof": {
        "type": "Ed25519Signature2020",
        "created": "2025-05-22T15:30:45Z",
        "verificationMethod": "did:web:lemma-enterprise-0f6ba17076c1.herokuapp.com#key-1",
        "proofPurpose": "assertionMethod",
        "proofValue": "z58DAdFfa9SkqZMVPxAQpic7ndSayn5NBc2QcbPTsRPtH..."
      }
    }],
    "proof": {
      "type": "Ed25519Signature2020",
      "created": "2025-05-22T15:35:22Z",
      "verificationMethod": "did:web:example.com:users:123#key-1",
      "proofPurpose": "authentication",
      "challenge": "1234567890",
      "domain": "verifier.example.com",
      "proofValue": "z6Hgi7RB1JKj2CyPzSmBUUUyRWQYTc7VKZCgXGiRdz..."
    }
  },
  "challenge": "1234567890",
  "domain": "verifier.example.com",
  "check_revocation": true
}
```

### Verify Credential Response

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "verification_result": true,
  "credential_status": "valid",
  "issuer": "did:web:lemma-enterprise-0f6ba17076c1.herokuapp.com",
  "subject": "did:web:example.com:users:123",
  "issuance_date": "2025-05-22T15:30:45Z",
  "expiration_date": "2026-01-01T00:00:00Z",
  "attributes": {
    "isHuman": true,
    "verificationLevel": "basic"
  },
  "revocation_checked": true,
  "revocation_status": "not_revoked"
}
```

## Error Handling

The API uses standard HTTP status codes to indicate success or failure:

- 200 OK: Request succeeded
- 400 Bad Request: Invalid request parameters
- 401 Unauthorized: Authentication failed
- 403 Forbidden: Insufficient permissions
- 404 Not Found: Resource not found
- 429 Too Many Requests: Rate limit exceeded
- 500 Internal Server Error: Server error

Error responses include a JSON body with details:

```json
{
  "error": "invalid_request",
  "error_description": "Missing required parameter: challenge",
  "status_code": 400
}
```

## Rate Limiting

API requests are rate-limited to prevent abuse. Limits are applied per API key:

- Authentication endpoints: 10 requests per minute
- Credential issuance: 30 requests per minute
- Credential verification: 60 requests per minute
- OPRF evaluation: 100 requests per minute

Rate limit headers are included in all responses:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 58
X-RateLimit-Reset: 1621872000
```

## Example Implementations

### JavaScript Client

```javascript
// Example JavaScript client for credential verification
async function verifyCredential(presentation, challenge, domain) {
  const apiKey = 'YOUR_API_KEY';
  const response = await fetch('https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/credentials/verify', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`
    },
    body: JSON.stringify({
      presentation,
      challenge,
      domain,
      check_revocation: true
    })
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(`Verification failed: ${error.error_description}`);
  }
  
  return response.json();
}
```

### Python Client

```python
import requests

def verify_credential(presentation, challenge, domain, api_key):
    """
    Verify a credential presentation using the Lemma Enterprise API.
    
    Args:
        presentation (dict): The verifiable presentation
        challenge (str): The challenge string
        domain (str): The domain string
        api_key (str): Your API key
        
    Returns:
        dict: The verification result
    """
    url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/credentials/verify"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "presentation": presentation,
        "challenge": challenge,
        "domain": domain,
        "check_revocation": True
    }
    
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    
    return response.json()
```

## Webhooks

Lemma Enterprise supports webhooks for asynchronous notifications about credential events:

1. Register a webhook URL in your account settings
2. Configure the events you want to receive
3. Implement an endpoint to receive webhook events

### Webhook Events

- `credential.issued`: A new credential has been issued
- `credential.verified`: A credential has been successfully verified
- `credential.revoked`: A credential has been revoked

### Webhook Payload

```json
{
  "event": "credential.verified",
  "timestamp": "2025-05-22T15:40:12Z",
  "data": {
    "credential_id": "urn:uuid:123e4567-e89b-12d3-a456-426614174000",
    "issuer": "did:web:lemma-enterprise-0f6ba17076c1.herokuapp.com",
    "subject": "did:web:example.com:users:123",
    "verification_result": true
  }
}
```

### Webhook Security

Webhook requests include a signature header for verification:

```
X-Lemma-Signature: t=1621872012,v1=5257a869e7ecebeda32affa62cdca3fa51cad7e77a0e56ff536d0ce8e108d8bd
```

To verify the signature:
1. Split the header value to get the timestamp and signature
2. Compute the HMAC-SHA256 of the request body using your webhook secret
3. Compare the computed signature with the received signature

## OPRF Revocation

Lemma Enterprise uses Oblivious Pseudorandom Functions (OPRFs) for privacy-preserving credential revocation checks. This allows verifying that a credential has not been revoked without revealing the credential identifier.

### OPRF Evaluation Request

```http
POST /api/oprf/evaluate
Content-Type: application/json
Authorization: Bearer YOUR_API_KEY

{
  "blinded_element": "X8cc6e802c5a1c8b3e9b92cf2c8c1c792a91d65137a913f4b3e8c3f197ca1d603",
  "key_id": "2025-05-22-key1"
}
```

### OPRF Evaluation Response

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "evaluated_element": "X1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p7q8r9s0t1u2v3w4x5y6z7a8b9c0d1e2f3g4h5i6j7k8l9m0",
  "key_id": "2025-05-22-key1",
  "proof": "X9s8r7q6p5o4n3m2l1k0j9i8h7g6f5e4d3c2b1a0z9y8x7w6v5u4t3s2r1q0p9o8n7m6l5k4j3i2h1g0f9e8d7c6b5a4"
}
```

For more information on the OPRF revocation system, see the [OPRF_REVOCATION_README.md](./OPRF_REVOCATION_README.md) file.

## Deployment Architecture

The Lemma Enterprise system consists of two separate Heroku applications:

1. **Main Web Application** - A Python/Flask application that handles the user interface, credential issuance, and verification.
2. **OPRF Service** - A Go microservice that provides Oblivious Pseudorandom Function (OPRF) evaluation for privacy-preserving revocation checks.

This separation allows for better scalability and maintenance of each component. The web application communicates with the OPRF service via HTTP requests, using the URL specified in the `OPRF_SERVICE_INTERNAL` environment variable.

### Deployment Process

To deploy the complete system:

1. Deploy the main web application using:
   ```
   git push heroku main
   ```

2. Deploy the OPRF service using the provided script:
   ```
   # On Windows
   .\deploy_oprf_service.ps1
   
   # On Unix/Linux
   ./deploy_oprf_service.sh
   ```

3. Scale both applications as needed:
   ```
   heroku ps:scale web=1 --app lemma-enterprise
   heroku ps:scale web=1 --app lemma-oprf-service
   ```