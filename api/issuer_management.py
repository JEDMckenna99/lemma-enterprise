"""
Lemma Issuer Management
Provides consistent issuers for proper crypto implementation

ALL issuers use KMS-backed storage for FIPS 140-2 Level 2/3 compliance.

SECURITY: This module enforces that ALL signing keys MUST be encrypted by AWS KMS.
If KMS is unavailable, new key generation will FAIL rather than create unprotected keys.
This ensures compliance with FIPS 140-2 Level 2/3 requirements.
"""

import logging
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_PLATFORM_SITE_ALIASES = {"lemma.id", "www.lemma.id", "lemma_platform"}
_PLATFORM_CANONICAL_SITE_ID = "lemma_platform"
_PLATFORM_CANONICAL_DOMAIN = "lemma.id"


class KMSUnavailableError(RuntimeError):
    """
    SECURITY: Raised when KMS is unavailable and a new signing key would be created.
    
    This is a hard failure to prevent creating unencrypted signing keys that would
    violate FIPS 140-2 compliance requirements.
    """
    pass


def _normalize_site_label(value: str) -> str:
    return str(value or "").strip().lower()


def _is_platform_site(site_id: str) -> bool:
    return _normalize_site_label(site_id) in _PLATFORM_SITE_ALIASES


def _issuer_cache_key(site_id: str) -> str:
    normalized = _normalize_site_label(site_id)
    if normalized in _PLATFORM_SITE_ALIASES:
        return _PLATFORM_CANONICAL_SITE_ID
    return str(site_id or "").strip()


