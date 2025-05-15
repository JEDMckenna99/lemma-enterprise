# Lemma: A Network of Verified Humans

*The essential proof of humanness for digital trust*

A secure, modular, enterprise-grade implementation for verifying humans with minimal data collection and strong cryptographic standards.

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

---

## Key Features

- **Modular Architecture:** Clean separation of concerns for maintainability.
- **Enhanced Security:** Password hashing, CSRF protection, secure cookies, encrypted storage, and rate limiting.
- **Comprehensive Testing:** Full test coverage for all critical paths.
- **Improved UX:** Auto-redirects and detailed error feedback.
- **Multiple Deployment Options:** Easy deployment with Docker, Heroku, or Azure Web Apps.
- **Audit Logging:** Comprehensive logging for security events.
- **Decentralized Verification:** No central authority needed for credential verification.
- **Hardware-Backed Security:** Support for TPM, Secure Enclave, and Android Keystore.
- **P2P Revocation:** Decentralized credential revocation broadcast system.

---

## Architecture & Components

### Core Backend
- **`app.py`:** Main Flask application and entry point.
- **`lemma/__init__.py`:** Application factory and configuration.
- **`lemma/core/credential_service.py`:** Credential issuance and verification logic.
- **`lemma/core/did_resolver.py`:** Multi-method DID resolver for decentralized identity.
- **`lemma/core/revocation.py`:** P2P revocation system with compact bitstrings.
- **`lemma/auth/security.py`:** Authentication and security features.
- **`lemma/routes/`:** Modular route handlers.
- **`lemma/utils/zero_knowledge.py`:** Zero-knowledge proof utilities for selective disclosure.
- **`lemma/utils/secure_storage.py`:** Hardware-backed key storage utilities.
- **`lemma/models/`:** Data models.
- **`tests/`:** Comprehensive test suite.

### Templates
- **`templates/index.html`:** Landing page with "Verify Lemma" button.
- **`templates/verify.html`:** Credential verification and storage page.
- **`templates/protected.html`:** Content requiring human verification.
- **`templates/admin_login.html`:** Secure admin login.
- **`templates/admin.html`:** Admin dashboard for issuing credentials.

### Storage System
- **`.lemma_enterprise/`:** (Created automatically) Contains cryptographic keys and credential registry:
  - `keys.json`: Ed25519 keys
  - `registry.json`: Issued credentials
  - `users.json`: User IDs (no personal data)
  - `revocation/`: Revocation data for decentralized verification

---

## Decentralized Identity Features

Lemma now includes a fully decentralized identity system that addresses 8 key goals:

### 1. Decentralized Identifier Management
- Support for multiple DID methods (`did:key`, `did:web`, `did:ethr`, `did:lemma`)
- Credentials remain valid even if the issuing authority goes offline
- Cross-platform interoperability with other identity systems

### 2. Client-Side Key Protection
- Hardware-backed key storage (TPM, Secure Enclave, Android Keystore)
- Secure credential backups with password protection
- Private keys never leave the user's device

### 3. End-to-End Encryption of Credentials
- Zero-knowledge proof utilities for minimal data disclosure
- Selective disclosure of only the `isHuman: true` claim
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

## Flows

### Admin Onboarding Flow
1. **Admin Authentication:** Secure login at `/admin/login` (password hashing, CSRF protection).
2. **Credential Issuance:** Admin enters a user ID at `/admin/issue` to issue a credential.
3. **Verification Link:** System generates a shareable verification link.
4. **User Verification:** User opens the verification link to `/verify?user_id={user_id}` to store their credential.
5. **Local Storage:** Credential is stored in the user's browser.
6. **Cross-Page Access:** User can access protected content at `/protected` using their credential.

### User Verification Flow
1. **Link Access:** User opens the verification link or clicks "Verify Lemma" on the homepage.
2. **Credential Retrieval:** System provides the credential (auto-issues if not found).
3. **Local Storage:** Credential is stored in browser local storage.
4. **Presentation Creation:** System creates a verifiable presentation.
5. **Verification Status:** User can see their verification status and manage credentials.

