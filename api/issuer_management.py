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
        issuer_key = 'federated_identity'
        
        if issuer_key not in self._issuers:
            try:
                from lemma_crypto import PyMinimalIssuer
                
                # Create persistent federated issuer
                issuer = PyMinimalIssuer()
                
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
        """Get consistent IAM issuer for specific site"""
        issuer_key = f'iam_{site_id}'
        
        if issuer_key not in self._issuers:
            try:
                from lemma_crypto import PyMinimalIssuer
                
                # Create persistent IAM issuer for this site
                issuer = PyMinimalIssuer()
                
                self._issuers[issuer_key] = issuer
                self._issuer_metadata[issuer_key] = {
                    'type': 'iam_issuer',
                    'name': f'Lemma IAM - {site_id}',
                    'site_id': site_id,
                    'did': issuer.get_did(),
                    'public_key_hex': issuer.get_public_key_hex(),
                    'trust_score': 0.90,
                    'verified': True
                }
                self._creation_times[issuer_key] = time.time()
                
                logger.info(f"✅ Created persistent IAM issuer for {site_id}: {issuer.get_did()[:50]}...")
                
            except ImportError as e:
                logger.error(f"❌ Failed to create IAM issuer for {site_id}: {e}")
                raise
                
        return self._issuers[issuer_key]
    
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
        """Generate deterministic user DID (not creating new issuer)"""
        import hashlib
        
        # Create deterministic DID from user ID
        user_hash = hashlib.sha256(f"lemma_user_{user_id}".encode()).hexdigest()
        
        # Format as proper DID (note: this is just identifier, not real public key)
        # In production, users would have their own real DIDs with private keys
        return f"did:lemma:user_{user_hash[:56]}"  # 64 chars total for DID format

# Global issuer manager instance
issuer_manager = LemmaIssuerManager()

def get_issuer_manager():
    """Get the global issuer manager instance"""
    return issuer_manager