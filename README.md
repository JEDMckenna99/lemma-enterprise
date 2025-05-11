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

---

## Key Features

- **Modular Architecture:** Clean separation of concerns for maintainability.
- **Enhanced Security:** Password hashing, CSRF protection, secure cookies, encrypted storage, and rate limiting.
- **Comprehensive Testing:** Full test coverage for all critical paths.
- **Improved UX:** Auto-redirects and detailed error feedback.
- **Docker & Azure Support:** Easy deployment with Docker, docker-compose, and Azure Web Apps.
- **Audit Logging:** Comprehensive logging for security events.

---

## Architecture & Components

### Core Backend
- **`app.py`:** Main Flask application and entry point.
- **`lemma/__init__.py`:** Application factory and configuration.
- **`lemma/core/credential_service.py`:** Credential issuance and verification logic.
- **`lemma/auth/security.py`:** Authentication and security features.
- **`lemma/routes/`:** Modular route handlers.
- **`lemma/utils/`:** Utility functions.
- **`lemma/models/`:** Data models.
- **`tests/`:** Comprehensive test suite.

### Templates
- **`templates/index.html`:** Landing page.
- **`templates/verify.html`:** Credential verification and storage page.
- **`templates/protected.html`:** Content requiring human verification.
- **`templates/admin_login.html`:** Secure admin login.
- **`templates/admin.html`:** Admin dashboard for issuing credentials.

### Storage System
- **`.lemma_enterprise/`:** (Created automatically) Contains cryptographic keys and credential registry:
  - `keys.json`: Ed25519 keys
  - `registry.json`: Issued credentials
  - `users.json`: User IDs (no personal data)

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
1. **Link Access:** User opens the verification link.
2. **Credential Retrieval:** System provides the credential.
3. **Local Storage:** Credential is stored in browser local storage.
4. **Presentation Creation:** System creates a verifiable presentation.

### Cross-Page Verification Flow
1. **Protected Access:** User attempts to access protected content.
2. **Credential Check:** System checks for a stored credential.
3. **Presentation Verification:** System verifies the presentation.
4. **Access Grant:** User is granted access to protected content.

---

## Installation & Deployment

### Prerequisites
- Python 3.9+
- pip
- Docker (optional)

### Local Development
```bash
# Clone the repository
git clone <repository-url>
cd lemma-enterprise-package

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

### Azure Deployment
1. **Create an Azure Web App:**
   ```bash
   az webapp create --resource-group YourResourceGroup --plan YourAppServicePlan --name LemmaHumanVerification --runtime "PYTHON:3.9"
   ```
2. **Set Environment Variables:**
   ```bash
   az webapp config appsettings set --resource-group YourResourceGroup --name LemmaHumanVerification --settings LEMMA_ADMIN_USER="your_admin_username" LEMMA_ADMIN_PASS="your_secure_password" LEMMA_SECRET_KEY="your_random_secret"
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
- **GET /api/credentials/{user_id}:** Get a user's credential (requires API key)
- **GET /api/credentials:** List all credentials (requires API key and admin authentication)

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

---

## Customization

- Modify the HTML templates to match your branding.
- Adjust the credential expiration in the credential service or `app.py` (default: 1 year).
- Add additional protected pages by following the pattern in `protected.html`.
- Customize security settings in `lemma/__init__.py`.

---

## Credential Storage and Cross-Device Support

Lemma uses a combination of approaches to help users manage their Verifiable Credentials across devices.

### Current Implementation

The system currently supports:

- **Browser LocalStorage**: Credentials are automatically stored in the browser's localStorage for seamless use on a single device.
- **Downloadable JSON Backup**: Users can download their credential as a JSON file which can be backed up or transferred to other devices.
- **Import Functionality**: Users can import previously downloaded JSON credentials on any device, enabling cross-device credential use.

This implementation ensures users can:
1. Use their credential automatically on the device where they initially verified
2. Backup their credential to prevent data loss
3. Transfer their credential to other devices (desktop or mobile) manually

### Future Plans

We're planning to integrate with digital wallet solutions for improved user experience:

- **Apple Wallet Integration**: Future versions will support adding Lemma credentials to Apple Wallet as passes.
- **Google Wallet Integration**: Support for Google Wallet will be added as Google expands their digital ID capabilities.
- **W3C Standards Compliance**: All wallet integrations will maintain compliance with W3C Verifiable Credentials standards.

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
