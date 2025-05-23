# Lemma: A Network of Verified Humans

*The essential proof of humanness for digital trust*

A secure, modular, enterprise-grade implementation for verifying humans with minimal data collection and strong cryptographic standards.

**Latest Version: 2.2.0** (Updated December 2024)

---

## Our Ethos

Lemma exists to solve one fundamental problem in the digital world: **proving that a user is a unique human being, nothing more and nothing less**.

We believe:

- **Privacy is paramount**: We collect only what's necessary to verify humanness, protecting user data while enabling trust.
- **Simplicity is powerful**: A focused solution that does one thing exceptionally well creates more value than complex systems that do many things adequately.
- **Offline verification matters**: By enabling credential verification without requiring an active internet connection, we create a more resilient digital ecosystem.
- **Bots undermine digital trust**: When nearly 40% of internet traffic is non-human, businesses need a reliable way to ensure they're interacting with real people.
- **Self-sovereignty is essential**: Users should control their own identity and determine what information they share with whom.

Lemma provides the simple proof that allows larger business functions to operate smoothly in a world increasingly challenged by sophisticated bots and automated systems.

---

## Overview

Lemma Enterprise provides a complete solution for trusted admin onboarding of verified humans to the Lemma network. The system focuses on:

- **Minimal Data Collection:** Only verifies that a user is human—no additional personal information is collected.
- **Strong Encryption:** Uses Ed25519 signatures and DID-based identifiers for cryptographic security.
- **Cross-Page Verification:** Demonstrates how verification works across different pages.
- **W3C Standards:** Issues standard Verifiable Credentials and Presentations.
- **Privacy by Design:** Credentials are stored in the user's browser, not in a central database.
- **Offline Verification:** Credentials can be verified without requiring an active internet connection.
- **Bot Prevention:** Fundamentally cuts bots at their core by making it impossible to generate valid credentials without human verification.
- **Decentralized Identity:** Supports multiple DID methods and true self-sovereign identity.
- **Zero-Knowledge Proofs:** Enables selective disclosure for maximum privacy.
- **Enterprise Security:** Production-ready security with comprehensive input validation and CSRF protection.

---

## What's New in Version 2.2.0

### 🔒 Enhanced Security Features
- **Simplified CSRF Protection:** Removed development-specific exemptions and Windows-specific workarounds for consistent security across all environments
- **Comprehensive Input Validation:** Added robust validation for all API endpoints with proper error handling and security limits
- **Production-Ready Builds:** Eliminated debug code and print statements from production deployments
- **Improved Key Management:** Enhanced key persistence strategy for Heroku and cloud deployments with external storage support

### 🛡️ Security Improvements
- **Uniform CSRF Protection:** `SameSite=Strict` cookies and consistent token validation
- **Input Sanitization:** Comprehensive validation for credentials, presentations, challenges, and API keys
- **Secure Logging:** Removed information leakage through debug statements
- **External Key Storage:** Support for AWS S3, Azure Blob, and HTTP-based key persistence

### 🔧 Production Enhancements
- **Environment Detection:** Automatic production/development mode detection
- **Secure Cookie Handling:** Proper cookie security based on deployment environment
- **Rate Limiting:** Enhanced protection against abuse with configurable limits
- **Error Handling:** Improved error responses without information disclosure

### 🚀 Previous Features (v2.1.0)
- **Lemma Wallet Integration**: Built-in wallet that automatically appears on any Lemma-integrated page
- **Enhanced Home Page Flow**: Automatic credential issuance, storage, and verification
- **Improved User Feedback**: Clear error messages and auto-hiding notifications
- **Protected Content Enhancements**: Direct credential management from protected pages
- **Lemma Network Access**: Interactive, paginated view of the Lemma Network
- **Credential Management**: Import/export functionality for cross-device use
- **Fixed CSRF Issues**: Resolved token handling for reliable deployment

---

## Key Features

