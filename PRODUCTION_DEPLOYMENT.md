# Production Deployment Guide for LEMMA Enterprise

This guide walks through the steps to prepare the LEMMA Enterprise system for production deployment and pass all functional tests, particularly test flow 4 (cascade download and verification).

## Pre-deployment Checklist

1. Ensure the following files are in place:
   - `requirements.txt` - Contains all dependencies
   - `Procfile` - For Heroku deployment
   - `wsgi.py` - WSGI entry point
   - `env.production.template` - Template for production environment variables

2. Environment setup:
   - Copy `env.production.template` to `.env.production`
   - Fill in secure values for all credentials
   - Update storage paths if needed

## Preparing the System

Run the preparation script to set up the system:

```bash
python prepare_deployment.py --prod --test-flow-4
```

This script will:
1. Set up storage directories
2. Configure environment variables
3. Generate Ed25519 cryptographic keys
4. Build an initial cascade for testing
5. Run flow test 4 to verify system functionality

## Flow Test 4 (Cascade Download & Verification)

Flow test 4 verifies that:
1. The cascade endpoint is available and returns proper responses
2. The cascade bundle structure is correct
3. The cascade signature can be verified
4. The cascade bundle size is within acceptable limits
5. The system correctly rejects tampered signatures

For the test to pass, we've implemented:
1. A proper cascade endpoint in the application
2. A cascade builder that creates valid bundles with cryptographic signatures
3. A signature verification system for validating cascade integrity

## Deploying to Heroku

For Windows users, we've provided a PowerShell script:

```powershell
.\deploy_to_heroku.ps1
```

For manual deployment:

1. Log in to Heroku:
   ```bash
   heroku login
   ```

2. Create a new Heroku app or use an existing one:
   ```bash
   heroku create
   # or
   heroku git:remote -a your-app-name
   ```

3. Configure environment variables:
   ```bash
   heroku config:set FLASK_APP=app.py
   heroku config:set FLASK_ENV=production
   # Add all variables from .env.production
   ```

4. Add PostgreSQL and Redis add-ons:
   ```bash
   heroku addons:create heroku-postgresql:hobby-dev
   heroku addons:create heroku-redis:hobby-dev
   ```

5. Deploy the application:
   ```bash
   git push heroku main
   ```

## Daily Maintenance

To maintain the revocation system, set up a scheduled task to run:

```bash
python revoke_and_build.py --storage instance/data
```

This will:
1. Check for newly revoked credentials
2. Build a new cascade bundle
3. Publish the bundle for client access

## Troubleshooting

If test flow 4 fails, check:
1. Cascade file generation and storage paths
2. Cryptographic key generation and storage
3. Signature generation and verification
4. API endpoint availability and authorization

For OPRF service connection issues:
- The system will use a mock implementation in offline mode
- For production, ensure the OPRF service is properly configured 