### Cross-Page Verification Flow
1. **Protected Access:** User attempts to access protected content via "Access Protected Content".
2. **Credential Check:** System checks for a stored Lemma credential.
3. **Presentation Verification:** System verifies the presentation.
4. **Access Grant:** User is granted access to protected content if verification passes.
5. **Redirect:** If no valid credential is found, user is redirected to the verification page.

### Zero-Knowledge Verification Flow
1. **Minimal Proof Creation:** User creates a zero-knowledge proof that only reveals they're human.
2. **Challenge-Response:** System issues a challenge that the user signs with their credential.
3. **Privacy-Preserving Verification:** System verifies the proof without seeing the full credential.
4. **Selective Attribute Sharing:** User can choose which credential attributes to reveal.
5. **Hardware-Backed Verification:** When available, verification leverages secure hardware.

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
# For decentralized features
heroku config:set DID_METHOD=key
heroku config:set LEMMA_ENABLE_P2P=true
heroku config:set LEMMA_HARDWARE_SECURITY=true

# Deploy the application
git push heroku main

# Open the application
heroku open
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

### Endpoints
- **GET /api/health:** Health check endpoint
- **POST /api/issue-credential:** Issue a credential (requires API key)
- **POST /api/verify-credential:** Verify a credential
- **GET /api/generate-challenge:** Generate a challenge for presentation verification
- **POST /api/verify-presentation:** Verify a presentation
- **GET /api/credential/{user_id}:** Get a user's credential (auto-issues if not found)
- **GET /api/credentials/{user_id}:** Get a user's credential (requires API key)
- **GET /api/credentials:** List all credentials (requires API key and admin authentication)
- **POST /api/presentation:** Create a presentation from a credential
- **POST /api/verify-human:** Verify a human presentation and set session

### New Decentralized Identity Endpoints
- **POST /api/create-minimal-proof:** Create a minimal zero-knowledge proof
- **POST /api/verify-minimal-proof:** Verify a minimal zero-knowledge proof
- **POST /api/create-selective-disclosure:** Create a selective disclosure
- **POST /api/verify-selective-disclosure:** Verify a selective disclosure
- **POST /api/verify-with-hardware:** Verify using hardware-backed security

---

## Security Considerations

- **Admin Credentials:** Set strong admin credentials via environment variables.
- **Session Secret:** Use a strong random value for `LEMMA_SECRET_KEY`.
- **API Key:** Set a strong API key for external integrations.
- **Key Protection:** The `.lemma_enterprise` directory contains cryptographic keys—keep it secure.
- **HTTPS:** Always use HTTPS in production for secure credential transmission.
- **Rate Limiting:** API endpoints are protected against abuse.
- **Password Hashing:** Admin passwords are securely hashed.
- **CSRF Protection:** All forms are protected against CSRF attacks.
- **Encrypted Storage:** Sensitive data is encrypted at rest.
- **Minimal Data Collection:** Only stores that a user is human—no personal information.
- **Hardware Security:** Use hardware-backed key storage when available.
- **Decentralized Verification:** No single point of failure for credential verification.

---

## Customization

- Modify the HTML templates to match your branding.
- Adjust the credential expiration in the credential service or `app.py` (default: 1 year).
- Add additional protected pages by following the pattern in `protected.html`.
- Customize security settings in `lemma/__init__.py`.
- Configure preferred DID methods using environment variables.
- Set up P2P peers for decentralized revocation.

---

## Credential Storage and Cross-Device Support

Lemma uses a combination of approaches to help users manage their Verifiable Credentials across devices.

### Current Implementation

The system currently supports:

- **Browser LocalStorage**: Credentials are automatically stored in the browser's localStorage for seamless use on a single device.
- **Downloadable JSON Backup**: Users can download their credential as a JSON file which can be backed up or transferred to other devices.
- **Import Functionality**: Users can import previously downloaded JSON credentials on any device, enabling cross-device credential use.
- **Encrypted Backups**: Password-protected credential backups with the `EncryptedBackup` utility.
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

---

## License

This project is licensed under the MIT License. See the LICENSE file for details. 
