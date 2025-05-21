"""
DID Resolver for Lemma Network
Supports multiple DID methods including did:key, did:web, and did:ethr
"""

import json
import base64
import hashlib
import requests
from typing import Dict, Any, Optional, List, Tuple
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import re

class DIDResolver:
    """Resolver for multiple DID methods."""
    
    def __init__(self):
        """Initialize the DID resolver."""
        # Cache for resolved DIDs to improve performance
        self.did_cache = {}
        
    def resolve(self, did: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a DID to its DID Document.
        Supports did:key, did:web, did:ethr, and did:lemma methods.
        """
        # Check cache first
        if did in self.did_cache:
            return self.did_cache[did]
        
        # Parse method
        match = re.match(r"did:([a-z]+):(.+)", did)
        if not match:
            return None
            
        method, method_specific_id = match.groups()
        
        result = None
        if method == "key":
            result = self._resolve_did_key(method_specific_id)
        elif method == "web":
            result = self._resolve_did_web(method_specific_id)
        elif method == "ethr":
            result = self._resolve_did_ethr(method_specific_id)
        elif method == "lemma":
            result = self._resolve_did_lemma(method_specific_id)
        
        # Cache the result if successful
        if result:
            self.did_cache[did] = result
            
        return result
    
    def get_verification_method(self, did: str, key_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get a verification method from a DID.
        If key_id is specified, return that specific key.
        Otherwise, return the first verification method.
        """
        did_doc = self.resolve(did)
        if not did_doc:
            return None
            
        verification_methods = did_doc.get("verificationMethod", [])
        if not verification_methods:
            return None
            
        if key_id:
            # If key ID is fully qualified (did#keys-1), extract the fragment
            if "#" in key_id:
                key_id = key_id.split("#")[1]
                
            # Find the specified key
            for method in verification_methods:
                method_id = method.get("id", "")
                if "#" in method_id and method_id.split("#")[1] == key_id:
                    return method
                elif method_id == key_id:
                    return method
                    
            # Key not found
            return None
        else:
            # Return the first verification method
            return verification_methods[0]
    
    def get_public_key(self, did: str, key_id: Optional[str] = None) -> Optional[Ed25519PublicKey]:
        """
        Get the public key for a DID.
        Returns a cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PublicKey object.
        """
        verification_method = self.get_verification_method(did, key_id)
        if not verification_method:
            return None
            
        key_type = verification_method.get("type")
        public_key_base58 = verification_method.get("publicKeyBase58")
        public_key_jwk = verification_method.get("publicKeyJwk")
        public_key_multibase = verification_method.get("publicKeyMultibase")
        
        if key_type == "Ed25519VerificationKey2018" or key_type == "Ed25519VerificationKey2020":
            if public_key_base58:
                # For now, we don't fully implement base58 decoding
                # This is a placeholder for when we add the base58 library
                raise NotImplementedError("Base58 decoding not yet implemented")
            elif public_key_jwk:
                # Extract the 'x' parameter from JWK, which contains the public key
                if "x" in public_key_jwk:
                    public_key_bytes = base64.urlsafe_b64decode(public_key_jwk["x"] + "==")
                    return Ed25519PublicKey.from_public_bytes(public_key_bytes)
            elif public_key_multibase:
                # For now, we don't fully implement multibase decoding
                # This is a placeholder for when we add multibase support
                raise NotImplementedError("Multibase decoding not yet implemented")
                
        return None
        
    def _resolve_did_key(self, method_specific_id: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a did:key identifier.
        did:key encodes the public key directly in the identifier.
        """
        # This is a simplified implementation
        # A full implementation would decode the multibase-encoded public key
        
        # For now, we'll create a minimal DID Document
        did = f"did:key:{method_specific_id}"
        
        return {
            "@context": "https://www.w3.org/ns/did/v1",
            "id": did,
            "verificationMethod": [
                {
                    "id": f"{did}#keys-1",
                    "type": "Ed25519VerificationKey2020",
                    "controller": did,
                    "publicKeyMultibase": method_specific_id
                }
            ],
            "authentication": [f"{did}#keys-1"],
            "assertionMethod": [f"{did}#keys-1"]
        }
    
    def _resolve_did_web(self, method_specific_id: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a did:web identifier.
        did:web uses HTTP(S) URLs to resolve DID Documents.
        """
        # Convert did:web ID to URL
        # did:web:example.com -> https://example.com/.well-known/did.json
        # did:web:example.com:user:alice -> https://example.com/user/alice/did.json
        
        parts = method_specific_id.split(':')
        domain = parts[0]
        path = '/'.join(parts[1:]) if len(parts) > 1 else ""
        
        if path:
            url = f"https://{domain}/{path}/did.json"
        else:
            url = f"https://{domain}/.well-known/did.json"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return None
    
    def _resolve_did_ethr(self, method_specific_id: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a did:ethr identifier.
        did:ethr uses Ethereum addresses as identifiers.
        """
        # This is a simplified implementation
        # A full implementation would interact with Ethereum network or use a service
        
        # For now, we'll just create a minimal DID Document
        did = f"did:ethr:{method_specific_id}"
        
        return {
            "@context": "https://www.w3.org/ns/did/v1",
            "id": did,
            "verificationMethod": [
                {
                    "id": f"{did}#controller",
                    "type": "EcdsaSecp256k1RecoveryMethod2020",
                    "controller": did,
                    "blockchainAccountId": f"eip155:1:{method_specific_id}"
                }
            ],
            "authentication": [f"{did}#controller"]
        }
    
    def _resolve_did_lemma(self, method_specific_id: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a did:lemma identifier.
        did:lemma is our custom method for Lemma Network identifiers.
        """
        try:
            # For local did:lemma, we'll use the credential service to get the keys
            from lemma.core.credential_service import get_credential_service
            credential_service = get_credential_service()
            
            # Get the keys from the credential service
            keys = credential_service.keys
            
            # Check if this is our DID
            if method_specific_id == keys.get('did_id'):
                # Create a DID document with our public key
                did = f"did:lemma:{method_specific_id}"
                public_key_jwk = keys.get('public_key_jwk', {})
                
                return {
                    "@context": [
                        "https://www.w3.org/ns/did/v1",
                        "https://w3id.org/security/suites/ed25519-2020/v1"
                    ],
                    "id": did,
                    "verificationMethod": [
                        {
                            "id": f"{did}#keys-1",
                            "type": "Ed25519VerificationKey2020",
                            "controller": did,
                            "publicKeyJwk": public_key_jwk
                        }
                    ],
                    "authentication": [f"{did}#keys-1"],
                    "assertionMethod": [f"{did}#keys-1"]
                }
            
            # If not our DID, try to resolve from network
            from flask import current_app
            peers = current_app.config.get('LEMMA_PEERS', [])
            
            # Try each peer until we find one that can resolve the DID
            for peer in peers:
                try:
                    url = f"{peer}/api/did/lemma/{method_specific_id}"
                    response = requests.get(url, timeout=5)
                    if response.ok:
                        return response.json()
                except:
                    continue
            
            return None
            
        except Exception as e:
            from flask import current_app
            current_app.logger.error(f"Error resolving did:lemma: {str(e)}")
            return None

# Global resolver instance
_did_resolver = None

def get_did_resolver():
    """Get the DID resolver instance."""
    global _did_resolver
    if _did_resolver is None:
        _did_resolver = DIDResolver()
    return _did_resolver 