- **Modular Architecture:** Clean separation of concerns for maintainability.
- **Enterprise Security:** Production-grade CSRF protection, input validation, secure cookies, encrypted storage, and rate limiting.
- **Comprehensive Testing:** Full test coverage for all critical paths.
- **Improved UX:** Auto-redirects and detailed error feedback.
- **Multiple Deployment Options:** Easy deployment with Docker, Heroku, or Azure Web Apps.
- **Audit Logging:** Comprehensive logging for security events.
- **Decentralized Verification:** No central authority needed for credential verification.
- **Hardware-Backed Security:** Support for TPM, Secure Enclave, and Android Keystore.
- **P2P Revocation:** Decentralized credential revocation broadcast system.
- **Portable Wallet:** Client-side credential wallet that can be integrated into any website.
- **Security-First Design:** All endpoints protected with validation, rate limiting, and proper authentication.

---

## Architecture & Components

### Core Backend
- **app.py:** Main Flask application and entry point.
- **lemma/__init__.py:** Application factory and configuration with production security settings.
- **lemma/core/credential_service.py:** Credential issuance and verification logic with enhanced key management.
- **lemma/core/did_resolver.py:** Multi-method DID resolver for decentralized identity.
- **lemma/core/revocation.py:** P2P revocation system with compact bitstrings.
- **lemma/auth/security.py:** Authentication and security features.
- **lemma/auth/csrf_config.py:** Enhanced CSRF protection configuration.
- **lemma/utils/input_validation.py:** Comprehensive input validation for all API endpoints.
- **lemma/routes/:** Modular route handlers with security middleware.
- **lemma/utils/zero_knowledge.py:** Zero-knowledge proof utilities for selective disclosure.
- **lemma/utils/secure_storage.py:** Hardware-backed key storage utilities.
- **lemma/models/:** Data models.
- **tests/:** Comprehensive test suite.

### Frontend Components
- **static/js/lemma-wallet.js:** Client-side wallet for storing and managing Lemma credentials.
- **static/js/lemma-wallet-init.js:** Automatic wallet initialization for Lemma-integrated pages.
- **static/js/lemma-plan.js:** Interactive, paginated display of the Lemma Network for verified users.
- **static/js/lemma-plan.css:** Styling for the Lemma Network display.

### Templates
- **templates/index.html:** Landing page with "Verify Lemma" and "Access Protected Content" buttons.
- **templates/verify.html:** Credential verification and storage page.
- **templates/protected.html:** Content requiring human verification with credential management.
- **templates/admin_login.html:** Secure admin login.
- **templates/admin.html:** Admin dashboard for issuing credentials.
- **templates/layout.html:** Common layout template with wallet integration.

### Storage System
- **.lemma_enterprise/:** (Created automatically) Contains cryptographic keys and credential registry:
  - keys.json: Ed25519 keys with encryption
  - registry.json: Issued credentials
  - users.json: User IDs (no personal data)
  - revocation/: Revocation data for decentralized verification

---

## Security Architecture

### Production Security Features
- **CSRF Protection:** Simplified, consistent protection across all environments with secure cookie handling
- **Input Validation:** Comprehensive validation for all API inputs with security limits and proper error handling
- **Rate Limiting:** Protection against abuse with configurable request limits per IP
- **Secure Logging:** Production builds automatically remove debug information and print statements
- **Key Management:** Enhanced persistence strategy with support for external storage services

### Security Headers & Policies
- **HTTPS Enforcement:** All OIDC4VP implementations enforce HTTPS in production environments
- **Security Headers:**
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: SAMEORIGIN  
  - X-XSS-Protection: 1; mode=block
  - Strict-Transport-Security with includeSubDomains (production only)
- **Session Security:**
  - 30-minute session lifetime
  - Secure and HttpOnly cookie flags
  - SameSite=Strict policy for CSRF protection

### Input Validation & Sanitization
- **Credential Validation:** Structure, signature, and content validation
- **API Security:** All endpoints protected with comprehensive input validation
- **Rate Limiting:** Configurable limits with IP-based tracking
- **Error Handling:** Secure error responses without information disclosure

---

## Decentralized Identity Features

Lemma includes a fully decentralized identity system that addresses 8 key goals:

### 1. Decentralized Identifier Management
- Support for multiple DID methods (did:key, did:web, did:ethr, did:lemma)
- Credentials remain valid even if the issuing authority goes offline
- Cross-platform interoperability with other identity systems

