"""
Decentralized revocation system for Lemma credentials.
Implements a peer-to-peer revocation broadcast mechanism with CRSets (Compact Revocation Sets).
"""

import os
import json
import time
import hashlib
import random
import base64
import logging
from typing import Dict, Any, List, Set, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

# Set up logging
logger = logging.getLogger(__name__)

class RevocationBitstring:
    """
    Efficient bitstring-based revocation representation.
    Uses a compact bitstring representation to efficiently track revoked credentials.
    """
    
    def __init__(self, issuer_id: str):
        """
        Initialize a new revocation bitstring for an issuer.
        
        Args:
            issuer_id: The DID of the issuer
        """
        self.issuer_id = issuer_id
        self.revoked_ids = set()
        self.last_updated = time.time()
        
        # Bloom filter parameters (for efficient revocation checking)
        self.bitstring_size = 10000  # Size of the bloom filter
        self.num_hashes = 5  # Number of hash functions
        self.bitstring = bytearray(self.bitstring_size // 8 + 1)  # Actual filter
    
    def revoke(self, credential_id: str) -> bool:
        """
        Revoke a credential.
        
        Args:
            credential_id: The ID of the credential to revoke
            
        Returns:
            bool: True if the credential was newly revoked, False if it was already revoked
        """
        if credential_id in self.revoked_ids:
            return False
            
        # Add to the set of revoked IDs
        self.revoked_ids.add(credential_id)
        
        # Update the bitstring (bloom filter)
        self._add_to_bitstring(credential_id)
        
        # Update timestamp
        self.last_updated = time.time()
        
        return True
    
    def is_revoked(self, credential_id: str) -> bool:
        """
        Check if a credential is revoked.
        
        Args:
            credential_id: The ID of the credential to check
            
        Returns:
            bool: True if the credential might be revoked, False if it is definitely not revoked
        """
        # Direct check for certainty
        if credential_id in self.revoked_ids:
            return True
            
        # Use bloom filter for fast negative checks
        return self._check_bitstring(credential_id)
    
    def _add_to_bitstring(self, credential_id: str):
        """Add a credential ID to the bitstring (bloom filter)."""
        for i in range(self.num_hashes):
            # Use different hash seeds for each hash function
            hash_val = int(hashlib.sha256(f"{credential_id}:{i}".encode()).hexdigest(), 16)
            bit_pos = hash_val % self.bitstring_size
            
            # Set the bit at the calculated position
            byte_pos = bit_pos // 8
            bit_offset = bit_pos % 8
            self.bitstring[byte_pos] |= (1 << bit_offset)
    
    def _check_bitstring(self, credential_id: str) -> bool:
        """
        Check if a credential ID might be in the bitstring (bloom filter).
        This can have false positives but no false negatives.
        """
        for i in range(self.num_hashes):
            hash_val = int(hashlib.sha256(f"{credential_id}:{i}".encode()).hexdigest(), 16)
            bit_pos = hash_val % self.bitstring_size
            
            byte_pos = bit_pos // 8
            bit_offset = bit_pos % 8
            
            # If any bit is not set, the credential is definitely not revoked
            if not (self.bitstring[byte_pos] & (1 << bit_offset)):
                return False
                
        # All bits are set, the credential might be revoked
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the revocation data to a dictionary for serialization."""
        return {
            "issuer_id": self.issuer_id,
            "last_updated": self.last_updated,
            "revoked_count": len(self.revoked_ids),
            "revoked_ids": list(self.revoked_ids),
            "bitstring": base64.b64encode(self.bitstring).decode(),
            "bitstring_size": self.bitstring_size,
            "num_hashes": self.num_hashes
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RevocationBitstring':
        """Create a RevocationBitstring from a dictionary."""
        revocation = cls(data["issuer_id"])
        revocation.last_updated = data.get("last_updated", time.time())
        revocation.revoked_ids = set(data.get("revoked_ids", []))
        revocation.bitstring_size = data.get("bitstring_size", 10000)
        revocation.num_hashes = data.get("num_hashes", 5)
        
        # Decode the bitstring
        if "bitstring" in data:
            revocation.bitstring = bytearray(base64.b64decode(data["bitstring"]))
        
        return revocation


class RevocationRegistry:
    """
    Registry for tracking revoked credentials across multiple issuers.
    Provides a central point for checking credential revocation status.
    """
    
    def __init__(self, storage_dir: str):
        """
        Initialize the revocation registry.
        
        Args:
            storage_dir: Directory to store revocation data
        """
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
        
        # Path to the registry file
        self.registry_file = os.path.join(storage_dir, "revocation_registry.json")
        
        # Revocation data by issuer
        self.revocation_data = {}
        
        # Load existing registry if available
        self._load_registry()
    
    def _load_registry(self):
        """Load the registry from disk."""
        if os.path.exists(self.registry_file):
            try:
                with open(self.registry_file, 'r') as f:
                    data = json.load(f)
                    
                # Process each issuer's revocation data
                for issuer_id, revocation_data in data.items():
                    self.revocation_data[issuer_id] = RevocationBitstring.from_dict(revocation_data)
                    
                logger.info(f"Loaded revocation registry with {len(self.revocation_data)} issuers")
            except Exception as e:
                logger.error(f"Error loading revocation registry: {e}")
                # Start with an empty registry in case of error
                self.revocation_data = {}
    
    def _save_registry(self):
        """Save the registry to disk."""
        try:
            # Convert revocation data to dictionaries
            data = {
                issuer_id: revocation.to_dict()
                for issuer_id, revocation in self.revocation_data.items()
            }
            
            # Create a temporary file first to prevent data corruption
            temp_file = f"{self.registry_file}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
                
            # Atomic rename for data safety
            os.replace(temp_file, self.registry_file)
            
            logger.info(f"Saved revocation registry with {len(self.revocation_data)} issuers")
        except Exception as e:
            logger.error(f"Error saving revocation registry: {e}")
    
    def revoke_credential(self, issuer_id: str, credential_id: str) -> bool:
        """
        Revoke a credential.
        
        Args:
            issuer_id: The DID of the issuer
            credential_id: The ID of the credential to revoke
            
        Returns:
            bool: True if the credential was newly revoked, False if it was already revoked
        """
        # Get or create the revocation data for this issuer
        if issuer_id not in self.revocation_data:
            self.revocation_data[issuer_id] = RevocationBitstring(issuer_id)
            
        # Revoke the credential
        result = self.revocation_data[issuer_id].revoke(credential_id)
        
        # Save the updated registry
        self._save_registry()
        
        return result
    
    def is_revoked(self, issuer_id: str, credential_id: str) -> bool:
        """
        Check if a credential is revoked.
        
        Args:
            issuer_id: The DID of the issuer
            credential_id: The ID of the credential to check
            
        Returns:
            bool: True if the credential is revoked, False otherwise
        """
        # If we don't have data for this issuer, the credential is not revoked
        if issuer_id not in self.revocation_data:
            return False
            
        # Check if the credential is revoked
        return self.revocation_data[issuer_id].is_revoked(credential_id)
    
    def get_revocation_data(self, issuer_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the revocation data for an issuer.
        
        Args:
            issuer_id: The DID of the issuer
            
        Returns:
            Dict: The revocation data as a dictionary, or None if not found
        """
        if issuer_id not in self.revocation_data:
            return None
            
        return self.revocation_data[issuer_id].to_dict()
    
    def import_revocation_data(self, data: Dict[str, Any]) -> bool:
        """
        Import revocation data from another registry.
        
        Args:
            data: The revocation data to import
            
        Returns:
            bool: True if the data was successfully imported
        """
        try:
            # Validate the data
            if not isinstance(data, dict) or "issuer_id" not in data:
                logger.error("Invalid revocation data format")
                return False
                
            issuer_id = data["issuer_id"]
            
            # If we don't have data for this issuer, create it
            if issuer_id not in self.revocation_data:
                self.revocation_data[issuer_id] = RevocationBitstring.from_dict(data)
                self._save_registry()
                return True
                
            # If our data is older, update it
            if data.get("last_updated", 0) > self.revocation_data[issuer_id].last_updated:
                self.revocation_data[issuer_id] = RevocationBitstring.from_dict(data)
                self._save_registry()
                return True
                
            # Our data is newer, no update needed
            return False
        except Exception as e:
            logger.error(f"Error importing revocation data: {e}")
            return False


class P2PRevocationNetwork:
    """
    Peer-to-peer network for revocation data exchange.
    Handles actual HTTP requests to peer nodes for revocation data exchange.
    """
    
    def __init__(self, registry: RevocationRegistry, peer_urls: List[str] = None):
        """
        Initialize the P2P revocation network.
        
        Args:
            registry: The local revocation registry
            peer_urls: List of URLs of known peers
        """
        self.registry = registry
        self.peer_urls = peer_urls or []
        self.peers = {}
        self.last_sync = defaultdict(lambda: 0)  # Track last sync time with each peer
        
    def add_peer(self, peer_id: str, peer_url: str):
        """
        Add a peer to the network.
        
        Args:
            peer_id: Unique identifier for the peer
            peer_url: URL to reach the peer
        """
        self.peers[peer_id] = peer_url
        if peer_url not in self.peer_urls:
            self.peer_urls.append(peer_url)
            
        logger.info(f"Added peer {peer_id} at {peer_url}")
    
    def broadcast_revocation(self, issuer_id: str, credential_id: str):
        """
        Broadcast a revocation to all peers.
        
        Args:
            issuer_id: The DID of the issuer
            credential_id: The ID of the credential that was revoked
        """
        # First, revoke the credential locally
        self.registry.revoke_credential(issuer_id, credential_id)
        
        # Get the updated revocation data
        revocation_data = self.registry.get_revocation_data(issuer_id)
        if not revocation_data:
            logger.error(f"Failed to get revocation data for {issuer_id}")
            return
        
        # Broadcast to all peers
        for peer_id, peer_url in self.peers.items():
            try:
                self._send_revocation_data(peer_url, revocation_data)
                logger.info(f"Broadcasted revocation to peer {peer_id}")
            except Exception as e:
                logger.error(f"Error broadcasting revocation to peer {peer_id}: {e}")
    
    def _send_revocation_data(self, peer_url: str, revocation_data: Dict[str, Any]):
        """
        Send revocation data to a peer.
        
        Args:
            peer_url: The URL of the peer
            revocation_data: The revocation data to send
        """
        try:
            import requests
            
            # Normalize URL
            if not peer_url.endswith('/'):
                peer_url += '/'
                
            # Build the endpoint URL
            endpoint = f"{peer_url}api/revocation/import"
            
            # Send the data
            response = requests.post(
                endpoint, 
                json=revocation_data,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            # Check if the request was successful
            if response.status_code == 200:
                return True
            else:
                logger.warning(f"Peer responded with status {response.status_code}: {response.text}")
                return False
                
        except ImportError:
            logger.warning("Requests library not available, skipping P2P communication")
            return False
        except Exception as e:
            logger.error(f"Error sending revocation data: {e}")
            return False
    
    def sync_with_peers(self):
        """
        Synchronize revocation data with all known peers.
        This should be called periodically to keep revocation data up to date.
        """
        sync_results = {}
        
        # For each peer, request their revocation data
        for peer_id, peer_url in self.peers.items():
            try:
                sync_result = self._sync_with_peer(peer_id, peer_url)
                sync_results[peer_id] = sync_result
                if sync_result["success"]:
                    logger.info(f"Synced with peer {peer_id}: {sync_result['updates']} updates")
                else:
                    logger.warning(f"Failed to sync with peer {peer_id}: {sync_result['error']}")
            except Exception as e:
                logger.error(f"Error syncing with peer {peer_id}: {e}")
                sync_results[peer_id] = {"success": False, "error": str(e)}
                
        return sync_results
    
    def _sync_with_peer(self, peer_id: str, peer_url: str) -> Dict[str, Any]:
        """
        Synchronize revocation data with a specific peer.
        
        Args:
            peer_id: The ID of the peer
            peer_url: The URL of the peer
            
        Returns:
            Dict with sync results
        """
        try:
            import requests
            
            # Normalize URL
            if not peer_url.endswith('/'):
                peer_url += '/'
                
            # Get the list of issuers from the peer
            issuers_endpoint = f"{peer_url}api/revocation/issuers"
            issuers_response = requests.get(issuers_endpoint, timeout=10)
            
            if issuers_response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Failed to get issuers from peer: {issuers_response.status_code}"
                }
                
            peer_issuers = issuers_response.json().get("issuers", [])
            updates = 0
            
            # For each issuer, check if we need to update our data
            for issuer_id in peer_issuers:
                # Get the last update time for this issuer from the peer
                issuer_endpoint = f"{peer_url}api/revocation/issuer/{issuer_id}"
                issuer_response = requests.get(issuer_endpoint, timeout=10)
                
                if issuer_response.status_code != 200:
                    logger.warning(f"Failed to get data for issuer {issuer_id} from peer: {issuer_response.status_code}")
                    continue
                    
                peer_issuer_data = issuer_response.json()
                peer_last_updated = peer_issuer_data.get("last_updated", 0)
                
                # Get our local data for this issuer
                local_issuer_data = self.registry.get_revocation_data(issuer_id)
                local_last_updated = local_issuer_data.get("last_updated", 0) if local_issuer_data else 0
                
                # If peer has newer data, import it
                if peer_last_updated > local_last_updated:
                    # Get the full revocation data from the peer
                    data_endpoint = f"{peer_url}api/revocation/data/{issuer_id}"
                    data_response = requests.get(data_endpoint, timeout=10)
                    
                    if data_response.status_code != 200:
                        logger.warning(f"Failed to get revocation data for issuer {issuer_id} from peer: {data_response.status_code}")
                        continue
                        
                    revocation_data = data_response.json()
                    
                    # Import the data
                    if self.registry.import_revocation_data(revocation_data):
                        updates += 1
                        logger.info(f"Imported newer revocation data for {issuer_id} from peer {peer_id}")
            
            # Update the last sync time for this peer
            self.last_sync[peer_id] = time.time()
            
            return {
                "success": True,
                "updates": updates,
                "issuers": len(peer_issuers),
                "timestamp": time.time()
            }
                
        except ImportError:
            return {
                "success": False,
                "error": "Requests library not available"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
            
    def get_sync_status(self) -> Dict[str, Any]:
        """
        Get the synchronization status with all peers.
        
        Returns:
            Dict with status information for each peer
        """
        status = {}
        for peer_id, peer_url in self.peers.items():
            last_sync_time = self.last_sync.get(peer_id, 0)
            status[peer_id] = {
                "url": peer_url,
                "last_sync": last_sync_time,
                "time_since_sync": time.time() - last_sync_time if last_sync_time > 0 else None
            }
            
        return {
            "peers": len(self.peers),
            "last_sync": max(self.last_sync.values()) if self.last_sync else 0,
            "details": status
        }

# Global revocation registry instance
_revocation_registry = None

def get_revocation_registry(storage_dir: str = None):
    """Get the revocation registry instance."""
    global _revocation_registry
    if _revocation_registry is None and storage_dir is not None:
        _revocation_registry = RevocationRegistry(storage_dir)
    return _revocation_registry

def init_revocation_registry(storage_dir: str):
    """Initialize the revocation registry."""
    global _revocation_registry
    _revocation_registry = RevocationRegistry(storage_dir)
    return _revocation_registry 