# Pre-Deployment Security Checklist

## Sensitive Information Check

Before deploying the Lemma Enterprise system to a live environment, ensure the following security measures are in place:

### 1. Environment Variables

✅ Ensure all sensitive information is stored in environment variables and not hardcoded:
- `LEMMA_ADMIN_USER`
- `LEMMA_ADMIN_PASS`
- `LEMMA_SECRET_KEY`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_PHONE_NUMBER`

### 2. Git Repository Cleanup

✅ Add the following files to `.gitignore` if not already present:
- `.env` files
- `*.pem` (private keys)
- `.lemma_enterprise/` (contains cryptographic keys and credential registry)
- `lemma_test_credential_*.json` (test credentials)

✅ Remove any accidentally committed sensitive files:
```bash
git rm --cached .env
git rm --cached .lemma_enterprise/*
git rm --cached lemma_test_credential_*.json
```

### 3. Test Files

✅ Review test files for hardcoded credentials:
- `test_env.py`
- `test_sms.py`
- `test_sms_configured.py`
- `test_full_system.py`
- `test_invite_workflow.py`

### 4. Default Credentials

✅ Change default credentials:
- Update default admin password from `password` to a strong, unique password
- Generate a secure random secret key for `LEMMA_SECRET_KEY`

### 5. Deployment Files

✅ Ensure deployment scripts don't contain hardcoded credentials:
- `prepare_deployment.py`
- `deploy_to_azure.py`

### 6. Credential Storage

✅ Verify cryptographic keys and credentials are stored securely:
- Check that `.lemma_enterprise/keys.json` is not committed to the repository
- Ensure credential registry is properly secured

### 7. Azure-Specific Security

✅ For Azure deployment:
- Use Azure Key Vault for storing secrets in production
- Enable HTTPS for all endpoints
- Set up proper access controls and network security groups

## Pre-Deployment Actions

1. Run the following command to check for any remaining hardcoded secrets:
```bash
grep -r "password\|secret\|key\|token\|sid\|auth" --include="*.py" --include="*.json" .
```

2. Create a fresh `.env` file for production with strong credentials:
```
LEMMA_ADMIN_USER=admin
LEMMA_ADMIN_PASS=[strong-password]
LEMMA_SECRET_KEY=[random-32-character-string]
TWILIO_ACCOUNT_SID=[your-twilio-sid]
TWILIO_AUTH_TOKEN=[your-twilio-token]
TWILIO_PHONE_NUMBER=[your-twilio-number]
```

3. Test the application with the production environment variables:
```bash
python test_full_system.py
```

4. Create the deployment package:
```bash
python prepare_deployment.py
```

5. Deploy to Azure:
```bash
python deploy_to_azure.py
```

## Post-Deployment Verification

After deployment, verify:
1. Admin login works with the new credentials
2. SMS invitations can be sent successfully
3. Users can verify their credentials
4. Protected resources are accessible only to verified humans
