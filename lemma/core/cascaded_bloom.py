"""
Cascaded Bloom filter revocation system for Lemma credentials.
Implements OPRF-based privacy-preserving revocation checks with minimal data leakage.
"""

import os
import json
import time
import hashlib
import base64
import logging
import requests
from typing import Dict, Any, List, Optional, Tuple, Union, Set
from datetime import datetime, timedelta
import numpy as np

# Set up logging
logger = logging.getLogger(__name__)

# Try to import pybloom_live, but provide a fallback implementation if not available
try:
    from pybloom_live import BloomFilter, ScalableBloomFilter
    PYBLOOM_AVAILABLE = True
except ImportError:
    logger.warning("pybloom_live not available, using fallback BloomFilter implementation")
    PYBLOOM_AVAILABLE = False
    
    # Simple fallback BloomFilter implementation
    class BloomFilter:
        def __init__(self, capacity, error_rate):
            self.capacity = capacity
            self.error_rate = error_rate
            
            # Calculate optimal bit array size and hash functions
            self.size = self._get_size(capacity, error_rate)
            self.hash_count = self._get_hash_count(self.size, capacity)
            
            # Initialize bit array
            self.bits = [False] * self.size
            self.count = 0
            
        def _get_size(self, n, p):
            """Calculate optimal bit array size."""
            m = -n * np.log(p) / (np.log(2) ** 2)
            return int(m)
            
        def _get_hash_count(self, m, n):
            """Calculate optimal number of hash functions."""
            k = m / n * np.log(2)
            return max(1, int(k))
            
        def _get_positions(self, item):
            """Get bit positions for an item using multiple hash functions."""
            # Convert item to bytes if it's not already
            if not isinstance(item, bytes):
                if isinstance(item, str):
                    item_bytes = item.encode('utf-8')
                else:
                    item_bytes = str(item).encode('utf-8')
            else:
                item_bytes = item
                
            positions = []
            for i in range(self.hash_count):
                # Use different hash seeds
                hash_input = item_bytes + str(i).encode()
                hash_value = int(hashlib.md5(hash_input).hexdigest(), 16)
                positions.append(hash_value % self.size)
                
            return positions
            
        def add(self, item):
            """Add an item to the filter."""
            positions = self._get_positions(item)
            for pos in positions:
                self.bits[pos] = True
            self.count += 1
            
        def __contains__(self, item):
            """Check if an item might be in the filter."""
            positions = self._get_positions(item)
            return all(self.bits[pos] for pos in positions)
            
        def __len__(self):
            """Get count of items added."""
            return self.count
            
        @property
        def bitarray(self):
            """Get bit array as numpy array for serialization."""
            return np.array(self.bits, dtype=np.bool_)


