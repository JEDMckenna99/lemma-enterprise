#!/usr/bin/env python3
"""
Check trusted issuers and validate credential issuer trust
"""

from api.trusted_issuers import get_trusted_issuer_dids, is_trusted_issuer, clear_cache

print("=" * 60)
print("TRUSTED ISSUER REGISTRY")
print("=" * 60)

# Clear cache to get fresh data
clear_cache()

trusted = get_trusted_issuer_dids()

print(f"\nTotal trusted issuers: {len(trusted)}")
print("\nTrusted Issuer DIDs:")

for did in sorted(trusted):
    print(f"  - {did[:60]}...")

# Check some old DIDs that might be in credentials
print("\n" + "=" * 60)
print("OLD ISSUER CHECK")
print("=" * 60)

old_issuers = [
    # These are the old DIDs from before KMS migration
    "did:lemma:aba9b52a0af7966628d68f2890a899277b88f688",  # Old federated
    "did:lemma:143b960715ecaa24d02943fc0bd7b391af8f5e92",  # Old lemma.id
    "did:lemma:843982bf25189ae055c93bb381a6b3",            # Old lemma_platform
]

print("\nChecking if old issuers are still trusted:")
for did in old_issuers:
    is_trust = is_trusted_issuer(did)
    status = "TRUSTED" if is_trust else "NOT TRUSTED"
    print(f"  {did[:40]}... -> {status}")

print("\n" + "=" * 60)
print("CURRENT ISSUER STATUS")
print("=" * 60)

from api.database import SessionLocal, Site
db = SessionLocal()

sites = db.query(Site).filter(Site.kms_encrypted_signing_key != None).all()
for site in sites:
    print(f"\n{site.site_id}:")
    print(f"  DID: {site.issuer_did}")
    print(f"  Status: {site.key_status}")
    print(f"  Created: {site.key_created_at}")

db.close()

