#!/usr/bin/env python3
"""
Re-encrypt the lemma_platform signing key using the corrected KMS encryption context.

This script is needed because the original key was encrypted with a timestamp
in the encryption context, which makes decryption impossible since we don't
store the timestamp.

The corrected encryption context does NOT include timestamp.
"""

import os
import sys

def reencrypt_key():
    print("=" * 60)
    print("LEMMA KMS KEY RE-ENCRYPTION")
    print("=" * 60)
    
    from api.database import SessionLocal, Site
    from api.kms_manager import get_kms_manager, is_kms_available
    from datetime import datetime, timedelta
    
    if not is_kms_available():
        print("ERROR: KMS is not available!")
        return False
    
    kms = get_kms_manager()
    db = SessionLocal()
    
    try:
        # Get the site
        site = db.query(Site).filter(Site.site_id == 'lemma_platform').first()
        if not site:
            print("ERROR: lemma_platform site not found!")
            return False
        
        print(f"\nCurrent state:")
        print(f"  Site ID: {site.site_id}")
        print(f"  Has encrypted key: {bool(site.kms_encrypted_signing_key)}")
        print(f"  Current public key: {site.public_key_hex[:30] if site.public_key_hex else 'None'}...")
        print(f"  Current issuer DID: {site.issuer_did[:40] if site.issuer_did else 'None'}...")
        
        # Generate new keypair
        from lemma_crypto import PyMinimalIssuer
        print("\nGenerating new keypair...")
        issuer = PyMinimalIssuer()
        
        # Get signing key bytes
        signing_key_bytes = bytes(issuer.signing_key_bytes())
        print(f"  Signing key: {len(signing_key_bytes)} bytes")
        
        # Encrypt with KMS (using corrected context without timestamp)
        print("\nEncrypting with KMS...")
        encrypted_key, kms_key_id = kms.encrypt_signing_key(signing_key_bytes, 'lemma_platform')
        print(f"  Encrypted key length: {len(encrypted_key)} chars")
        print(f"  KMS Key ID: {kms_key_id[:50]}...")
        
        # Update database
        print("\nUpdating database...")
        site.kms_encrypted_signing_key = encrypted_key
        site.kms_key_id = kms_key_id
        site.public_key_hex = issuer.get_public_key_hex()
        site.issuer_did = issuer.get_did()
        site.key_created_at = datetime.utcnow()
        site.key_rotation_due = datetime.utcnow() + timedelta(days=365)
        site.key_status = 'active'
        db.commit()
        
        print(f"\nNew state:")
        print(f"  Public key: {site.public_key_hex[:30]}...")
        print(f"  Issuer DID: {site.issuer_did[:40]}...")
        print(f"  Key created: {site.key_created_at}")
        
        # Verify decryption works
        print("\nVerifying decryption...")
        decrypted = kms.decrypt_signing_key(encrypted_key, 'lemma_platform')
        if decrypted == signing_key_bytes:
            print("  Decryption successful!")
        else:
            print("  ERROR: Decrypted key doesn't match!")
            return False
        
        # Verify issuer loads correctly
        print("\nVerifying issuer load...")
        from api.issuer_management import get_issuer_manager
        manager = get_issuer_manager()
        manager._issuers.clear()  # Clear cache
        
        loaded_issuer = manager.get_iam_issuer('lemma_platform')
        if loaded_issuer.get_public_key_hex() == issuer.get_public_key_hex():
            print("  Issuer loaded correctly!")
        else:
            print("  WARNING: Issuer public keys don't match!")
        
        print("\n" + "=" * 60)
        print("KMS KEY RE-ENCRYPTION COMPLETE")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == '__main__':
    success = reencrypt_key()
    sys.exit(0 if success else 1)