### 2. Client-Side Key Protection
- Hardware-backed key storage (TPM, Secure Enclave, Android Keystore)
- Secure credential backups with password protection
- Private keys never leave the user's device

### 3. End-to-End Encryption of Credentials
- Zero-knowledge proof utilities for minimal data disclosure
- Selective disclosure of only the isHuman: true claim
- JWT-based proof formats for standardized verification

### 4. Peer-to-Peer Revocation Broadcast
- Compact revocation bitstrings (CRSets) for efficient storage
- Bloom filter-based lookups for fast verification
- P2P synchronization of revocation information

### 5. Interoperability & Open Standards
- Strict adherence to W3C Verifiable Credentials and DID standards
- Support for multiple proof types and verification methods
- Seamless integration with existing identity ecosystems

### 6. Privacy-First Data Minimization
- Selective disclosure mechanisms for fine-grained control
- Zero-knowledge proofs that reveal only verification results
- Ephemeral sessions that don't leave lasting traces

### 7. Self-Hosted & Federated Deployment
- Configuration options for federated nodes
- P2P network for decentralized verification
- No central server required for the network to function

### 8. Auditable & Open Verification
- Transparent cryptographic operations
- Detailed logging for security operations
- Configurable trust policies for verifiers

---

## OPRF-Cascaded Bloom Revocation

Lemma implements a privacy-preserving revocation system using Oblivious Pseudorandom Functions (OPRF) with cascaded Bloom filters.

### Key Features

1. **Privacy-Preserving**: The OPRF protocol ensures the issuer never learns which credentials are being checked for revocation status.

2. **Efficient Synchronization**: The cascaded Bloom filter structure reduces bandwidth requirements to <100 kB per 1M revoked credentials.

3. **Offline Verification**: Credentials include revocation "witnesses" that can be verified locally without an active internet connection.

4. **Zero Metadata Leakage**: The system reveals no information about which credentials are being verified to any party.

### How It Works

1. **Credential Issuance**: When a credential is issued, the user receives a standard W3C Verifiable Credential.

2. **Revocation Process**: When credentials are revoked, the system:
   - Applies the OPRF function (with secret key k) to each revoked credential ID
   - Inserts the resulting values into a multi-level cascaded Bloom filter
   - Publishes the signed cascade for verifiers to download

3. **Client Verification**: To check if a credential is valid:
   - The client generates a random blinding factor r
   - Computes α = r·H₁(credential_id) and sends α to the issuer
   - Issuer returns β = α^k without learning the credential ID
   - Client computes y = β^(r⁻¹), the unblinded OPRF output
   - Client checks if y is in the cascade - if not, the credential is valid

4. **Offline Verification**: The client attaches a witness (α, β, r) to presentations, allowing verifiers to check revocation status without contacting the issuer.

### Technical Details

- Based on the ristretto255 elliptic curve implementation
- OPRF protocol following RFC 9497
- False positive rate: ~2% at the first level, ~0.0008% overall with 3-level cascade
- Client operations require only 1 OPRF evaluation per credential per epoch (typically daily)

See [OPRF_REVOCATION_README.md](./OPRF_REVOCATION_README.md) for detailed implementation information.

---

## User Flows

### Home Page Flow
1. **Initial Entry:** User visits the home page with two main actions: "Verify Lemma" and "Access Protected Content".
2. **Lemma Verification:** Clicking "Verify Lemma" automatically:
   - Generates a unique user ID
   - Issues a new credential
   - Stores the credential in browser's local storage
   - Creates a verification presentation
   - Redirects to the protected page upon successful verification
3. **Protected Access:** Clicking "Access Protected Content":
   - Checks if a Lemma credential exists in local storage
   - If no credential exists, displays an error message on the home page
   - If a credential exists, creates a presentation and verifies it
   - Redirects to protected content upon successful verification

