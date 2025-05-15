# Testing Guide for Lemma Human Verification System

This guide provides instructions for testing the Lemma human verification system, with a focus on verifying the DID implementation and credential verification flow.

## Prerequisites

- Python 3.9+
- pip
- A web browser
- Access to a Lemma Enterprise deployment (local or Heroku)

## Setup

1. Clone the repository and install the required packages:

```bash
git clone <repository-url>
cd lemma-enterprise
pip install -r requirements.txt
```

2. (Optional) Install Selenium for browser testing:

```bash
pip install selenium webdriver-manager
```

## 1. Basic API Testing

### a. Test the Heroku Deployment

Run the `test_heroku_deployment.py` script to verify that the main API functionality is working:

```bash
python test_heroku_deployment.py https://your-lemma-app.herokuapp.com
```

This script tests:
- API health
- Credential issuance
- Credential retrieval
- Credential verification
- Presentation creation and verification

### b. Test DID Resolution

Run the `heroku_did_resolution_test.py` script to test DID resolution:

```bash
python heroku_did_resolution_test.py https://your-lemma-app.herokuapp.com
```

This script will:
- Fetch a credential from the system to extract the issuer DID
- Resolve the DID to get the DID document
- Analyze the DID document structure

You can also test with a specific DID:

```bash
python heroku_did_resolution_test.py https://your-lemma-app.herokuapp.com did:lemma:test123
```

## 2. DID Functionality Testing

Run the `test_did_functionality.py` script for comprehensive DID testing:

```bash
python test_did_functionality.py https://your-lemma-app.herokuapp.com
```

This script tests:
- DID resolution
- DID verification
- DID format validation
- Cross-page verification with DIDs

## 3. Browser Storage Testing

Run the browser storage test to ensure credentials are properly stored and retrieved in the browser:

```bash
python browser_storage_test.py --url https://your-lemma-app.herokuapp.com
```

For visible browser testing (non-headless):

```bash
python browser_storage_test.py --url https://your-lemma-app.herokuapp.com --visible
```

To test with a specific user:

```bash
python browser_storage_test.py --url https://your-lemma-app.herokuapp.com --user test-user-123
```

## 4. Running Standard Tests

Run the standard test suite:

```bash
python run_tests.py
```

Or for more detailed tests with environment variables:

```bash
python run_test_with_env.py
```

## 5. Manual Testing

### Verification Flow

1. Navigate to your Lemma deployment's home page
2. Click "Verify Lemma"
3. Confirm that you receive a valid credential
4. Check if the credential contains proper DID values for issuer and subject

### Protected Content Access

1. After verification, try to access the protected page
2. Confirm that you can access the protected content using your credential
3. Open the protected page in a new browser or incognito window
4. Confirm that you cannot access the protected content without verification

### Admin Functionality

1. Log in to the admin interface with your admin credentials
2. Issue a credential to a test user
3. Check if the credential has the correct DID values
4. Verify the credential using the API

## Troubleshooting

### Environment Variables

Ensure these critical environment variables are set in your Heroku deployment:

- `ED25519_PRIVATE_KEY`: Base64-encoded private key
- `DID`: The DID of the issuer (e.g., did:lemma:your-service)
- `LEMMA_ADMIN_USER`: Admin username
- `LEMMA_ADMIN_PASS`: Admin password
- `LEMMA_SECRET_KEY`: Secret key for Flask sessions
- `LEMMA_API_KEY`: API key for protected endpoints

### Common Issues

1. **Invalid challenge error**: Check if the challenge generation and verification endpoints are working correctly.
2. **Missing credential**: Verify that the credential issuance process is completing successfully.
3. **DID resolution fails**: Ensure the DID method is supported and properly configured.
4. **Browser storage issues**: Check if localStorage is accessible and working in your browser. 