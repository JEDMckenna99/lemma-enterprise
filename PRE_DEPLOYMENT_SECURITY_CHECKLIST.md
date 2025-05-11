# Pre-Deployment Security Checklist

## Sensitive Information Check

Before deploying the Lemma Enterprise system to a live environment, ensure the following security measures are in place:

### 1. Environment Variables

✅ Ensure all sensitive information is stored in environment variables and not hardcoded:
- `LEMMA_ADMIN_USER`
- `LEMMA_ADMIN_PASS`
- `LEMMA_SECRET_KEY`
- `LEMMA_API_KEY`
- `LEMMA_SESSION_TIMEOUT`
- `LEMMA_RATE_LIMIT`

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
LEMMA_ADMIN_USER=[your-admin-username]
LEMMA_ADMIN_PASS=[your-admin-password]
LEMMA_SECRET_KEY=[your-secure-secret-key]
LEMMA_API_KEY=[your-api-key]
LEMMA_SESSION_TIMEOUT=3600
LEMMA_RATE_LIMIT=100/hour
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

## Environment Variables

Ensure all of these environment variables are set with proper values:

- `LEMMA_ADMIN_USER` - Username for admin access (not "admin" in production)
- `LEMMA_ADMIN_PASS` - Strong password for admin (rotate periodically)
- `LEMMA_SECRET_KEY` - Strong random value (16+ bytes of entropy)
- `LEMMA_API_KEY` - Strong API key for external integrations
- `LEMMA_SESSION_TIMEOUT` - Session timeout in seconds (3600 or less)
- `LEMMA_RATE_LIMIT` - Rate limit for API endpoints (100/hour recommended)

## Production Configuration

Verify the deployment configurations in `.env.production`:

```
LEMMA_ADMIN_USER=[your-admin-username]
LEMMA_ADMIN_PASS=[your-admin-password]
LEMMA_SECRET_KEY=[your-secure-secret-key]
LEMMA_API_KEY=[your-api-key]
LEMMA_SESSION_TIMEOUT=3600
LEMMA_RATE_LIMIT=100/hour
```