class CascadedBloomRevocation:
    """
    Enhanced revocation system using OPRF evaluations and cascaded Bloom filters.
    Provides privacy-preserving revocation checks without revealing which credential is being checked.
    """
    
    def __init__(self, issuer_id: str, cascade_levels: int = 3, error_rate: float = 0.02, 
                 expected_revocations: int = 10000):
        """
        Initialize a new cascaded Bloom filter for an issuer.
        
        Args:
            issuer_id: The DID of the issuer
            cascade_levels: Number of levels in the cascade (default: 3)
            error_rate: Base error rate for the first level (default: 0.02 or 2%)
            expected_revocations: Expected number of revoked credentials (for sizing)
        """
        self.issuer_id = issuer_id
        self.cascade_levels = cascade_levels
        self.base_error_rate = error_rate
        self.expected_revocations = expected_revocations
        self.revoked_ids = set()  # For direct verification
        self.oprf_evals = {}  # Map from credential ID to OPRF evaluation
        self.last_updated = time.time()
        
        # Initialize the cascade of Bloom filters
        self.levels = []
        self._init_cascade()
        
    def _init_cascade(self):
        """Initialize the Bloom filter cascade with increasing sizes and decreasing error rates."""
        for level in range(self.cascade_levels):
            # Each level uses a different size and error rate
            # Level 0 (most precise): error_rate
            # Level 1 (larger): error_rate/10
            # Level 2 (largest): error_rate/100
            level_error = self.base_error_rate / (10 ** level)
            
            # Size scales with expected items and error rate
            # Formula: m = -n*ln(p)/(ln(2)^2) where:
            # m = bits, n = expected items, p = error rate
            # For simplicity, we'll use the PyBloom implementation which handles this
            
            level_capacity = self.expected_revocations * (10 ** level)
            
            # Create a Bloom filter for this level
            bloom = BloomFilter(capacity=level_capacity, error_rate=level_error)
            
            self.levels.append(bloom)
            
            logger.info(f"Initialized cascade level {level}: capacity={level_capacity}, error_rate={level_error}")
        
    def revoke(self, credential_id: str, oprf_eval: Optional[bytes] = None) -> bool:
        """
        Revoke a credential by adding its OPRF evaluation to the cascade.
        
        Args:
            credential_id: ID of the credential to revoke
            oprf_eval: Optional pre-computed OPRF evaluation
            
        Returns:
            bool: True if the credential was newly revoked, False if it was already revoked
        """
        if credential_id in self.revoked_ids:
            return False
            
        # Add to the set of revoked IDs
        self.revoked_ids.add(credential_id)
        
        # Get or use the OPRF evaluation
        if oprf_eval is None:
            oprf_eval = self._get_oprf_evaluation(credential_id)
        
        # Store the evaluation for future reference
        self.oprf_evals[credential_id] = oprf_eval
        
        # Add to all levels of the cascade
        for bloom in self.levels:
            bloom.add(oprf_eval)
        
        # Update timestamp
        self.last_updated = time.time()
        
        return True
    
    def is_revoked(self, oprf_eval: bytes) -> Tuple[bool, int]:
        """
        Check if a credential is revoked using its OPRF evaluation.
        
        Args:
            oprf_eval: The OPRF evaluation to check
            
        Returns:
            (bool, int): (is_revoked, level_matched) - the level is useful for confidence
        """
        # Check each level, starting from the most precise
        for level, bloom in enumerate(self.levels):
            if oprf_eval in bloom:
                return True, level
                
        # Not found in any level
        return False, -1
    
    def _get_oprf_evaluation(self, credential_id: str) -> bytes:
        """
        Get the OPRF evaluation for a credential ID.
        
        In a real implementation, this would call the OPRF service.
        For now, we use a placeholder hash function.
        
        Args:
            credential_id: ID of the credential
            
        Returns:
            bytes: The OPRF evaluation result
        """
        # This is a placeholder. In a real implementation, this would
        # use the OPRF service to get the evaluation.
        # For testing purposes, we use a hash
        hash_obj = hashlib.sha256(f"oprf_{credential_id}".encode())
        return hash_obj.digest()
    
    def generate_witness(self, credential_id: str, epoch: str) -> Dict[str, Any]:
        """
        Generate a witness proving that a credential is not revoked.
        
        In a real implementation, this would:
        1. Generate random blinding factor r
        2. Compute alpha = r·H₁(credential_id)
        3. Get beta from OPRF service 
        4. Return {alpha, beta, r, epoch}
        
        Args:
            credential_id: ID of the credential
            epoch: Current epoch (e.g., date)
            
        Returns:
            dict: A witness that can be verified offline
        """
        # This is a placeholder implementation
        # In a real implementation, this would use the OPRF client to blind,
        # then call the OPRF server, then package the witness
        
        # Mock the witness for now
        mock_r = os.urandom(32)
        mock_alpha = hashlib.sha256(f"alpha_{credential_id}_{mock_r.hex()}".encode()).digest()
        mock_beta = hashlib.sha256(f"beta_{credential_id}_{mock_r.hex()}".encode()).digest()
        
        return {
            "epoch": epoch,
            "alpha": base64.b64encode(mock_alpha).decode('utf-8'),
            "beta": base64.b64encode(mock_beta).decode('utf-8'),
            "r": base64.b64encode(mock_r).decode('utf-8'),
            "type": "OPRF-Ristretto255"
        }
    
    def verify_witness(self, witness: Dict[str, Any], cascade_hash: str) -> bool:
        """
        Verify a non-revocation witness without connecting to the service.
        
        Args:
            witness: The witness to verify
            cascade_hash: Hash of the cascade for the witness's epoch
            
        Returns:
            bool: True if the witness is valid (credential not revoked)
        """
        # This is a placeholder implementation
        # In a real implementation, this would:
        # 1. Verify the cascade hash matches the expected value for the epoch
        # 2. Compute y = β^(r⁻¹) using values from witness
        # 3. Check if y is in the cascade
        
        try:
            # Decode the witness components
            alpha = base64.b64decode(witness["alpha"])
            beta = base64.b64decode(witness["beta"])
            r = base64.b64decode(witness["r"])
            
            # Simulate unblinding (in a real implementation, this would use actual curve operations)
            # Mock unblinding by deriving a value from the witness components
            mock_y = hashlib.sha256(beta + r).digest()
            
            # Check against cascade (would check against an actual cascade in real implementation)
            # For mock purposes, we'll always return true (not revoked)
            return True
            
        except Exception as e:
            logger.error(f"Error verifying witness: {e}")
            return False
            
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the cascade to a dictionary for serialization.
        
        Returns:
            dict: The cascade data in serializable format
        """
        # Serialize each level of the cascade
        serialized_levels = []
        for i, bloom in enumerate(self.levels):
            level_data = {
                "level": i,
                "capacity": bloom.capacity,
                "error_rate": bloom.error_rate,
                "count": len(bloom),
                "bitarray": base64.b64encode(bloom.bitarray.tobytes()).decode('utf-8'),
                "hash_count": bloom.hash_count
            }
            serialized_levels.append(level_data)
        
        return {
            "issuer_id": self.issuer_id,
            "cascade_levels": self.cascade_levels,
            "base_error_rate": self.base_error_rate,
            "expected_revocations": self.expected_revocations,
            "revoked_count": len(self.revoked_ids),
            "last_updated": self.last_updated,
            "levels": serialized_levels,
            "format_version": "1.0",
            "algorithm": "OPRF-Ristretto255-CascadedBloom"
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CascadedBloomRevocation':
        """
        Create a CascadedBloomRevocation from a dictionary.
        
        Args:
            data: The serialized cascade data
            
        Returns:
            CascadedBloomRevocation: A new instance with the loaded data
        """
        # Create a new instance
        cascade = cls(
            issuer_id=data["issuer_id"],
            cascade_levels=data.get("cascade_levels", 3),
            error_rate=data.get("base_error_rate", 0.02),
            expected_revocations=data.get("expected_revocations", 10000)
        )
        
        # Overwrite the default levels with the loaded ones
        cascade.levels = []
        
        # Recreate each level
        for level_data in data.get("levels", []):
            # Create a BloomFilter with the right parameters
            bloom = BloomFilter(
                capacity=level_data["capacity"],
                error_rate=level_data["error_rate"]
            )
            
            # Restore the bit array
            bitarray_bytes = base64.b64decode(level_data["bitarray"])
            bloom.bitarray = np.frombuffer(bitarray_bytes, dtype=np.bool_).copy()
            
            # Set the hash count
            bloom.hash_count = level_data["hash_count"]
            
            # Add to the cascade
            cascade.levels.append(bloom)
        
        # Restore metadata
        cascade.last_updated = data.get("last_updated", time.time())
        
        return cascade


class OPRFClient:
    """
    Client for the OPRF service.
    Handles blinding, unblinding, and communication with the OPRF service.
    """
    
    def __init__(self, server_url: str = "http://localhost:8080", cache_size: int = 1000):
        """
        Initialize the OPRF client.
        
        Args:
            server_url: URL of the OPRF service
            cache_size: Maximum number of evaluations to cache
        """
        self.server_url = server_url
        self.oprfeval_endpoint = f"{server_url}/oprfeval"
        self.pubkey_endpoint = f"{server_url}/pubkey"
        self.public_key = None
        self._initialize_crypto()
        
        # Cache for OPRF evaluations to reduce network requests and cryptographic operations
        self.cache_size = cache_size
        self.evaluation_cache = {}
        self.cache_hits = 0
        self.cache_misses = 0
        
    def _initialize_crypto(self):
        """Initialize cryptographic backend."""
        try:
            # Try to import pyristretto255
            import pyristretto255
            from pyristretto255 import hashtopoint, Scalar, Element
            
            self.hashtopoint = hashtopoint
            self.Scalar = Scalar
            self.Element = Element
            self.pyristretto255 = pyristretto255
            self.using_mock = False
            logger.info("Using pyristretto255 for OPRF operations")
        except ImportError:
            logger.warning("pyristretto255 not available, using mock implementation")
            self.using_mock = True
    
    def get_public_key(self) -> str:
        """
        Get the OPRF service's public key.
        
        Returns:
            str: Hex-encoded public key
        """
        try:
            response = requests.get(self.pubkey_endpoint)
            response.raise_for_status()
            data = response.json()
            self.public_key = data["publicKey"]
            return self.public_key
        except Exception as e:
            logger.error(f"Failed to get OPRF public key: {e}")
            raise
    
    def blind(self, credential_id: str) -> Tuple[bytes, bytes]:
        """
        Blind a credential ID for OPRF evaluation.
        
        Args:
            credential_id: ID of the credential
            
        Returns:
            Tuple[bytes, bytes]: (alpha, r) - blinded value and blinding factor
        """
        if self.using_mock:
            # Mock implementation for testing
            r = os.urandom(32)
            alpha = hashlib.sha256(f"{credential_id}:{r.hex()}".encode()).digest()
            return alpha, r
        
        try:
            # Convert credential ID to bytes
            credential_bytes = credential_id.encode('utf-8')
            
            # Hash to point: H₁(credential_id)
            input_point = self.hashtopoint(credential_bytes)
            
            # Generate random scalar r
            r = self.Scalar.random()
            r_bytes = bytes(r)
            
            # Compute alpha = r · H₁(credential_id)
            alpha_point = r * input_point
            alpha_bytes = bytes(alpha_point)
            
            return alpha_bytes, r_bytes
        except Exception as e:
            logger.error(f"Error in blind operation: {e}")
            raise
        
    def evaluate(self, alpha: bytes) -> bytes:
        """
        Send a blinded value to the OPRF service for evaluation.
        
        Args:
            alpha: Blinded credential ID
            
        Returns:
            bytes: The evaluated value (beta)
        """
        try:
            # Encode alpha for transmission
            alpha_b64 = base64.b64encode(alpha).decode('utf-8')
            
            # Send to OPRF service
            response = requests.post(
                self.oprfeval_endpoint,
                json={"alpha": [alpha_b64]}
            )
            response.raise_for_status()
            
            # Parse response
            data = response.json()
            beta_b64 = data["beta"][0]
            
            # Decode the response
            beta = base64.b64decode(beta_b64)
            
            return beta
        except Exception as e:
            logger.error(f"Failed to evaluate OPRF: {e}")
            raise
            
    def unblind(self, beta: bytes, r: bytes) -> bytes:
        """
        Unblind an OPRF evaluation result.
        
        Args:
            beta: The evaluation result from the server
            r: The blinding factor used
            
        Returns:
            bytes: The unblinded OPRF result
        """
        if self.using_mock:
            # Mock unblinding for testing
            y = hashlib.sha256(f"{beta.hex()}:{r.hex()}".encode()).digest()
            return y
        
        try:
            # Convert beta to Element
            beta_point = self.Element.from_bytes(beta)
            
            # Convert r to Scalar and compute its inverse
            r_scalar = self.Scalar.from_bytes(r)
            r_inv = ~r_scalar  # Inverse operation
            
            # Compute y = β^(r⁻¹)
            y_point = r_inv * beta_point
            y_bytes = bytes(y_point)
            
            return y_bytes
        except Exception as e:
            logger.error(f"Error in unblind operation: {e}")
            raise
        
    def get_evaluation(self, credential_id: str) -> bytes:
        """
        Perform a complete OPRF evaluation for a credential ID.
        Uses caching to avoid repeated evaluations of the same credential.
        
        Args:
            credential_id: ID of the credential
            
        Returns:
            bytes: The unblinded OPRF evaluation
        """
        # Check cache first
        cache_key = f"{credential_id}"
        if cache_key in self.evaluation_cache:
            self.cache_hits += 1
            logger.debug(f"Cache hit for {credential_id[:8]}... (hit rate: {self.cache_hits/(self.cache_hits+self.cache_misses):.2f})")
            return self.evaluation_cache[cache_key]
        
        # Not in cache, perform evaluation
        self.cache_misses += 1
        
        # Step 1: Blind the credential ID
        alpha, r = self.blind(credential_id)
        
        # Step 2: Get evaluation from server
        beta = self.evaluate(alpha)
        
        # Step 3: Unblind the result
        y = self.unblind(beta, r)
        
        # Store in cache
        self.evaluation_cache[cache_key] = y
        
        # Trim cache if it exceeds the maximum size
        if len(self.evaluation_cache) > self.cache_size:
            # Remove oldest entries (simple LRU implementation)
            keys_to_remove = list(self.evaluation_cache.keys())[:(len(self.evaluation_cache) - self.cache_size)]
            for key in keys_to_remove:
                del self.evaluation_cache[key]
            logger.debug(f"Cache trimmed, removed {len(keys_to_remove)} entries")
        
        return y
        
    def clear_cache(self):
        """Clear the evaluation cache."""
        self.evaluation_cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0
        logger.debug("Evaluation cache cleared")
        
    def get_cache_stats(self):
        """Get cache statistics."""
        total = self.cache_hits + self.cache_misses
        hit_rate = self.cache_hits / total if total > 0 else 0
        return {
            "cache_size": len(self.evaluation_cache),
            "max_cache_size": self.cache_size,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": hit_rate
        }
        
    def generate_witness(self, credential_id: str, epoch: str) -> Dict[str, Any]:
        """
        Generate a witness for a credential ID.
        
        Args:
            credential_id: ID of the credential
            epoch: Current epoch
            
        Returns:
            dict: Witness data with alpha, beta, r
        """
        # Step 1: Blind the credential ID
        alpha, r = self.blind(credential_id)
        
        # Step 2: Get evaluation from server
        beta = self.evaluate(alpha)
        
        # Step 3: Create the witness
        witness = {
            "epoch": epoch,
            "alpha": base64.b64encode(alpha).decode('utf-8'),
            "beta": base64.b64encode(beta).decode('utf-8'),
            "r": base64.b64encode(r).decode('utf-8'),
            "type": "OPRF-Ristretto255"
        }
        
        return witness


def build_revocation_cascade(revoked_list: List[str], 
                             oprf_client: Optional[OPRFClient] = None,
                             issuer_id: str = "did:lemma:default",
                             cascade_levels: int = 3,
                             error_rate: float = 0.02) -> CascadedBloomRevocation:
    """
    Build a cascaded Bloom filter for revoked credentials.
    
    Args:
        revoked_list: List of revoked credential IDs
        oprf_client: Client for OPRF evaluations (optional)
        issuer_id: Issuer DID
        cascade_levels: Number of levels in the cascade
        error_rate: Base error rate for the first level
        
    Returns:
        CascadedBloomRevocation: The built cascade
    """
    # Create the cascade
    cascade = CascadedBloomRevocation(
        issuer_id=issuer_id,
        cascade_levels=cascade_levels, 
        error_rate=error_rate,
        expected_revocations=len(revoked_list)
    )
    
    # Create an OPRF client if none provided
    if not oprf_client:
        oprf_client = OPRFClient()
    
    # Process each revoked credential
    for cid in revoked_list:
        try:
            # Get the OPRF evaluation
            y = oprf_client.get_evaluation(cid)
            
            # Add to cascade
            cascade.revoke(cid, y)
            
        except Exception as e:
            logger.error(f"Error processing revoked credential {cid}: {e}")
    
    return cascade


def create_cascade_bundle(cascade: CascadedBloomRevocation, 
                          epoch: str,
                          expiry_days: int = 1) -> Dict[str, Any]:
    """
    Create a bundle with the cascade and metadata.
    
    Args:
        cascade: The cascade to include
        epoch: Current epoch string (e.g., "2023-06-15")
        expiry_days: Days until the bundle expires
        
    Returns:
        dict: The cascade bundle ready for distribution
    """
    # Get the current time
    now = datetime.now()
    
    # Create the bundle
    bundle = {
        "cascade": cascade.to_dict(),
        "metadata": {
            "issuer": cascade.issuer_id,
            "epoch": epoch,
            "created": now.isoformat(),
            "expires": (now + timedelta(days=expiry_days)).isoformat(),
            "cascade_levels": cascade.cascade_levels,
            "base_error_rate": cascade.base_error_rate,
            "revoked_count": len(cascade.revoked_ids),
            "format_version": "1.0",
            "algorithm": "OPRF-Ristretto255-CascadedBloom"
        }
    }
    
    # Calculate bundle hash for verification
    bundle_hash = hashlib.sha256(json.dumps(bundle, sort_keys=True).encode()).hexdigest()
    bundle["metadata"]["hash"] = bundle_hash
    
    return bundle 