### Admin Onboarding Flow
1. **Admin Authentication:** Secure login at /admin/login (password hashing, CSRF protection).
2. **Credential Issuance:** Admin enters a user ID at /admin/issue to issue a credential.
3. **Verification Link:** System generates a shareable verification link.
4. **User Verification:** User opens the verification link to /verify?user_id={user_id} to store their credential.
5. **Local Storage:** Credential is stored in the user's browser.
6. **Cross-Page Access:** User can access protected content at /protected using their credential.

### Protected Content Management
1. **View Credential:** Users can view their Lemma credential details directly on the protected page.
2. **Credential Management:** Users can clear their stored credential using the "Clear Lemma" button.
3. **Import Functionality:** Users can import a previously downloaded credential.
4. **Lemma Network Access:** Users can view the detailed Lemma Network with an interactive, paginated interface.
5. **Session-Based Access:** Access is maintained via both browser storage and server session.

### Zero-Knowledge Verification Flow
1. **Minimal Proof Creation:** User creates a zero-knowledge proof that only reveals they're human.
2. **Challenge-Response:** System issues a challenge that the user signs with their credential.
3. **Privacy-Preserving Verification:** System verifies the proof without seeing the full credential.
4. **Selective Attribute Sharing:** User can choose which credential attributes to reveal.
5. **Hardware-Backed Verification:** When available, verification leverages secure hardware.

### Detailed Verification Workflows

#### Stripe Identity Verification to Credential Issuance
The Lemma system uses Stripe Identity for robust human verification before issuing credentials:

1. **Initiation:** User clicks "Verify Lemma" on the home page or visits /start-verification/{user_id}.
2. **Identity Verification:**
   - Lemma creates a Stripe Identity verification session
   - User is redirected to Stripe's hosted verification UI
   - User completes the identity verification process (ID document + selfie)
3. **Callback Processing:**
   - Stripe redirects back to /verification-callback?user_id={user_id}
   - Lemma checks verification status via Stripe API
   - If verification passes, a Verifiable Credential (VC) is issued
4. **Credential Storage:**
   - Credential is stored in the session
   - Credential is passed to the template for client-side storage
   - The Lemma wallet (IndexedDB-based) automatically detects and stores the credential
   - The wallet UI makes the credential accessible across the Lemma ecosystem
5. **Result:** User is redirected to the protected page with their new human verification credential

This secure workflow ensures only real humans receive credentials while collecting minimal personal data, as the ID verification occurs within Stripe's secure environment.

#### Verifiable Presentation Creation and Verification
For third-party sites integrating with Lemma, this workflow enables credential verification:

1. **Integration Setup:**
   - Customer site receives a unique DID (Decentralized Identifier) via the Lemma API
   - Customer integrates the Lemma wallet JavaScript components
2. **Presentation Request:**
   - When a user visits the customer site, it checks for a Lemma credential
   - Site generates a random challenge to prevent replay attacks
   - Site requests a Verifiable Presentation from the user's wallet
3. **Presentation Creation:**
   - Wallet creates a Verifiable Presentation (VP) containing:
     - The user's human verification credential
     - Proof of possession (signature over the challenge)
     - Minimum necessary claims (typically just isHuman: true)
4. **Verification Process:**
   - Customer site sends the VP to their backend
   - Backend verifies the VP against Lemma's verification API
   - API validates the cryptographic proof and credential status
   - API returns verification result to the customer backend
5. **Authorization:** If verification succeeds, the customer site grants access to protected content

This workflow enables a "verify once, use anywhere" model where users don't need to repeatedly prove their humanity across different sites in the Lemma network.

---

## Customer Site Integration

Lemma is designed to be easily integrated into customer sites, allowing them to verify users as humans without collecting personal data.

### Basic Integration
```html
<!-- Add these scripts to your website -->
<script src="https://your-lemma-instance.com/static/js/lemma-wallet.js"></script>
<script src="https://your-lemma-instance.com/static/js/lemma-wallet-init.js"></script>

<!-- Add this attribute to enable the wallet on your page -->
<div data-lemma="true">
  <!-- Your protected content goes here -->
</div>
```

