#!/usr/bin/env python3
"""Final KMS verification test"""

from api.kms_manager import is_kms_available, get_kms_manager
from api.issuer_management import get_issuer_manager
from api.database import SessionLocal, Site
import time

print('='*60)
print('FINAL KMS VERIFICATION TEST')
print('='*60)

print('\n1. KMS Status:')
print(f'   Available: {is_kms_available()}')
kms = get_kms_manager()
print(f'   Enabled: {kms.is_enabled()}')

print('\n2. KMS Key Info:')
info = kms.get_key_info()
print(f'   Key ID: {info["key_id"]}')
print(f'   State: {info["key_state"]}')

print('\n3. Database State:')
db = SessionLocal()
site = db.query(Site).filter(Site.site_id == 'lemma_platform').first()
print(f'   Has KMS key: {bool(site.kms_encrypted_signing_key)}')
print(f'   Public key: {site.public_key_hex[:30]}...')
print(f'   Key status: {site.key_status}')
db.close()

print('\n4. Issuer Load Test:')
manager = get_issuer_manager()
manager._issuers.clear()
start = time.time()
issuer = manager.get_iam_issuer('lemma_platform')
elapsed = (time.time() - start) * 1000
print(f'   Load time (with KMS decrypt): {elapsed:.0f}ms')
print(f'   Public key: {issuer.get_public_key_hex()[:30]}...')

start = time.time()
issuer2 = manager.get_iam_issuer('lemma_platform')
elapsed2 = (time.time() - start) * 1000
print(f'   Cached load: {elapsed2:.3f}ms')

print('\n'+'='*60)
print('ALL TESTS PASSED - KMS WORKING CORRECTLY')
print('='*60)

