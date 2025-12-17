#!/usr/bin/env python3
"""Compare all issuers to understand which keys are being used where"""

from api.issuer_management import get_issuer_manager
import os

manager = get_issuer_manager()

print('='*60)
print('ISSUER COMPARISON')
print('='*60)

# Check environment
print('\nEnvironment Variables:')
print(f'  LEMMA_FEDERATED_ISSUER_SEED: {"SET" if os.environ.get("LEMMA_FEDERATED_ISSUER_SEED") else "NOT SET"}')
print(f'  LEMMA_ISSUER_SEED: {"SET" if os.environ.get("LEMMA_ISSUER_SEED") else "NOT SET"}')
print(f'  LEMMA_KMS_KEY_ID: {"SET" if os.environ.get("LEMMA_KMS_KEY_ID") else "NOT SET"}')

# Federated issuer (for PoH)
fed = manager.get_federated_issuer()
print(f'\n1. FEDERATED ISSUER (PoH lemmas):')
print(f'   DID: {fed.get_did()[:50]}...')
print(f'   Public Key: {fed.get_public_key_hex()[:30]}...')
print(f'   Source: LEMMA_FEDERATED_ISSUER_SEED or LEMMA_API_SECRET derived')
print(f'   Storage: MEMORY (derived from env var)')

# IAM issuer for lemma.id
iam_lemma_id = manager.get_iam_issuer('lemma.id')
print(f'\n2. IAM ISSUER (lemma.id site):')
print(f'   DID: {iam_lemma_id.get_did()[:50]}...')
print(f'   Public Key: {iam_lemma_id.get_public_key_hex()[:30]}...')

# Check if this has KMS storage
from api.database import SessionLocal, Site
db = SessionLocal()
site_lemma_id = db.query(Site).filter(Site.site_id == 'lemma.id').first()
if site_lemma_id:
    print(f'   Has KMS key: {bool(site_lemma_id.kms_encrypted_signing_key)}')
    if site_lemma_id.kms_encrypted_signing_key:
        print(f'   DB Public Key: {site_lemma_id.public_key_hex[:30]}...')
else:
    print(f'   Site not in database')

# IAM issuer for lemma_platform (KMS-backed)
iam_platform = manager.get_iam_issuer('lemma_platform')
print(f'\n3. IAM ISSUER (lemma_platform - KMS):')
print(f'   DID: {iam_platform.get_did()[:50]}...')
print(f'   Public Key: {iam_platform.get_public_key_hex()[:30]}...')

site_platform = db.query(Site).filter(Site.site_id == 'lemma_platform').first()
if site_platform:
    print(f'   Has KMS key: {bool(site_platform.kms_encrypted_signing_key)}')
    print(f'   DB Public Key: {site_platform.public_key_hex[:30]}...')
    print(f'   Keys Match: {site_platform.public_key_hex == iam_platform.get_public_key_hex()}')

# Multi-lemma issuer
multi = manager.get_multi_lemma_issuer('qr_authentication')
print(f'\n4. MULTI-LEMMA ISSUER (QR auth):')
print(f'   DID: {multi.get_did()[:50]}...')
print(f'   Public Key: {multi.get_public_key_hex()[:30]}...')

db.close()

print('\n'+'='*60)
print('SUMMARY')
print('='*60)
print('\nCredentials signed with:')
print('  - Federated Issuer: PoH lemmas, network identity')
print('  - IAM Issuer (lemma.id): Your login credentials')
print('  - IAM Issuer (lemma_platform): Site-specific credentials')
print('\nIf old credentials still work, they are using an issuer')
print('that did NOT change (likely federated or lemma.id)')