### JavaScript API Integration
```javascript
// Verify a user with Lemma
async function verifyWithLemma() {
  // Check if wallet is available
  if (window.lemmaWallet) {
    // Get the first credential from the wallet
    const credential = await window.lemmaWallet.getFirstCredential();
    
    if (credential) {
      // Generate a random challenge
      const challenge = Array.from(crypto.getRandomValues(new Uint8Array(16)))
        .map(b => b.toString(16).padStart(2, '0')).join('');
      
      // Create a verification request to your backend
      const result = await fetch('/api/verify-lemma', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          credential: credential,
          challenge: challenge
        })
      }).then(res => res.json());
      
      if (result.verified) {
        // User is a verified human
        showProtectedContent();
      }
    } else {
      // Redirect to Lemma verification
      window.location.href = "https://your-lemma-instance.com/verify";
    }
  }
}
```

### Backend Verification
On your server, you'll need to verify the Lemma credential presentation:

```python
# Example using the Python requests library
import requests

def verify_lemma_credential(credential, challenge):
    # Send to your Lemma instance for verification
    response = requests.post(
        'https://your-lemma-instance.com/api/verify-human',
        json={
            'presentation': credential,
            'challenge': challenge
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        if result.get('success'):
            # User is verified human
            return True
    
    # Verification failed
    return False
```

The Lemma wallet is designed to be portable and work across websites, which is core to providing "verify once, use anywhere" functionality.

---

## Installation & Deployment

### Prerequisites
- Python 3.9+
- pip
- Git

### Local Development
```bash
# Clone the repository
git clone <repository-url>
cd lemma-enterprise

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export LEMMA_ADMIN_USER=admin
export LEMMA_ADMIN_PASS=secure_password_change_me
export LEMMA_SECRET_KEY=your_secret_key_here
export LEMMA_API_KEY=your_api_key_here
export DID=did:lemma:local
# For decentralized features
export DID_METHOD=key  # Options: key, web, ethr, lemma
export LEMMA_ENABLE_P2P=true
export LEMMA_HARDWARE_SECURITY=true

# Run the application
python app.py
```

### Docker Deployment
```bash
# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f
```

### Heroku Deployment

#### Quick Deployment with OPRF Cascade Revocation Layer

For the fastest deployment with the complete OPRF cascade revocation system:

**Windows (PowerShell):**
```powershell
.\deploy_with_oprf.ps1
```

**Linux/Mac (Bash):**
```bash
./deploy_with_oprf.sh
```

#### Manual Heroku Deployment

```bash
# Login to Heroku
heroku login

# Create a new Heroku app
heroku create lemma-enterprise-app

# Set required environment variables
heroku config:set LEMMA_ADMIN_USER=admin
heroku config:set LEMMA_ADMIN_PASS=secure_password_change_me
heroku config:set LEMMA_SECRET_KEY=your_secret_key_here
heroku config:set LEMMA_API_KEY=your_api_key_here
heroku config:set DID=did:lemma:heroku

# Enable OPRF cascade revocation layer
heroku config:set OPRF_SERVICE_INTERNAL=true
heroku config:set OPRF_RATE_LIMIT=60
heroku config:set OPRF_ROTATION_DAYS=30
heroku config:set OPRF_DEBUG=false

# For decentralized features
heroku config:set DID_METHOD=key
heroku config:set LEMMA_ENABLE_P2P=true
heroku config:set LEMMA_HARDWARE_SECURITY=true
# For external key storage (optional)
heroku config:set LEMMA_EXTERNAL_STORAGE_URL=s3://your-bucket/keys.json
heroku config:set AWS_ACCESS_KEY_ID=your_access_key
heroku config:set AWS_SECRET_ACCESS_KEY=your_secret_key

# Deploy the application
git push heroku main

# Scale both web and OPRF processes
heroku ps:scale web=1 oprf=1

# Open the application
heroku open
```

#### OPRF Service Verification

After deployment, verify the OPRF cascade revocation layer is operational:

```bash
# Check process status
heroku ps

# View OPRF service logs
heroku logs --tail --dyno=oprf

# Test OPRF integration
curl https://your-app.herokuapp.com/api/oprf/status
```

Expected response:
```json
{
  "status": "ok",
  "oprf_service": "internal",
  "oprf_response": {
    "status": "ok",
    "service": "oprf",
    "version": "1.0.0"
  }
}
```

