# Lemma Enterprise: Human Verification System

A secure, modular, enterprise-grade implementation for verifying humans with minimal data collection and strong cryptographic standards.

## Overview

Lemma Enterprise provides a complete solution for trusted admin onboarding of verified humans to the Lemma network. The system focuses exclusively on:

1. **Minimal Data Collection**: Only verifies that a user is human - no additional personal information
2. **Strong Encryption**: Uses Ed25519 signatures with enhanced security features
3. **Cross-Page Verification**: Demonstrates how verification works across different pages
4. **W3C Standards**: Issues standard Verifiable Credentials and Presentations

## Key Features

- **Modular Architecture**: Clean separation of concerns for maintainability
- **Enhanced Security**: Password hashing, CSRF protection, secure cookies, and encrypted storage
- **Comprehensive Testing**: Full test coverage for all critical paths
- **Improved UX**: Auto-redirects, QR codes, and detailed error feedback
- **Docker Support**: Easy deployment with Docker and docker-compose
- **Rate Limiting**: Protection against API abuse
- **Audit Logging**: Comprehensive logging for security events

## Admin Onboarding Flow

The admin onboarding flow allows trusted admins to mint credentials for users they know are human, bypassing automated KYC:

1. **Admin Authentication**: Secure login at `/admin/login` with password hashing and CSRF protection
2. **Credential Issuance**: Admin enters a user ID at `/admin/issue` to issue a credential for a trusted human
3. **Verification Link**: System generates a shareable verification link and QR code
4. **User Verification**: User receives the link to `/verify?user_id={user_id}` to store their credential
5. **Local Storage**: Credential is stored in the user's browser, maintaining privacy
6. **Cross-Page Access**: User can access protected content at `/protected` using their credential

## Architecture

### Core Components

- **`app.py`**: Main application entry point
- **`lemma/__init__.py`**: Application factory and configuration
- **`lemma/core/credential_service.py`**: Core credential issuance and verification
- **`lemma/auth/security.py`**: Authentication and security features
- **`lemma/routes/`**: Modular route handlers
- **`lemma/utils/`**: Utility functions
- **`lemma/models/`**: Data models
- **`tests/`**: Comprehensive test suite

## Installation

### Prerequisites

- Python 3.9+
- pip
- Docker (optional, for containerized deployment)

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

## Testing

The system includes comprehensive tests for all critical paths:

```bash
# Run all tests with coverage report
python run_tests.py

# Or use pytest directly
pytest -v --cov=lemma
```

## API Documentation

### Authentication

All API endpoints that modify data require an API key:

```
X-API-Key: your_api_key_here
```

### Endpoints

- **GET /api/health**: Health check endpoint
- **POST /api/issue-credential**: Issue a credential (requires API key)
- **POST /api/verify-credential**: Verify a credential
- **GET /api/generate-challenge**: Generate a challenge for presentation verification
- **POST /api/verify-presentation**: Verify a presentation
- **GET /api/credentials/{user_id}**: Get a user's credential (requires API key)
- **GET /api/credentials**: List all credentials (requires API key and admin authentication)

## Security Considerations

1. **Admin Credentials**: Set strong admin credentials via environment variables
2. **Session Secret**: Use a strong random value for LEMMA_SECRET_KEY
3. **API Key**: Set a strong API key for external integrations
4. **HTTPS**: Always use HTTPS in production for secure credential transmission
5. **Rate Limiting**: API endpoints are protected against abuse
6. **Password Hashing**: Admin passwords are securely hashed
7. **CSRF Protection**: All forms are protected against CSRF attacks
8. **Encrypted Storage**: Sensitive data is encrypted at rest

## Customization

- Modify the HTML templates to match your branding
- Adjust the credential expiration in the credential service
- Add additional protected pages by following the pattern in `protected.html`
- Customize the security settings in `lemma/__init__.py`

## License

This project is licensed under the MIT License - see the LICENSE file for details.
