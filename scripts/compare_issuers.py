#!/usr/bin/env python3
"""Compare all issuers - verify KMS-backed storage"""

from api.issuer_management import get_issuer_manager
from api.database import SessionLocal, Site
from api.kms_manager import is_kms_available
import os

manager = get_issuer_manager()

print('='*60)
print('KMS-BACKED ISSUER STATUS')
print('='*60)

print(f'\nKMS Available: {is_kms_available()}')

db = SessionLocal()

# All expected KMS-backed sites
sites_to_check = [
    ('federated_network', 'Federated (PoH)', lambda: manager.get_federated_issuer()),
    ('lemma.id', 'IAM (lemma.id)', lambda: manager.get_iam_issuer('lemma.id')),
    ('lemma_platform', 'IAM (lemma_platform)', lambda: manager.get_iam_issuer('lemma_platform')),
    ('multi_lemma_qr_authentication', 'Multi-Lemma (QR)', lambda: manager.get_multi_lemma_issuer('qr_authentication')),
]

all_kms_backed = True

for site_id, name, get_issuer in sites_to_check:
    print(f'\n{name}:')
    print(f'  Site ID: {site_id}')
    
    # Check database
    site = db.query(Site).filter(Site.site_id == site_id).first()
    if site:
        has_kms = bool(site.kms_encrypted_signing_key)
        print(f'  In Database: Yes')
        print(f'  KMS-Backed: {"Yes" if has_kms else "NO"}')
        if has_kms:
            print(f'  DB Public Key: {site.public_key_hex[:30]}...')
            print(f'  Issuer DID: {site.issuer_did[:50]}...')
        else:
            all_kms_backed = False
    else:
        print(f'  In Database: NO')
        all_kms_backed = False
    
    # Try to load issuer
    try:
        issuer = get_issuer()
        print(f'  Loaded Public Key: {issuer.get_public_key_hex()[:30]}...')
        if site and site.public_key_hex:
            match = site.public_key_hex == issuer.get_public_key_hex()
            print(f'  Keys Match DB: {match}')
            if not match:
                all_kms_backed = False
    except Exception as e:
        print(f'  Load Error: {e}')
        all_kms_backed = False

db.close()

print('\n' + '='*60)
if all_kms_backed:
    print('ALL ISSUERS ARE KMS-BACKED')
else:
    print('WARNING: Some issuers are NOT KMS-backed!')
    print('Run: python scripts/full_kms_migration.py')
print('='*60)