### Azure Deployment
1. **Create an Azure Web App:**
   ```bash
   az webapp create --resource-group YourResourceGroup --plan YourAppServicePlan --name LemmaHumanVerification --runtime "PYTHON:3.9"
   ```

2. **Set Environment Variables:**
   ```bash
   az webapp config appsettings set --resource-group YourResourceGroup --name LemmaHumanVerification --settings LEMMA_ADMIN_USER="your_admin_username" LEMMA_ADMIN_PASS="your_secure_password" LEMMA_SECRET_KEY="your_random_secret" DID="did:lemma:azure" DID_METHOD="key" LEMMA_ENABLE_P2P="true"
   ```

3. **Deploy the Code:**
   ```bash
   az webapp deployment source config-zip --resource-group YourResourceGroup --name LemmaHumanVerification --src lemma-enterprise.zip
   ```

---

## API Documentation

### Authentication
All API endpoints that modify data require an API key:
```
X-API-Key: your_api_key_here
```

### Core Endpoints
- **GET /api/health:** Health check endpoint
- **POST /api/issue-credential:** Issue a credential (requires API key)
- **POST /api/verify-credential:** Verify a credential with comprehensive validation
- **GET /api/generate-challenge:** Generate a challenge for presentation verification
- **POST /api/verify-presentation:** Verify a presentation with enhanced security
- **GET /api/credential-lookup/{user_id}:** Get a user's credential (auto-issues if not found)
- **GET /api/user-credential/{user_id}:** Get a user's credential (requires API key)
- **GET /api/credentials:** List all credentials (requires API key and admin authentication)
- **POST /api/presentation:** Create a presentation from a credential
- **POST /api/verify-human:** Verify a human presentation and set session
- **POST /api/logout:** Clear the verification session
- **GET /api/generate-csrf-token:** Generate a CSRF token for secure form submission

### Security Endpoints
- **GET /api/generate-csrf:** Generate CSRF token with secure cookie setting
- **POST /api/complete-verification-flow:** All-in-one verification endpoint with comprehensive validation

### Decentralized Identity Endpoints
- **POST /api/create-minimal-proof:** Create a minimal zero-knowledge proof
- **POST /api/verify-minimal-proof:** Verify a minimal zero-knowledge proof
- **POST /api/create-selective-disclosure:** Create a selective disclosure
- **POST /api/verify-selective-disclosure:** Verify a selective disclosure
- **POST /api/verify-with-hardware:** Verify using hardware-backed security

### Revocation & P2P Endpoints
- **GET /api/revocation/status:** Get revocation status for the local node
- **POST /api/revocation/sync:** Manually trigger synchronization with peer nodes
- **POST /api/revocation/import:** Import revocation data from a peer node
- **GET /api/revocation/issuers:** List all issuers in the revocation registry
- **GET /api/revocation/issuer/{issuer_id}:** Get metadata for an issuer's revocation data
- **GET /api/revocation/data/{issuer_id}:** Get the full revocation data for an issuer

---

## Security Considerations

### Production Security
- **Enhanced CSRF Protection:** Uniform protection across all environments with secure cookie handling
- **Comprehensive Input Validation:** All endpoints protected with robust validation and security limits
- **Rate Limiting:** Configurable protection against abuse with IP-based tracking
- **Secure Key Management:** Multiple persistence strategies including external storage for cloud deployments
- **Debug Code Removal:** Automatic removal of debug statements and print calls in production builds

### Core Security Features
- **Admin Credentials:** Set strong admin credentials via environment variables.
- **Session Secret:** Use a strong random value for LEMMA_SECRET_KEY.
- **API Key:** Set a strong API key for external integrations.
- **Key Protection:** Enhanced key management with encryption and external storage options.
- **HTTPS:** Always use HTTPS in production for secure credential transmission.
- **Password Hashing:** Admin passwords are securely hashed.
- **Encrypted Storage:** Sensitive data is encrypted at rest.
- **Minimal Data Collection:** Only stores that a user is human—no personal information.
- **Hardware Security:** Use hardware-backed key storage when available.
- **Decentralized Verification:** No single point of failure for credential verification.

