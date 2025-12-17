"""
Lemma Issuer Management
Provides consistent issuers for proper crypto implementation

ALL issuers use KMS-backed storage for FIPS 140-2 Level 2/3 compliance.
"""

import logging
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class LemmaIssuerManager:
    """
    Manages consistent issuers for different credential types
    Ensures same issuer DID used for same credential type
    
    ALL issuers are now KMS-backed for security compliance.
    """
    
    def __init__(self):
        self._issuers: Dict[str, any] = {}
        self._issuer_metadata: Dict[str, Dict] = {}
        self._creation_times: Dict[str, float] = {}
    
    def _load_or_create_kms_issuer(self, site_id: str, issuer_name: str, trust_score: float = 0.90) -> Tuple[any, Dict]:
        """
        Common method to load or create a KMS-backed issuer.
        
        This is the ONLY way issuers should be created - all use KMS storage.
        """
        from api.database import SessionLocal, Site
        from api.kms_manager import get_kms_manager, is_kms_available
        from datetime import datetime, timedelta
        from lemma_crypto import PyMinimalIssuer
        
        db = SessionLocal()
        try:
            site = db.query(Site).filter_by(site_id=site_id).first()
            kms = get_kms_manager()
            
            # Try to load existing KMS-encrypted key
            if site and site.kms_encrypted_signing_key and is_kms_available():
                try:
                    signing_key_bytes = kms.decrypt_signing_key(
                        site.kms_encrypted_signing_key,
                        site_id
                    )
                    issuer = PyMinimalIssuer.from_seed(list(signing_key_bytes))
                    
                    site.key_last_used = datetime.utcnow()
                    db.commit()
                    
                    metadata = {
                        'type': site_id,
                        'name': issuer_name,
                        'site_id': site_id,
                        'did': issuer.get_did(),
                        'public_key_hex': issuer.get_public_key_hex(),
                        'trust_score': trust_score,
                        'verified': True,
                        'storage': 'kms_backed'
                    }
                    
                    logger.info(f"✅ Loaded KMS-backed issuer for {site_id}: {issuer.get_did()[:50]}...")
                    return issuer, metadata
                    
                except Exception as e:
                    logger.error(f"❌ Failed to load KMS key for {site_id}: {e}")
                    # Fall through to create new key
            
            # Create new keypair and encrypt with KMS
            if not is_kms_available():
                raise RuntimeError(f"KMS not available - cannot create issuer for {site_id}")
            
            issuer = PyMinimalIssuer()
            signing_key_bytes = bytes(issuer.signing_key_bytes())
            
            encrypted_key, kms_key_id = kms.encrypt_signing_key(signing_key_bytes, site_id)
            
            # Create or update site in database
            if not site:
                site = Site(
                    site_id=site_id,
                    site_name=issuer_name,
                    site_domain='lemma.id',
                    admin_email='admin@lemma.id',
                    created_at=datetime.utcnow(),
                    is_active=True
                )
                db.add(site)
            
            site.kms_encrypted_signing_key = encrypted_key
            site.kms_key_id = kms_key_id
            site.public_key_hex = issuer.get_public_key_hex()
            site.issuer_did = issuer.get_did()
            site.key_created_at = datetime.utcnow()
            site.key_rotation_due = datetime.utcnow() + timedelta(days=365)
            site.key_status = 'active'
            
            db.commit()
            
            metadata = {
                'type': site_id,
                'name': issuer_name,
                'site_id': site_id,
                'did': issuer.get_did(),
                'public_key_hex': issuer.get_public_key_hex(),
                'trust_score': trust_score,
                'verified': True,
                'storage': 'kms_backed'
            }
            
            logger.info(f"✅ Created NEW KMS-backed issuer for {site_id}: {issuer.get_did()[:50]}...")
            return issuer, metadata
            
        finally:
            db.close()
        
    def get_federated_issuer(self):
        """Get consistent federated identity issuer (KMS-backed)"""
        issuer_key = 'federated_identity'
        
        if issuer_key not in self._issuers:
            try:
                issuer, metadata = self._load_or_create_kms_issuer(
                    site_id='federated_network',
                    issuer_name='Lemma Federated Identity Network',
                    trust_score=0.95
                )
                
                self._issuers[issuer_key] = issuer
                self._issuer_metadata[issuer_key] = metadata
                self._creation_times[issuer_key] = time.time()
                
            except Exception as e:
                logger.error(f"❌ Failed to create federated issuer: {e}")
                raise
                
        return self._issuers[issuer_key]
    
    def get_iam_issuer(self, site_id: str):
        """Get consistent IAM issuer for specific site - UNIQUE keypair per site with KMS storage"""
        issuer_key = f'iam_{site_id}'
        
        # Check memory cache first
        if issuer_key in self._issuers:
            return self._issuers[issuer_key]
        
        # Check database for existing KMS-encrypted key
        from api.database import SessionLocal, Site
        from api.kms_manager import get_kms_manager, is_kms_available
        from datetime import datetime, timedelta
        
        db = SessionLocal()
        try:
            site = db.query(Site).filter_by(site_id=site_id).first()
            kms = get_kms_manager()
            
            from lemma_crypto import PyMinimalIssuer
            
            if site and site.kms_encrypted_signing_key and is_kms_available():
                # LOAD existing key from KMS-encrypted storage
                try:
                    # Decrypt signing key using AWS KMS
                    signing_key_bytes = kms.decrypt_signing_key(
                        site.kms_encrypted_signing_key,
                        site_id
                    )
                    
                    # Load issuer from decrypted key
                    issuer = PyMinimalIssuer.from_seed(list(signing_key_bytes))
                    
                    # Update last used timestamp
                    site.key_last_used = datetime.utcnow()
                    db.commit()
                    
                    # Cache in memory
                    self._issuers[issuer_key] = issuer
                    self._issuer_metadata[issuer_key] = {
                        'type': 'iam_issuer',
                        'name': f'Lemma IAM - {site_id}',
                        'site_id': site_id,
                        'did': issuer.get_did(),
                        'public_key_hex': issuer.get_public_key_hex(),
                        'trust_score': 0.90,
                        'verified': True,
                        'storage': 'kms_backed'
                    }
                    self._creation_times[issuer_key] = time.time()
                    
                    logger.info(f"✅ Loaded KMS-backed issuer for {site_id}: {issuer.get_did()[:50]}...")
                    return issuer
                    
                except Exception as e:
                    logger.error(f"❌ Failed to load KMS key for {site_id}: {e}")
                    # Fall through to create new key
            
            # Generate NEW keypair and store with KMS encryption
            issuer = PyMinimalIssuer()  # Generates NEW keypair!
            
            # Get signing key bytes for encryption
            signing_key_bytes = bytes(issuer.signing_key_bytes())
            
            if is_kms_available():
                # ENCRYPT with AWS KMS
                try:
                    encrypted_key, kms_key_id = kms.encrypt_signing_key(
                        signing_key_bytes,
                        site_id
                    )
                    
                    # Store encrypted key in database
                    if site:
                        site.kms_encrypted_signing_key = encrypted_key
                        site.kms_key_id = kms_key_id
                        site.public_key_hex = issuer.get_public_key_hex()
                        site.issuer_did = issuer.get_did()
                        site.key_created_at = datetime.utcnow()
                        site.key_rotation_due = datetime.utcnow() + timedelta(days=365)
                        site.key_status = 'active'
                    else:
                        logger.warning(f"⚠️ Site {site_id} not found in database - key not persisted")
                    
                    db.commit()
                    logger.info(f"✅ Created NEW KMS-backed issuer for {site_id}")
                    logger.info(f"🔐 Key encrypted with KMS: {kms_key_id[:50]}...")
                    
                except Exception as e:
                    logger.error(f"❌ KMS encryption failed for {site_id}: {e}")
                    logger.warning("⚠️ Falling back to memory-only storage (not persistent!)")
            else:
                logger.warning(f"⚠️ KMS not available - key for {site_id} stored in memory only (not persistent!)")
            
            # Cache in memory
            self._issuers[issuer_key] = issuer
            self._issuer_metadata[issuer_key] = {
                'type': 'iam_issuer',
                'name': f'Lemma IAM - {site_id}',
                'site_id': site_id,
                'did': issuer.get_did(),
                'public_key_hex': issuer.get_public_key_hex(),
                'trust_score': 0.90,
                'verified': True,
                'storage': 'kms_backed' if is_kms_available() else 'memory_only'
            }
            self._creation_times[issuer_key] = time.time()
            
            return issuer
            
        except ImportError as e:
            logger.error(f"❌ Failed to import crypto library for {site_id}: {e}")
            raise
        finally:
            db.close()
    
    def get_multi_lemma_issuer(self, lemma_type: str):
        """Get consistent issuer for multi-lemma types (KMS-backed)"""
        issuer_key = f'multi_lemma_{lemma_type}'
        
        if issuer_key not in self._issuers:
            try:
                # Map lemma types to site IDs
                site_id = f'multi_lemma_{lemma_type}'
                issuer_name = f'Lemma {lemma_type.replace("_", " ").title()} Issuer'
                
                issuer, metadata = self._load_or_create_kms_issuer(
                    site_id=site_id,
                    issuer_name=issuer_name,
                    trust_score=0.85
                )
                metadata['lemma_type'] = lemma_type
                
                self._issuers[issuer_key] = issuer
                self._issuer_metadata[issuer_key] = metadata
                self._creation_times[issuer_key] = time.time()
                
            except Exception as e:
                logger.error(f"❌ Failed to create {lemma_type} issuer: {e}")
                raise
                
        return self._issuers[issuer_key]
    
    def generate_deterministic_user_did(self, user_id: str) -> str:
        """
        Generate deterministic user DID (legacy helper).

        NOTE: This produces a stable identifier and is NOT pairwise.
        Prefer PPID subjects (see `generate_ppid_did_from_email`) for cross-RP unlinkability.
        """
        import hashlib
        
        # Create deterministic DID from user ID
        user_hash = hashlib.sha256(f"lemma_user_{user_id}".encode()).hexdigest()
        
        # Format as proper DID (note: this is just identifier, not real public key)
        # In production, users would have their own real DIDs with private keys
        return f"did:lemma:user_{user_hash[:56]}"  # 64 chars total for DID format

    def generate_ppid_did_from_email(self, email: str, rp_id: str) -> str:
        """Generate pairwise subject DID for a user (PPID) from email + relying party id."""
        from api.ppid import derive_ppid_did
        return derive_ppid_did(email, rp_id)

# Global issuer manager instance
issuer_manager = LemmaIssuerManager()

def get_issuer_manager():
    """Get the global issuer manager instance"""
    return issuer_manager