def _kms_context_candidates(site_id: str, site=None) -> list[str]:
    candidates: list[str] = []

    def add(value):
        text = str(value or "").strip()
        if text and text not in candidates:
            candidates.append(text)

    if _is_platform_site(site_id):
        add(_PLATFORM_CANONICAL_SITE_ID)
        add(_PLATFORM_CANONICAL_DOMAIN)

    add(site_id)
    add(getattr(site, "site_id", None))
    add(getattr(site, "site_domain", None))
    return candidates

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
            # Query by site_domain (hostname) first, fall back to site_id
            site = db.query(Site).filter_by(site_domain=site_id).first()
            if not site:
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
                import secrets
                site = Site(
                    site_id=site_id,
                    company_name=issuer_name,
                    site_domain='lemma.id',
                    admin_email='admin@lemma.id',
                    api_key=f"lm_{secrets.token_urlsafe(32)}",
                    oauth_client_id=f"client_{secrets.token_urlsafe(16)}",
                    oauth_client_secret=secrets.token_urlsafe(32),
                    created_at=datetime.utcnow()
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
        storage_site_id = _issuer_cache_key(site_id)
        issuer_key = f'iam_{storage_site_id}'
        
        # Check memory cache first
        if issuer_key in self._issuers:
            return self._issuers[issuer_key]
        
        # Check database for existing KMS-encrypted key
        from api.database import SessionLocal, Site
        from api.kms_manager import get_kms_manager, is_kms_available
        from datetime import datetime, timedelta
        
        db = SessionLocal()
        try:
            if _is_platform_site(site_id):
                platform_candidates = []
                for candidate_site_id in (_PLATFORM_CANONICAL_SITE_ID, _PLATFORM_CANONICAL_DOMAIN):
                    found = db.query(Site).filter_by(site_id=candidate_site_id).first()
                    if found and found not in platform_candidates:
                        platform_candidates.append(found)
                found = db.query(Site).filter_by(site_domain=_PLATFORM_CANONICAL_DOMAIN).first()
                if found and found not in platform_candidates:
                    platform_candidates.append(found)
                site = next(
                    (candidate for candidate in platform_candidates if candidate.kms_encrypted_signing_key),
                    platform_candidates[0] if platform_candidates else None,
                )
                if not site:
                    import secrets
                    site = Site(
                        site_id=_PLATFORM_CANONICAL_SITE_ID,
                        company_name='Lemma Platform',
                        site_domain=_PLATFORM_CANONICAL_DOMAIN,
                        admin_email='admin@lemma.id',
                        api_key=f"lm_{secrets.token_urlsafe(32)}",
                        oauth_client_id=f"client_{secrets.token_urlsafe(16)}",
                        oauth_client_secret=secrets.token_urlsafe(32),
                        created_at=datetime.utcnow()
                    )
                    db.add(site)
                    db.flush()
            else:
                # Query by site_domain (hostname) first, fall back to site_id
                site = db.query(Site).filter_by(site_domain=site_id).first()
                if not site:
                    site = db.query(Site).filter_by(site_id=site_id).first()
            kms = get_kms_manager()
            
            from lemma_crypto import PyMinimalIssuer
            
            if site and site.kms_encrypted_signing_key and is_kms_available():
                # LOAD existing key from KMS-encrypted storage
                last_error = None
                decrypt_context = None
                try:
                    # Decrypt signing key using AWS KMS
                    for context_site_id in _kms_context_candidates(storage_site_id, site):
                        try:
                            signing_key_bytes = kms.decrypt_signing_key(
                                site.kms_encrypted_signing_key,
                                context_site_id
                            )
                            decrypt_context = context_site_id
                            break
                        except Exception as exc:
                            last_error = exc
                    else:
                        raise last_error or RuntimeError("No KMS context candidates available")
                    
                    # Load issuer from decrypted key
                    issuer = PyMinimalIssuer.from_seed(list(signing_key_bytes))

                    if decrypt_context != storage_site_id:
                        try:
                            encrypted_key, kms_key_id = kms.encrypt_signing_key(
                                signing_key_bytes,
                                storage_site_id
                            )
                            site.kms_encrypted_signing_key = encrypted_key
                            site.kms_key_id = kms_key_id
                            logger.info(
                                "Migrated issuer KMS context for %s from %s to %s",
                                site_id,
                                decrypt_context,
                                storage_site_id,
                            )
                        except Exception as migrate_error:
                            logger.warning(
                                "Loaded issuer for %s with legacy KMS context %s but could not migrate: %s",
                                site_id,
                                decrypt_context,
                                migrate_error,
                            )
                    
                    # Update last used timestamp
                    site.key_last_used = datetime.utcnow()
                    db.commit()
                    
                    # Cache in memory
                    self._issuers[issuer_key] = issuer
                    self._issuer_metadata[issuer_key] = {
                        'type': 'iam_issuer',
                        'name': f'Lemma IAM - {storage_site_id}',
                        'site_id': storage_site_id,
                        'did': issuer.get_did(),
                        'public_key_hex': issuer.get_public_key_hex(),
                        'trust_score': 0.90,
                        'verified': True,
                        'storage': 'kms_backed'
                    }
                    self._creation_times[issuer_key] = time.time()
                    
                    logger.info(f"✅ Loaded KMS-backed issuer for {storage_site_id}: {issuer.get_did()[:50]}...")
                    return issuer
                    
                except Exception as e:
                    logger.error(f"❌ Failed to load KMS key for {site_id}: {e}")
                    if _is_platform_site(site_id):
                        raise KMSUnavailableError(
                            f"Existing platform issuer key could not be decrypted for {storage_site_id}; "
                            "refusing to rotate the platform issuer DID implicitly."
                        ) from e
                    # Fall through to create new key
            
            # =================================================================
            # SECURITY: Generate NEW keypair - REQUIRES KMS for encryption
            # =================================================================
            # CRITICAL: We must have KMS available to create new signing keys.
            # Creating unencrypted keys would violate FIPS 140-2 compliance.
            
            if not is_kms_available():
                error_msg = (
                    f"SECURITY FAILURE: Cannot create signing key for site '{site_id}' - "
                    f"AWS KMS is unavailable. All signing keys MUST be encrypted by KMS "
                    f"for FIPS 140-2 Level 2/3 compliance. Check AWS credentials and "
                    f"LEMMA_KMS_KEY_ID environment variable."
                )
                logger.critical(f"🚨 {error_msg}")
                raise KMSUnavailableError(error_msg)
            
            # Generate new keypair
            issuer = PyMinimalIssuer()
            signing_key_bytes = bytes(issuer.signing_key_bytes())
            
            # ENCRYPT with AWS KMS - this MUST succeed
            try:
                encrypted_key, kms_key_id = kms.encrypt_signing_key(
                    signing_key_bytes,
                    storage_site_id
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
                    db.commit()
                    logger.info(f"✅ Created NEW KMS-backed issuer for {storage_site_id}")
                    logger.info(f"🔐 Key encrypted with KMS: {kms_key_id[:50]}...")
                else:
                    # Site doesn't exist - this is a configuration error
                    logger.error(f"🚨 SECURITY: Site {storage_site_id} not found in database - cannot persist KMS key!")
                    raise RuntimeError(f"Site {storage_site_id} not found - cannot create issuer without database record")
                
            except KMSUnavailableError:
                raise  # Re-raise our custom error
            except Exception as e:
                # KMS encryption failed - this is a hard failure, NOT a fallback
                error_msg = (
                    f"SECURITY FAILURE: KMS encryption failed for site '{storage_site_id}': {e}. "
                    f"Cannot create signing key without KMS protection."
                )
                logger.critical(f"🚨 {error_msg}")
                raise KMSUnavailableError(error_msg) from e
            
            # Cache in memory (key is safely encrypted in database)
            self._issuers[issuer_key] = issuer
            self._issuer_metadata[issuer_key] = {
                'type': 'iam_issuer',
                'name': f'Lemma IAM - {storage_site_id}',
                'site_id': storage_site_id,
                'did': issuer.get_did(),
                'public_key_hex': issuer.get_public_key_hex(),
                'trust_score': 0.90,
                'verified': True,
                'storage': 'kms_backed'  # Always KMS-backed now
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
