"""
Lemma Issuer Management
Provides consistent issuers for proper crypto implementation
"""

import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class LemmaIssuerManager:
    """
    Manages consistent issuers for different credential types
    Ensures same issuer DID used for same credential type
    """
    
    def __init__(self):
        self._issuers: Dict[str, any] = {}
        self._issuer_metadata: Dict[str, Dict] = {}
        self._creation_times: Dict[str, float] = {}
        
    def get_federated_issuer(self):
        """Get consistent federated identity issuer"""
        import os
        import hashlib
        
        issuer_key = 'federated_identity'
        
        if issuer_key not in self._issuers:
            try:
                from lemma_crypto import PyMinimalIssuer
                
                # Create persistent federated issuer from environment seed or derive from secret
                federated_seed_hex = os.environ.get('LEMMA_FEDERATED_ISSUER_SEED')
                
                if federated_seed_hex:
                    # Use configured seed
                    seed_bytes = bytes.fromhex(federated_seed_hex)
                    issuer = PyMinimalIssuer.from_seed(list(seed_bytes))
                    logger.info("✅ Using LEMMA_FEDERATED_ISSUER_SEED for federated issuer")
                else:
                    # Derive deterministic seed from API key (ensures consistency)
                    api_secret = os.environ.get('LEMMA_API_SECRET', 'lemma-federated-network-default-seed-v1')
                    seed_bytes = hashlib.sha256(api_secret.encode()).digest()
                    issuer = PyMinimalIssuer.from_seed(list(seed_bytes))
                    logger.info("✅ Derived federated issuer seed from LEMMA_API_SECRET")
                
                self._issuers[issuer_key] = issuer
                self._issuer_metadata[issuer_key] = {
                    'type': 'federated_identity',
                    'name': 'Lemma Federated Identity Network',
                    'did': issuer.get_did(),
                    'public_key_hex': issuer.get_public_key_hex(),
                    'trust_score': 0.95,
                    'verified': True
                }
                self._creation_times[issuer_key] = time.time()
                
                logger.info(f"✅ Created persistent federated issuer: {issuer.get_did()[:50]}...")
                
            except ImportError as e:
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
        """Get consistent issuer for multi-lemma types (QR auth, delegation, etc.)"""
        issuer_key = f'multi_lemma_{lemma_type}'
        
        if issuer_key not in self._issuers:
            try:
                from lemma_crypto import PyMinimalIssuer
                
                issuer = PyMinimalIssuer()
                
                self._issuers[issuer_key] = issuer
                self._issuer_metadata[issuer_key] = {
                    'type': f'multi_lemma_{lemma_type}',
                    'name': f'Lemma {lemma_type.title()} Issuer',
                    'lemma_type': lemma_type,
                    'did': issuer.get_did(),
                    'public_key_hex': issuer.get_public_key_hex(),
                    'trust_score': 0.85,
                    'verified': True
                }
                self._creation_times[issuer_key] = time.time()
                
                logger.info(f"✅ Created persistent {lemma_type} issuer: {issuer.get_did()[:50]}...")
                
            except ImportError as e:
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
