# Lemma Enterprise: Component Summary

This document provides a summary of all the components in the Lemma Human Verification System, explaining their purpose and how they work together.

## Core Components

### 1. Backend Application (`app.py`)

The main Flask application that provides:

- **DID-based Credential Issuance**: Issues W3C Verifiable Credentials that verify a user is human
- **Cryptographic Security**: Uses Ed25519 signatures for enterprise-grade security
- **Minimal Storage**: File-based storage for keys and credential registry
- **Admin Authentication**: Secure login for trusted admins
- **Verifiable Presentations**: Supports cross-page verification with cryptographic proofs

### 2. HTML Templates

#### `index.html`
- Landing page that explains the Lemma Human Network
- Provides links to verification and protected content
- Explains the benefits of the system

#### `verify.html`
- Credential verification and storage interface
- Allows users to:
  - Retrieve their credential
  - Store it in browser local storage
  - Create verifiable presentations
  - Access protected content

#### `protected.html`
- Example of content that requires human verification
- Demonstrates cross-page verification
- Shows how credentials can be used across different pages

#### `admin_login.html`
- Secure login interface for trusted admins
- Simple username/password authentication

#### `admin.html`
- Admin dashboard for issuing credentials to trusted humans
- Allows admins to:
  - Issue credentials to users they've verified as human
  - Generate shareable verification links
  - Manage existing credentials

### 3. Storage System

The `.lemma_enterprise` directory (created automatically) contains:

- **`keys.json`**: Cryptographic keys for signing credentials
- **`registry.json`**: Registry of issued credentials
- **`users.json`**: Basic user information (only IDs, no personal data)

## Workflow Components

### 1. Admin Onboarding Flow

The trusted admin onboarding flow allows admins to mint credentials for users they know are human:

1. **Admin Login**: Secure authentication at `/admin/login`
2. **Credential Issuance**: Admin enters a user ID at `/admin/issue`
3. **Link Generation**: System creates a verification link for the user
4. **Admin Sharing**: Admin shares the link with the trusted human

### 2. User Verification Flow

The user verification flow allows users to receive and store their credential:

1. **Link Access**: User opens the verification link
2. **Credential Retrieval**: System provides the credential
3. **Local Storage**: Credential is stored in browser local storage
4. **Presentation Creation**: System creates a verifiable presentation

### 3. Cross-Page Verification Flow

The cross-page verification flow demonstrates how credentials work across pages:

1. **Protected Access**: User attempts to access protected content
2. **Credential Check**: System checks for a stored credential
3. **Presentation Verification**: System verifies the presentation
4. **Access Grant**: User is granted access to protected content

## Security Components

### 1. Cryptographic System

- **Ed25519 Keys**: High-security elliptic curve cryptography
- **DID-based Identifiers**: Decentralized identifiers for users and issuers
- **Signature Verification**: Cryptographic proof of credential validity

### 2. Admin Security

- **Environment Variables**: Admin credentials stored as environment variables
- **Session Management**: Secure session handling with timeouts
- **HTTPS Enforcement**: Recommended for all production deployments

### 3. Privacy Protection

- **Minimal Data Collection**: Only stores that a user is human - nothing else
- **Local Storage**: Credentials stored on user devices, not in a central database
- **No Personal Information**: No collection of age, document type, or other personal data

## Deployment Components

### 1. Azure Deployment Files

- **`requirements.txt`**: Python dependencies for deployment
- **`DEPLOYMENT.md`**: Step-by-step deployment instructions
- **`LEMMA_README.md`**: System documentation and overview

### 2. Configuration Options

- **Environment Variables**:
  - `LEMMA_ADMIN_USER`: Admin username
  - `LEMMA_ADMIN_PASS`: Admin password
  - `LEMMA_SECRET_KEY`: Secret key for session encryption

## How It All Works Together

1. **Admin Issues Credential**: Using the admin interface, a trusted admin issues a credential to a user they've verified as human
2. **User Stores Credential**: The user receives a link, opens it, and stores the credential in their browser
3. **Cross-Page Verification**: The user can now access protected content across different pages
4. **Security Throughout**: All interactions are secured with cryptographic proofs

This architecture provides a complete, enterprise-grade solution for human verification with minimal data collection, strong security, and cross-page functionality.
