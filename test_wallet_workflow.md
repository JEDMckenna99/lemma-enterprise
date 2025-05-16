# Testing Lemma Wallet Storage and VC Workflow

This guide explains how to test the wallet storage functionality and verifiable credential (VC) workflow in your Lemma system.

## Prerequisites

- Running Lemma instance (local or Heroku)
- Modern web browser (Chrome, Firefox, etc.)
- Python 3.6+ with `requests` package (for API testing)
- Selenium WebDriver (for browser automation testing)

## 1. Manual Testing Workflow

### Step 1: Get a Verifiable Credential

1. Visit your Lemma instance (e.g., http://localhost:5000 or your Heroku URL)
2. Click "Verify Lemma" or navigate directly to `/verify`
3. Complete the verification process
4. After verification, your browser should have a credential stored in:
   - The Lemma wallet (using IndexedDB)
   - Check the wallet UI by clicking the wallet icon in the corner

### Step 2: Validate Wallet Storage

1. Open Developer Tools in your browser (F12 or Ctrl+Shift+I)
2. Go to the "Application" tab
3. Check IndexedDB:
   - Find the "lemma_wallet" database
   - Look in the "credentials" object store
   - Verify your credential is stored with proper wallet metadata
4. You can also use the wallet UI to view stored credentials:
   - Click on the wallet icon in the corner of the page
   - Your stored credentials should be listed

### Step 3: Test Protected Access

1. Navigate to `/protected` in your Lemma instance
2. You should automatically gain access to the protected content
3. If redirected to verification, the wallet credential wasn't recognized

### Step 4: Test Creating a Verifiable Presentation

Use the `/api/presentation` endpoint to create a VP from your VC:

```python
import requests
import json

# Get your credential from the API (you'll need to know your user ID)
user_id = "your-user-id"
response = requests.get(f"http://localhost:5000/api/credential-lookup/{user_id}")
credential = response.json()

# Create a presentation
response = requests.post(
    "http://localhost:5000/api/presentation",
    json={"credential": credential, "challenge": "test-challenge"}
)

if response.status_code == 200:
    presentation = response.json()
    print("Created presentation:", json.dumps(presentation, indent=2))
else:
    print("Failed:", response.text)
```

### Step 5: Verify the Presentation

Use the `/api/verify` endpoint to verify the presentation:

```python
# Verify the presentation
verify_response = requests.post(
    "http://localhost:5000/api/verify",
    json=presentation
)

if verify_response.status_code == 200:
    result = verify_response.json()
    print("Verification result:", json.dumps(result, indent=2))
    print("Valid:", result.get("valid"))
else:
    print("Verification failed:", verify_response.text)
```

## 2. Automated Testing

You can use the provided `test_wallet_flow.py` script to automate this workflow. The script:

1. Gets a credential for a test user
2. Tests storing it in the browser wallet
3. Tests protected access with the wallet credential
4. Creates a verifiable presentation
5. Verifies the presentation

Run it with:

```
python test_wallet_flow.py [your_lemma_url]
```

## 3. API Testing Only

For API-only testing without browser interaction, use the provided `test_wallet_api.py` script:

```
python test_wallet_api.py [your_lemma_url]
```

This script:
1. Gets a credential for a test user
2. Formats it for wallet storage
3. Tests the API endpoints related to the wallet
4. Creates a verifiable presentation
5. Verifies the presentation

## Troubleshooting

### Wallet Not Working
- Check browser console for errors related to the wallet initialization
- Verify JavaScript is enabled
- Make sure the lemma-wallet.js script is properly loaded
- Check if the wallet cookie is set (`lemma_wallet_enabled`)

### Credential Storage Issues
- Ensure the credential has the required fields (id, type, issuer, etc.)
- Check for IndexedDB permission issues in your browser
- Try using a different browser
- Some browsers in private/incognito mode may restrict IndexedDB storage

### Verification Failures
- Validate the credential's proof is properly formed
- Check issuer and subject DIDs are correct
- Verify the credential hasn't expired

## Conclusion

By following these steps, you can test the complete VC issuance, wallet storage, and verification workflow in your Lemma system. This validates that credentials are properly issued, stored in the wallet, and can be used to generate verifiable presentations for authentication. 