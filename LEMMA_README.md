# Lemma Enterprise: Human Verification System

A streamlined, enterprise-grade implementation for verifying humans with minimal data collection and strong cryptographic standards.

## Overview

This package provides a complete solution for trusted admin onboarding of verified humans to the Lemma network. It focuses exclusively on:

1. **Minimal Data Collection**: Only verifies that a user is human - no additional personal information
2. **Strong Encryption**: Uses Ed25519 signatures for enterprise-grade security
3. **Cross-Page Verification**: Demonstrates how verification works across different pages
4. **W3C Standards**: Issues standard Verifiable Credentials and Presentations

## Components

### Core Files

- **`app.py`**: The main Flask application with all backend logic
- **`requirements.txt`**: Dependencies for deployment
- **`.lemma_enterprise/`**: Directory created automatically for key and credential storage

### Templates

- **`templates/index.html`**: Landing page
- **`templates/verify.html`**: Credential verification and storage page
- **`templates/protected.html`**: Content that requires human verification
- **`templates/admin_login.html`**: Secure admin login
- **`templates/admin.html`**: Admin dashboard for issuing credentials

## Admin Onboarding Flow

The admin onboarding flow allows trusted admins to mint credentials for users they know are human, bypassing automated KYC:

1. **Admin Authentication**: Secure login at `/admin/login`
2. **Credential Issuance**: Admin enters a user ID at `/admin` to issue a credential
3. **User Verification**: User receives a link to `/verify?user={user_id}` to store their credential
4. **Local Storage**: Credential is stored in the user's browser, maintaining privacy
5. **Cross-Page Access**: User can access protected content at `/protected` using their credential

## Deployment

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

### Azure Deployment

1. **Create an Azure Web App**:
   ```bash
   az webapp create --resource-group YourResourceGroup --plan YourAppServicePlan --name LemmaHumanVerification --runtime "PYTHON:3.9"
   ```

2. **Set Environment Variables**:
   ```bash
   az webapp config appsettings set --resource-group YourResourceGroup --name LemmaHumanVerification --settings LEMMA_ADMIN_USER="your_admin_username" LEMMA_ADMIN_PASS="your_secure_password" LEMMA_SECRET_KEY="your_random_secret"
   ```

3. **Deploy the Code**:
   ```bash
   az webapp deployment source config-zip --resource-group YourResourceGroup --name LemmaHumanVerification --src lemma-enterprise.zip
   ```

## Security Considerations

1. **Admin Credentials**: Set strong admin credentials via environment variables
2. **Session Secret**: Use a strong random value for LEMMA_SECRET_KEY
3. **Key Protection**: The `.lemma_enterprise` directory contains cryptographic keys - keep it secure
4. **HTTPS**: Always use HTTPS in production for secure credential transmission

## Usage

### Admin Interface

1. Access `/admin/login` with your admin credentials
2. Issue credentials to trusted humans you've personally verified
3. Share the verification link with the user

### User Experience

1. User receives a verification link
2. They open it on their device and store the credential
3. The credential is saved in their browser's local storage
4. They can now access protected content across the site

## Customization

- Modify the HTML templates to match your branding
- Adjust the credential expiration in `app.py` (default: 1 year)
- Add additional protected pages by following the pattern in `protected.html`
