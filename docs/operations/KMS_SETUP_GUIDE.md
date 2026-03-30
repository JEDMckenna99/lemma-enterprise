# 🔐 AWS KMS Setup Guide for Lemma IAM

## Overview

This guide walks you through setting up AWS Key Management Service (KMS) to provide HSM-backed encryption for site-specific Ed25519 signing keys in the Lemma IAM system.

**Security Level:** FIPS 140-2 Level 2/3 compliant key storage

---

## 📋 Prerequisites

1. AWS Account with billing enabled
2. AWS CLI installed and configured
3. IAM user with KMS permissions
4. Heroku CLI (for deploying to production)

---

## 🚀 Step 1: Create AWS KMS Customer Master Key (CMK)

### Using AWS Console

1. Go to **AWS KMS Console**: https://console.aws.amazon.com/kms
2. Click **Create key**
3. Configure key:
   - **Key type:** Symmetric
   - **Key usage:** Encrypt and decrypt
   - **Advanced options:** Keep defaults (KMS generates key material)
4. Add labels:
   - **Alias:** `alias/lemma-iam-signing-keys`
   - **Description:** `Lemma IAM Site-Specific Signing Key Encryption`
5. Define key administrative permissions:
   - Select your IAM user/role
6. Define key usage permissions:
   - Select the IAM user/role that will be used by your application
7. Review and **Finish**
8. **Copy the Key ID** (looks like: `arn:aws:kms:us-east-1:123456789012:key/abcd1234-...`)

### Using AWS CLI

```bash
# Create the KMS key
aws kms create-key \
  --description "Lemma IAM Site-Specific Signing Key Encryption" \
  --key-usage ENCRYPT_DECRYPT \
  --origin AWS_KMS

# Output will include KeyMetadata with KeyId - copy this!

# Create an alias for easier reference
aws kms create-alias \
  --alias-name alias/lemma-iam-signing-keys \
  --target-key-id <KEY_ID_FROM_ABOVE>

# Enable automatic key rotation (rotates every year)
aws kms enable-key-rotation \
  --key-id <KEY_ID_FROM_ABOVE>

# Verify rotation is enabled
aws kms get-key-rotation-status \
  --key-id <KEY_ID_FROM_ABOVE>
```

---

## 🔑 Step 2: Create IAM User for Application Access

### Create IAM User

```bash
# Create IAM user
aws iam create-user \
  --user-name lemma-iam-kms-user

# Create access key
aws iam create-access-key \
  --user-name lemma-iam-kms-user

# IMPORTANT: Save the AccessKeyId and SecretAccessKey from the output!
```

### Create IAM Policy

Create a file named `lemma-kms-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowKMSEncryptDecrypt",
      "Effect": "Allow",
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:DescribeKey",
        "kms:GetKeyRotationStatus"
      ],
      "Resource": "arn:aws:kms:us-east-1:YOUR_ACCOUNT_ID:key/YOUR_KEY_ID"
    },
    {
      "Sid": "AllowKMSListKeys",
      "Effect": "Allow",
      "Action": [
        "kms:ListKeys",
        "kms:ListAliases"
      ],
      "Resource": "*"
    }
  ]
}
```

**Replace:**
- `YOUR_ACCOUNT_ID` with your AWS account ID
- `YOUR_KEY_ID` with the KMS key ID from Step 1

Apply the policy:

```bash
# Create the policy
aws iam create-policy \
  --policy-name LemmaKMSPolicy \
  --policy-document file://lemma-kms-policy.json

# Attach policy to user
aws iam attach-user-policy \
  --user-name lemma-iam-kms-user \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/LemmaKMSPolicy
```

---

## 🌐 Step 3: Configure Heroku Environment Variables

```bash
# Set AWS credentials
heroku config:set AWS_ACCESS_KEY_ID=AKIA...
heroku config:set AWS_SECRET_ACCESS_KEY=...
heroku config:set AWS_REGION=us-east-1

# Set KMS key ID (use the full ARN or just the key ID)
heroku config:set LEMMA_KMS_KEY_ID=arn:aws:kms:us-east-1:123456789012:key/abcd1234-...

# Verify configuration
heroku config:get AWS_ACCESS_KEY_ID
heroku config:get LEMMA_KMS_KEY_ID
```

---

## 🧪 Step 4: Test KMS Integration

### Local Testing

Create a test script `test_kms_local.py`:

```python
import os
from api.kms_manager import get_kms_manager, is_kms_available

# Set environment variables (use your actual values)
os.environ['AWS_ACCESS_KEY_ID'] = 'AKIA...'
os.environ['AWS_SECRET_ACCESS_KEY'] = '...'
os.environ['AWS_REGION'] = 'us-east-1'
os.environ['LEMMA_KMS_KEY_ID'] = 'arn:aws:kms:us-east-1:...'

# Test KMS availability
print(f"KMS Available: {is_kms_available()}")

# Get KMS manager
kms = get_kms_manager()

# Test encryption/decryption
test_key = os.urandom(32)  # 32-byte Ed25519 private key
site_id = "test_site_123"

print(f"\n🔐 Testing encryption for site: {site_id}")
print(f"Original key (first 8 bytes): {test_key[:8].hex()}")

# Encrypt
encrypted_key, kms_key_id = kms.encrypt_signing_key(test_key, site_id)
print(f"✅ Encrypted key (length: {len(encrypted_key)} chars)")
print(f"KMS Key ID: {kms_key_id[:50]}...")

# Decrypt
decrypted_key = kms.decrypt_signing_key(encrypted_key, site_id)
print(f"✅ Decrypted key (first 8 bytes): {decrypted_key[:8].hex()}")

# Verify
if test_key == decrypted_key:
    print("✅ SUCCESS: Encryption/Decryption working correctly!")
else:
    print("❌ FAILURE: Keys don't match!")

# Get key info
key_info = kms.get_key_info()
if key_info:
    print(f"\n📊 KMS Key Info:")
    print(f"  Key ID: {key_info['key_id']}")
    print(f"  State: {key_info['key_state']}")
    print(f"  Enabled: {key_info['enabled']}")
```

Run the test:

```bash
python test_kms_local.py
```

Expected output:
```
KMS Available: True

🔐 Testing encryption for site: test_site_123
Original key (first 8 bytes): a1b2c3d4e5f67890
✅ Encrypted key (length: 256 chars)
KMS Key ID: arn:aws:kms:us-east-1:123456789012:key/...
✅ Decrypted key (first 8 bytes): a1b2c3d4e5f67890
✅ SUCCESS: Encryption/Decryption working correctly!

📊 KMS Key Info:
  Key ID: abcd1234-5678-...
  State: Enabled
  Enabled: True
```

### Production Testing (on Heroku)

```bash
# SSH into Heroku dyno
heroku run bash

# Run Python console
python

>>> from api.kms_manager import is_kms_available, get_kms_manager
>>> print(f"KMS Available: {is_kms_available()}")
KMS Available: True

>>> kms = get_kms_manager()
>>> info = kms.get_key_info()
>>> print(info['key_state'])
Enabled

>>> exit()
```

---

## 🔄 Step 5: Database Migration (Add KMS Columns)

The KMS columns have been added to the `Site` model. You need to apply the migration:

### Create Migration

If using Alembic:

```bash
# Generate migration
alembic revision --autogenerate -m "Add KMS encryption columns to sites table"

# Review the migration file in alembic/versions/

# Apply migration
alembic upgrade head
```

### Manual SQL (if not using Alembic)

```sql
-- Connect to your PostgreSQL database
ALTER TABLE sites 
ADD COLUMN kms_encrypted_signing_key TEXT,
ADD COLUMN kms_key_id VARCHAR(255),
ADD COLUMN public_key_hex VARCHAR(64),
ADD COLUMN issuer_did VARCHAR(255),
ADD COLUMN key_created_at TIMESTAMP,
ADD COLUMN key_last_used TIMESTAMP,
ADD COLUMN key_rotation_due TIMESTAMP,
ADD COLUMN key_status VARCHAR(50) DEFAULT 'active';

-- Create index for faster lookups
CREATE INDEX idx_sites_issuer_did ON sites(issuer_did);
CREATE INDEX idx_sites_key_status ON sites(key_status);
```

---

## 📊 Step 6: Verify Production Deployment

After deploying to Heroku:

```bash
# Check logs for KMS initialization
heroku logs --tail | grep KMS

# Expected output:
# ✅ KMS manager initialized with key: arn:aws:kms:us-east-1...
# 🔐 Region: us-east-1
```

When a site is registered:

```bash
heroku logs --tail | grep "issuer for"

# Expected output:
# ✅ Created NEW KMS-backed issuer for site_abc123
# 🔐 Key encrypted with KMS: arn:aws:kms:...
```

When a credential is issued:

```bash
heroku logs --tail | grep "Loaded KMS"

# Expected output:
# ✅ Loaded KMS-backed issuer for site_abc123: did:lemma:a1b2c3...
```

---

## 💰 Cost Estimation

| Component | Cost |
|-----------|------|
| KMS Customer Master Key | $1.00/month |
| KMS API Requests (10,000/month) | $0.03 |
| **Total** | **~$1.03/month** |