### Security Headers & Policies
- **HTTPS Enforcement:** All OIDC4VP implementations enforce HTTPS in production environments:
  - Strict HTTPS redirection for all requests
  - HTTP Strict Transport Security (HSTS) headers
  - Secure cookie settings with SameSite=Strict
  - SSL/TLS required for all credential operations
- **Enhanced Security Headers:**
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: SAMEORIGIN
  - X-XSS-Protection: 1; mode=block
  - Strict-Transport-Security with includeSubDomains
- **Session Security:**
  - 30-minute session lifetime
  - Secure and HttpOnly cookie flags
  - CSRF protection with SSL enforcement

---

## User Experience Enhancements

### Home Page
- One-click verification with the "Verify Lemma" button
- Clear feedback with inline error messages for "Access Protected Content"
- Auto-hiding notifications for better user experience
- Mobile-responsive design with optimized button layout

### Protected Content Page
- View Lemma credential details with the "View Lemma" button
- Clear stored credentials with the "Clear Lemma" button 
- Import functionality for cross-device credential management
- Clear verification status indicators

### Credential Management
- Secure local storage of credentials in the browser
- Import/export functionality for credential portability
- Password-protected credential backups
- Session-based verification for seamless browsing

---

## Customization

- Modify the HTML templates to match your branding.
- Adjust the credential expiration in the credential service or app.py (default: 1 year).
- Add additional protected pages by following the pattern in protected.html.
- Customize security settings in lemma/__init__.py.
- Configure preferred DID methods using environment variables.
- Set up P2P peers for decentralized revocation.
- Style error messages and notifications to match your design system.
- Configure input validation limits in lemma/utils/input_validation.py.
- Set up external key storage for cloud deployments.

---

## Credential Storage and Cross-Device Support

Lemma uses a combination of approaches to help users manage their Verifiable Credentials across devices.

### Current Implementation

The system currently supports:

- **Browser LocalStorage**: Credentials are automatically stored in the browser's localStorage for seamless use on a single device.
- **Downloadable JSON Backup**: Users can download their credential as a JSON file which can be backed up or transferred to other devices.
- **Import Functionality**: Users can import previously downloaded JSON credentials on any device, enabling cross-device credential use.
- **Encrypted Backups**: Password-protected credential backups with the EncryptedBackup utility.
- **Hardware-Backed Storage**: Support for storing keys in TPM, Secure Enclave, or Android Keystore.

This implementation ensures users can:
1. Use their credential automatically on the device where they initially verified
2. Backup their credential securely to prevent data loss
3. Transfer their credential to other devices (desktop or mobile) with encryption
4. Leverage hardware security when available

### Future Plans

We're planning to integrate with digital wallet solutions for improved user experience:

- **Apple Wallet Integration**: Future versions will support adding Lemma credentials to Apple Wallet as passes.
- **Google Wallet Integration**: Support for Google Wallet will be added as Google expands their digital ID capabilities.
- **W3C Standards Compliance**: All wallet integrations will maintain compliance with W3C Verifiable Credentials standards.
- **Decentralized Identity Wallets**: Support for third-party decentralized identity wallets.

These integrations will enable:
- One-tap credential storage
- Simple cross-device transfer
- Increased security through device-level authentication
- Familiar user interfaces for credential management

---

## Testing

The system includes comprehensive tests for all critical paths:
```bash
# Run all tests with coverage report
python run_tests.py

# Or use pytest directly
pytest -v --cov=lemma
```

### Security Testing
Version 2.2.0 includes enhanced security testing:
- CSRF protection validation
- Input validation boundary testing
- Rate limiting verification
- Authentication and authorization tests
- Key management security tests

---

## Documentation

- **[SECURITY_IMPROVEMENTS.md](./SECURITY_IMPROVEMENTS.md):** Detailed documentation of the security enhancements in version 2.2.0
- **[OPRF_REVOCATION_README.md](./OPRF_REVOCATION_README.md):** Technical details on the OPRF revocation system
- **API Documentation:** Available at `/api/docs` when running the application

---

## License

This project is licensed under the MIT License. See the LICENSE file for details.