# Lemma: A Network of Verified Humans

*The essential proof of humanness for digital trust*

A secure, modular, enterprise-grade implementation for verifying humans with minimal data collection and strong cryptographic standards.

**Latest Version: 2.1.0** (Updated May 2025)

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

## What's New in Version 2.1.0

- **Lemma Wallet Integration**: Added a built-in wallet that automatically appears on any Lemma-integrated page, allowing users to manage multiple credentials.
- **Enhanced Home Page Flow**: The "Verify Lemma" button now automatically issues, stores, and verifies credentials locally without redirects.
- **Improved User Feedback**: The "Access Protected Content" button now displays a clear error message on the same page when no lemma is found instead of redirecting.
- **Protected Content Enhancements**: Users can now view their Lemma credential details directly on the protected page.
- **Credential Management**: Added ability to clear Lemma credentials directly from the protected page.
- **Better Error Handling**: Improved error messages and feedback throughout the verification flow.
- **Fixed CSRF Issues**: Resolved CSRF token handling for more reliable deployment, especially on Heroku.
- **Local Storage Integration**: Improved integration with browser's local storage for seamless credential persistence.
- **Auto-Hiding Messages**: Error notifications now automatically hide after a few seconds for better UX.

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
- **Portable Wallet:** Client-side credential wallet that can be integrated into any website.

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

### Frontend Components
- **`static/js/lemma-wallet.js`:** Client-side wallet for storing and managing Lemma credentials.
- **`static/js/lemma-wallet-init.js`:** Automatic wallet initialization for Lemma-integrated pages.

### Templates
- **`templates/index.html`:** Landing page with "Verify Lemma" and "Access Protected Content" buttons.
- **`templates/verify.html`:** Credential verification and storage page.
- **`templates/protected.html`:** Content requiring human verification with credential management.
- **`templates/admin_login.html`:** Secure admin login.
- **`templates/admin.html`:** Admin dashboard for issuing credentials.
- **`templates/layout.html`:** Common layout template with wallet integration.

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

## User Flows

### Home Page Flow (New)
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
1. **Admin Authentication:** Secure login at `/admin/login` (password hashing, CSRF protection).
2. **Credential Issuance:** Admin enters a user ID at `/admin/issue` to issue a credential.
3. **Verification Link:** System generates a shareable verification link.
4. **User Verification:** User opens the verification link to `/verify?user_id={user_id}` to store their credential.
5. **Local Storage:** Credential is stored in the user's browser.
6. **Cross-Page Access:** User can access protected content at `/protected` using their credential.

### Protected Content Management (New)
1. **View Credential:** Users can view their Lemma credential details directly on the protected page.
2. **Credential Management:** Users can clear their stored credential using the "Clear Lemma" button.
3. **Import Functionality:** Users can import a previously downloaded credential.
4. **Session-Based Access:** Access is maintained via both browser storage and server session.

### Zero-Knowledge Verification Flow
1. **Minimal Proof Creation:** User creates a zero-knowledge proof that only reveals they're human.
2. **Challenge-Response:** System issues a challenge that the user signs with their credential.
3. **Privacy-Preserving Verification:** System verifies the proof without seeing the full credential.
4. **Selective Attribute Sharing:** User can choose which credential attributes to reveal.
5. **Hardware-Backed Verification:** When available, verification leverages secure hardware.

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

#### Troubleshooting Heroku Deployment

If you encounter CSRF token errors when deploying to Heroku (such as "csrf_token is undefined" in the verify.html template), we've implemented the following fixes:

1. Added a context processor to inject the CSRF token into all templates rendered by the main blueprint:
   ```python
   # In lemma/routes/main.py
   @main_bp.context_processor
   def inject_csrf_token():
       return {'csrf_token': generate_csrf_token()}
   ```

2. Updated the templates to access the token as a variable instead of a function call:
   ```html
   <!-- In templates like verify.html -->
   <meta name="csrf-token" content="{{ csrf_token }}">
   ```

This solution ensures that CSRF tokens are properly available in templates when deployed to Heroku's environment, preventing 500 errors during the verification process.

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
- **GET /api/credential-lookup/{user_id}:** Get a user's credential (auto-issues if not found)
- **GET /api/user-credential/{user_id}:** Get a user's credential (requires API key)
- **GET /api/credentials:** List all credentials (requires API key and admin authentication)
- **POST /api/presentation:** Create a presentation from a credential
- **POST /api/verify-human:** Verify a human presentation and set session
- **POST /api/logout:** Clear the verification session
- **GET /api/generate-csrf-token:** Generate a CSRF token for secure form submission

### Decentralized Identity Endpoints
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
- Adjust the credential expiration in the credential service or `app.py` (default: 1 year).
- Add additional protected pages by following the pattern in `protected.html`.
- Customize security settings in `lemma/__init__.py`.
- Configure preferred DID methods using environment variables.
- Set up P2P peers for decentralized revocation.
- Style error messages and notifications to match your design system.

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