**Scalability:**
- Up to 100 sites: ~$1/month
- Up to 1,000 sites: ~$1-2/month (depends on signing frequency)
- Up to 10,000 sites: ~$5-10/month

---

## 🔒 Security Best Practices

### 1. Principle of Least Privilege

Only grant `kms:Encrypt` and `kms:Decrypt` permissions - never `kms:DeleteKey` or `kms:ScheduleKeyDeletion` to application users.

### 2. Encryption Context

The implementation uses encryption context for additional security:

```python
encryption_context = {
    'site_id': site_id,
    'key_type': 'ed25519_signing_key',
    'purpose': 'lemma_iam_credential_signing',
    'version': '1.0'
}
```

This prevents:
- Using encrypted keys for wrong sites
- Replay attacks
- Key misuse

### 3. Key Rotation

```bash
# Check rotation status
aws kms get-key-rotation-status --key-id alias/lemma-iam-signing-keys

# Rotation happens automatically every 365 days
# Old key versions remain available to decrypt existing ciphertexts
```

### 4. Audit Logging

All KMS operations are logged to AWS CloudTrail:

```bash
# View KMS events
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceType,AttributeValue=AWS::KMS::Key \
  --max-results 50
```

### 5. Key Backup

KMS keys are automatically backed up by AWS. To export encrypted keys:

```sql
-- Backup encrypted keys from database
SELECT 
  site_id, 
  kms_encrypted_signing_key, 
  kms_key_id, 
  issuer_did,
  key_created_at
FROM sites
WHERE kms_encrypted_signing_key IS NOT NULL
ORDER BY key_created_at DESC;
```

---

## 🚨 Troubleshooting

### "KMS is not enabled"

**Problem:** `is_kms_available()` returns `False`

**Solutions:**
1. Check environment variables are set:
   ```bash
   heroku config | grep AWS
   heroku config | grep LEMMA_KMS
   ```
2. Verify AWS credentials are valid:
   ```bash
   aws sts get-caller-identity
   ```
3. Check application logs:
   ```bash
   heroku logs --tail | grep KMS
   ```

### "Access Denied" when encrypting/decrypting

**Problem:** `AccessDeniedException` from AWS

**Solutions:**
1. Verify IAM policy is attached:
   ```bash
   aws iam list-attached-user-policies --user-name lemma-iam-kms-user
   ```
2. Check KMS key policy allows your IAM user
3. Verify key ID is correct:
   ```bash
   aws kms describe-key --key-id $LEMMA_KMS_KEY_ID
   ```

### "InvalidCiphertextException"

**Problem:** Decryption fails with invalid ciphertext error

**Possible causes:**
- Encryption context mismatch (site_id changed)
- Corrupted ciphertext in database
- Wrong KMS key used for decryption

**Solution:**
- Check encryption context matches between encrypt/decrypt
- Regenerate key for affected site
- Verify ciphertext wasn't truncated in database

### Performance Issues

**Problem:** Slow credential issuance

**Solution:**
- KMS calls are cached in memory (only decrypts once per dyno)
- Consider increasing dyno size for more memory
- Monitor KMS request latency in CloudWatch

---

## 📈 Monitoring

### CloudWatch Metrics

Monitor these KMS metrics:

1. **NumberOfOperations** - Track encryption/decryption calls
2. **SecondsUntilKeyMaterialExpiration** - Key rotation alerts
3. **UserErrors** - Failed operations

### Application Metrics

Log these events:

```python
logger.info(f"🔐 KMS encrypt: site={site_id}, time={elapsed_ms}ms")
logger.info(f"🔓 KMS decrypt: site={site_id}, time={elapsed_ms}ms, cached={from_cache}")
logger.error(f"❌ KMS error: site={site_id}, error={error_code}")
```

---

## 🎯 Next Steps

1. ✅ Set up KMS (this guide)
2. Deploy to Heroku
3. Test site registration with KMS-backed keys
4. Monitor KMS usage and costs
5. Set up CloudWatch alarms for key errors
6. Plan for key rotation (automatic, but monitor)

---

## 📚 Additional Resources

- [AWS KMS Developer Guide](https://docs.aws.amazon.com/kms/latest/developerguide/)
- [AWS KMS Best Practices](https://docs.aws.amazon.com/kms/latest/developerguide/best-practices.html)
- [FIPS 140-2 Compliance](https://aws.amazon.com/compliance/fips/)
- [CloudTrail Logging for KMS](https://docs.aws.amazon.com/kms/latest/developerguide/logging-using-cloudtrail.html)

