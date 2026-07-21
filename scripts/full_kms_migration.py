#!/usr/bin/env python3
"""
Full KMS Migration Script

Migrates ALL issuers to KMS-backed storage:
1. federated_network - For PoH lemmas
2. lemma.id - For IAM login credentials
3. multi_lemma_qr - For QR authentication
4. multi_lemma_delegation - For device delegation

WARNING: This will invalidate ALL existing credentials!
"""

import os
import sys
from datetime import datetime, timedelta

def migrate_all_to_kms():
    print("=" * 60)
    print("FULL KMS MIGRATION")
    print("=" * 60)
    print("\n⚠️  WARNING: This will invalidate ALL existing credentials!")
    print("    All users will need to re-authenticate.\n")
    
    from api.database import SessionLocal, Site
    from api.kms_manager import get_kms_manager, is_kms_available
    from lemma_crypto import PyMinimalIssuer
    
    if not is_kms_available():
        print("❌ ERROR: KMS is not available!")
        return False
    
    kms = get_kms_manager()
    db = SessionLocal()
    
    # Sites to migrate
    # NOTE: site_id must match the format used in issuer_management.py
    # get_multi_lemma_issuer uses: site_id = f'multi_lemma_{lemma_type}'
    sites_to_migrate = [
        {
            'site_id': 'federated_network',
            'name': 'Lemma Federated Identity Network',
            'description': 'PoH lemmas and federated identity',
            'domain': 'lemma.id',
            'admin_email': 'admin@lemma.id'
        },
        {
            'site_id': 'lemma.id',
            'name': 'Lemma.id IAM',
            'description': 'IAM login credentials for lemma.id',
            'domain': 'lemma.id',
            'admin_email': 'admin@lemma.id'
        },
        {
            'site_id': 'multi_lemma_qr_authentication',
            'name': 'Multi-Lemma QR Authentication',
            'description': 'QR code authentication lemmas',
            'domain': 'lemma.id',
            'admin_email': 'admin@lemma.id'
        },
        {
            'site_id': 'multi_lemma_delegation',
            'name': 'Multi-Lemma Device Delegation',
            'description': 'Device delegation lemmas',
            'domain': 'lemma.id',
            'admin_email': 'admin@lemma.id'
        }
    ]
    
    results = []
    
    try:
        for site_config in sites_to_migrate:
            site_id = site_config['site_id']
            print(f"\n{'='*40}")
            print(f"Migrating: {site_id}")
            print(f"{'='*40}")
            
            # Check if site exists
            site = db.query(Site).filter(Site.site_id == site_id).first()
            
            if not site:
                # Create new site
                print(f"  Creating new site entry...")
                from api.oauth_client_secret_crypto import provision_oauth_client_credentials

                oauth_client_id, oauth_stored = provision_oauth_client_credentials(site_id)
                site = Site(
                    site_id=site_id,
                    company_name=site_config['name'],
                    site_domain=site_config['domain'],
                    admin_email=site_config['admin_email'],
                    oauth_client_id=oauth_client_id,
                    oauth_client_secret=oauth_stored,
                    created_at=datetime.utcnow()
                )
                db.add(site)
                db.flush()
            
            # Generate new keypair
            print(f"  Generating new Ed25519 keypair...")
            issuer = PyMinimalIssuer()
            signing_key_bytes = bytes(issuer.signing_key_bytes())
            
            # Encrypt with KMS
            print(f"  Encrypting with AWS KMS...")
            encrypted_key, kms_key_id = kms.encrypt_signing_key(signing_key_bytes, site_id)
            
            # Update database
            print(f"  Updating database...")
            site.kms_encrypted_signing_key = encrypted_key
            site.kms_key_id = kms_key_id
            site.public_key_hex = issuer.get_public_key_hex()
            site.issuer_did = issuer.get_did()
            site.key_created_at = datetime.utcnow()
            site.key_rotation_due = datetime.utcnow() + timedelta(days=365)
            site.key_status = 'active'
            
            db.commit()
            
            # Verify decryption works
            print(f"  Verifying decryption...")
            decrypted = kms.decrypt_signing_key(encrypted_key, site_id)
            if decrypted != signing_key_bytes:
                print(f"  ❌ ERROR: Decryption verification failed!")
                return False
            
            print(f"  ✅ Success!")
            print(f"     DID: {issuer.get_did()[:50]}...")
            print(f"     Public Key: {issuer.get_public_key_hex()[:30]}...")
            
            results.append({
                'site_id': site_id,
                'did': issuer.get_did(),
                'public_key': issuer.get_public_key_hex(),
                'status': 'migrated'
            })
        
        # Also update lemma_platform if it exists (already done but verify)
        lp = db.query(Site).filter(Site.site_id == 'lemma_platform').first()
        if lp and lp.kms_encrypted_signing_key:
            print(f"\n✅ lemma_platform already has KMS key")
            results.append({
                'site_id': 'lemma_platform',
                'did': lp.issuer_did,
                'public_key': lp.public_key_hex,
                'status': 'existing'
            })
        
        print("\n" + "=" * 60)
        print("MIGRATION COMPLETE")
        print("=" * 60)
        print("\nMigrated Issuers:")
        for r in results:
            print(f"  - {r['site_id']}: {r['status']}")
            print(f"    DID: {r['did'][:50]}...")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == '__main__':
    success = migrate_all_to_kms()
    sys.exit(0 if success else 1)

