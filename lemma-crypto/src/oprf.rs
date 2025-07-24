//! OPRF (Oblivious Pseudorandom Function) implementation
//! 
//! Provides privacy-preserving credential verification using Ristretto255

use curve25519_dalek::{
    ristretto::RistrettoPoint,
    scalar::Scalar,
    traits::Identity,
};
use std::collections::HashMap;
use serde::{Deserialize, Serialize};

use crate::constants::*;
use crate::utils::{secure_random_bytes, LRUCache};
use crate::Result;

/// Hash a credential ID to a point on the curve for OPRF operations
fn hash_to_point(data: &[u8]) -> RistrettoPoint {
    use sha2::{Sha512, Digest};
    
    let mut hasher = Sha512::new();
    hasher.update(b"OPRF_CONTEXT");
    hasher.update(data);
    let hash = hasher.finalize();
    
    // Convert to 64-byte array for uniform bytes
    let mut uniform_bytes = [0u8; 64];
    uniform_bytes.copy_from_slice(&hash);
    
    RistrettoPoint::from_uniform_bytes(&uniform_bytes)
}

/// OPRF-related errors
#[derive(Debug, thiserror::Error)]
pub enum OPRFError {
    #[error("Invalid credential ID")]
    InvalidCredentialId,
    #[error("Server key not available")]
    ServerKeyNotAvailable,
    #[error("Invalid blinded point")]
    InvalidBlindedPoint,
    #[error("Invalid server response")]
    InvalidServerResponse,
    #[error("Cryptographic error: {0}")]
    CryptoError(String),
}

/// Result of OPRF evaluation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OPRFResult {
    pub evaluation: [u8; SCALAR_SIZE],
    pub cached: bool,
}

/// Result of blinding operation
#[derive(Debug, Clone)]
pub struct BlindResult {
    pub blinded_point: RistrettoPoint,
    pub unblind_scalar: Scalar,
}

/// OPRF Client for privacy-preserving credential verification
pub struct OPRFClient {
    server_key: Option<Scalar>,
    cache: LRUCache<String, [u8; SCALAR_SIZE]>,
}

impl OPRFClient {
    /// Create a new OPRF client
    pub fn new() -> Self {
        Self {
            server_key: None,
            cache: LRUCache::new(MAX_OPRF_CACHE_SIZE),
        }
    }

    /// Create a new OPRF client with server key (for testing)
    pub fn new_with_server_key(server_key: [u8; SCALAR_SIZE]) -> Self {
        Self {
            server_key: Some(Scalar::from_bytes_mod_order(server_key)),
            cache: LRUCache::new(MAX_OPRF_CACHE_SIZE),
        }
    }

    /// Blind a credential ID for OPRF evaluation
    /// 
    /// This is the client-side operation that blinds the credential ID
    /// before sending it to the server for evaluation.
    pub fn blind(&self, credential_id: &str) -> Result<BlindResult> {
        if credential_id.is_empty() {
            return Err(OPRFError::InvalidCredentialId.into());
        }

        // Hash credential ID to group element
        let input_point = hash_to_point(credential_id.as_bytes());

        // Generate random blinding factor
        let random_bytes = secure_random_bytes(SCALAR_SIZE);
        let blind_scalar = Scalar::from_bytes_mod_order(
            random_bytes.try_into()
                .map_err(|_| OPRFError::CryptoError("Failed to generate blinding scalar".to_string()))?
        );

        // Blind the input point
        let blinded_point = input_point * blind_scalar;

        Ok(BlindResult {
            blinded_point,
            unblind_scalar: blind_scalar,
        })
    }

    /// Server-side OPRF evaluation
    /// 
    /// This evaluates the OPRF on a blinded point using the server's secret key.
    pub fn evaluate(&self, blinded_point: &RistrettoPoint) -> Result<RistrettoPoint> {
        let server_key = self.server_key
            .ok_or(OPRFError::ServerKeyNotAvailable)?;

        // Evaluate OPRF: β = α^k where k is server key
        let evaluated_point = blinded_point * server_key;

        Ok(evaluated_point)
    }

    /// Unblind the server's response to get the final OPRF output
    /// 
    /// This is the client-side operation that unblinds the server's response
    /// to get the final OPRF output.
    pub fn unblind(&self, evaluated_point: &RistrettoPoint, unblind_scalar: &Scalar) -> [u8; SCALAR_SIZE] {
        // Unblind: γ = β^(r^-1) where r is the blinding factor
        let unblinded_point = evaluated_point * unblind_scalar.invert();
        
        // Return the compressed point as bytes
        unblinded_point.compress().to_bytes()
    }

    /// Get OPRF evaluation for a credential ID
    /// 
    /// This performs the complete OPRF flow: blind, evaluate, unblind.
    /// Results are cached to avoid redundant computations.
    pub fn get_evaluation(&mut self, credential_id: &str) -> Result<OPRFResult> {
        if credential_id.is_empty() {
            return Err(OPRFError::InvalidCredentialId.into());
        }

        // Check cache first
        if let Some(cached_result) = self.cache.get(&credential_id.to_string()) {
            return Ok(OPRFResult {
                evaluation: cached_result,
                cached: true,
            });
        }

        // Perform OPRF evaluation
        let blind_result = self.blind(credential_id)?;
        let evaluated_point = self.evaluate(&blind_result.blinded_point)?;
        let final_result = self.unblind(&evaluated_point, &blind_result.unblind_scalar);

        // Cache the result
        self.cache.put(credential_id.to_string(), final_result);

        Ok(OPRFResult {
            evaluation: final_result,
            cached: false,
        })
    }

    /// Set server key (for testing purposes)
    pub fn set_server_key(&mut self, server_key: [u8; SCALAR_SIZE]) {
        self.server_key = Some(Scalar::from_bytes_mod_order(server_key));
    }

    /// Clear the evaluation cache
    pub fn clear_cache(&mut self) {
        self.cache.clear();
    }

    /// Get cache statistics
    pub fn get_cache_stats(&self) -> HashMap<String, usize> {
        let mut stats = HashMap::new();
        stats.insert("cache_size".to_string(), self.cache.len());
        stats.insert("cache_capacity".to_string(), MAX_OPRF_CACHE_SIZE);
        stats
    }
}

impl Default for OPRFClient {
    fn default() -> Self {
        Self::new()
    }
}

/// OPRF Server for handling evaluation requests
pub struct OPRFServer {
    server_key: Scalar,
}

impl OPRFServer {
    /// Create a new OPRF server with a random key
    pub fn new() -> Self {
        let random_bytes = secure_random_bytes(SCALAR_SIZE);
        let server_key = Scalar::from_bytes_mod_order(
            random_bytes.try_into().expect("Failed to generate server key")
        );

        Self { server_key }
    }

    /// Create a new OPRF server with a specific key
    pub fn new_with_key(server_key: [u8; SCALAR_SIZE]) -> Self {
        Self {
            server_key: Scalar::from_bytes_mod_order(server_key),
        }
    }

    /// Get the server's public key (for key agreement protocols)
    pub fn get_public_key(&self) -> [u8; POINT_SIZE] {
        (RistrettoPoint::identity() * self.server_key).compress().to_bytes()
    }

    /// Evaluate OPRF on a blinded point
    pub fn evaluate(&self, blinded_point: &RistrettoPoint) -> RistrettoPoint {
        blinded_point * self.server_key
    }

    /// Batch evaluate multiple blinded points
    pub fn batch_evaluate(&self, blinded_points: &[RistrettoPoint]) -> Vec<RistrettoPoint> {
        blinded_points.iter()
            .map(|point| self.evaluate(point))
            .collect()
    }
}

impl Default for OPRFServer {
    fn default() -> Self {
        Self::new()
    }
}

/// Utility functions for OPRF operations
pub mod utils {
    use super::*;

    /// Parse RistrettoPoint from bytes
    pub fn parse_point(bytes: &[u8]) -> Result<RistrettoPoint> {
        if bytes.len() != POINT_SIZE {
            return Err(OPRFError::InvalidBlindedPoint.into());
        }

        let point_bytes: [u8; POINT_SIZE] = bytes.try_into()
            .map_err(|_| OPRFError::InvalidBlindedPoint)?;

        // Use compress/decompress for RistrettoPoint
        let compressed = curve25519_dalek::ristretto::CompressedRistretto::from_slice(&point_bytes)
            .map_err(|_| OPRFError::InvalidBlindedPoint)?;
        
        Ok(compressed.decompress()
            .ok_or(OPRFError::InvalidBlindedPoint)?)
    }

    /// Convert RistrettoPoint to bytes
    pub fn point_to_bytes(point: &RistrettoPoint) -> [u8; POINT_SIZE] {
        point.compress().to_bytes()
    }

    /// Generate deterministic OPRF output for testing
    pub fn deterministic_oprf_output(credential_id: &str, server_key: &[u8; SCALAR_SIZE]) -> [u8; SCALAR_SIZE] {
        let input_point = hash_to_point(credential_id.as_bytes());
        let key_scalar = Scalar::from_bytes_mod_order(*server_key);
        let output_point = input_point * key_scalar;
        output_point.compress().to_bytes()
    }
}

/// Realistic OPRF Client with server key exchange and network simulation
pub struct RealisticOPRFClient {
    server_public_key: Option<[u8; POINT_SIZE]>,
    shared_secret: Option<Scalar>,
    cache: LRUCache<String, [u8; SCALAR_SIZE]>,
    network_delay_ms: u64,
}

impl RealisticOPRFClient {
    /// Create a new realistic OPRF client
    pub fn new() -> Self {
        Self {
            server_public_key: None,
            shared_secret: None,
            cache: LRUCache::new(MAX_OPRF_CACHE_SIZE),
            network_delay_ms: 50, // Simulate 50ms network delay
        }
    }

    /// Perform key exchange with server (simulated)
    pub fn exchange_keys(&mut self, server_public_key: [u8; POINT_SIZE]) -> Result<()> {
        // Simulate network delay for key exchange
        std::thread::sleep(std::time::Duration::from_millis(self.network_delay_ms));
        
        // In real implementation, this would involve proper key derivation
        // For now, we'll use a simplified approach
        self.server_public_key = Some(server_public_key);
        
        // Derive shared secret from server public key
        let compressed_point = curve25519_dalek::ristretto::CompressedRistretto::from_slice(&server_public_key)
            .map_err(|_| OPRFError::InvalidServerResponse)?;
        let server_point = compressed_point.decompress()
            .ok_or(OPRFError::InvalidServerResponse)?;
        
        // Generate client secret
        let client_secret = Scalar::from_bytes_mod_order(
            secure_random_bytes(SCALAR_SIZE).try_into()
                .map_err(|_| OPRFError::CryptoError("Failed to generate client secret".to_string()))?
        );
        
        // Derive shared secret (simplified - in real protocol would use proper key derivation)
        self.shared_secret = Some(client_secret);
        
        Ok(())
    }

    /// Realistic OPRF evaluation with network simulation
    pub fn realistic_evaluation(&mut self, credential_id: &str) -> Result<OPRFResult> {
        if credential_id.is_empty() {
            return Err(OPRFError::InvalidCredentialId.into());
        }

        // Check cache first (still fast for offline verification)
        if let Some(cached_result) = self.cache.get(&credential_id.to_string()) {
            return Ok(OPRFResult {
                evaluation: cached_result,
                cached: true,
            });
        }

        // Ensure we have exchanged keys
        if self.shared_secret.is_none() {
            return Err(OPRFError::ServerKeyNotAvailable.into());
        }

        // Simulate network delay for server communication
        std::thread::sleep(std::time::Duration::from_millis(self.network_delay_ms));

        // Perform OPRF evaluation (this part is still local cryptographic work)
        let blind_result = self.blind(credential_id)?;
        
        // Simulate server evaluation (with network delay)
        let server_key = self.shared_secret.unwrap();
        let evaluated_point = &blind_result.blinded_point * server_key;
        
        let final_result = self.unblind(&evaluated_point, &blind_result.unblind_scalar);

        // Cache the result
        self.cache.put(credential_id.to_string(), final_result);

        Ok(OPRFResult {
            evaluation: final_result,
            cached: false,
        })
    }

    /// Blind a credential ID for OPRF evaluation
    pub fn blind(&self, credential_id: &str) -> Result<BlindResult> {
        if credential_id.is_empty() {
            return Err(OPRFError::InvalidCredentialId.into());
        }

        // Hash credential ID to group element
        let input_point = hash_to_point(credential_id.as_bytes());

        // Generate random blinding factor
        let random_bytes = secure_random_bytes(SCALAR_SIZE);
        let blind_scalar = Scalar::from_bytes_mod_order(
            random_bytes.try_into()
                .map_err(|_| OPRFError::CryptoError("Failed to generate blinding scalar".to_string()))?
        );

        // Blind the input point
        let blinded_point = input_point * blind_scalar;

        Ok(BlindResult {
            blinded_point,
            unblind_scalar: blind_scalar,
        })
    }

    /// Unblind the evaluated point
    pub fn unblind(&self, evaluated_point: &RistrettoPoint, unblind_scalar: &Scalar) -> [u8; SCALAR_SIZE] {
        // Unblind by multiplying with inverse of blinding scalar
        let unblinded_point = evaluated_point * unblind_scalar.invert();
        
        // Convert to bytes
        let mut result = [0u8; SCALAR_SIZE];
        result.copy_from_slice(&unblinded_point.compress().to_bytes());
        result
    }

    /// Set network delay for testing
    pub fn set_network_delay(&mut self, delay_ms: u64) {
        self.network_delay_ms = delay_ms;
    }

    /// Clear cache and reset keys (for testing)
    pub fn reset(&mut self) {
        self.cache.clear();
        self.server_public_key = None;
        self.shared_secret = None;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_oprf_roundtrip() {
        let server_key = [1u8; SCALAR_SIZE];
        let mut client = OPRFClient::new_with_server_key(server_key);
        let credential_id = "test_credential_123";

        // Test complete OPRF flow
        let result = client.get_evaluation(credential_id).unwrap();
        assert_eq!(result.evaluation.len(), SCALAR_SIZE);
        assert!(!result.cached);

        // Test caching
        let result2 = client.get_evaluation(credential_id).unwrap();
        assert_eq!(result.evaluation, result2.evaluation);
        assert!(result2.cached);
    }

    #[test]
    fn test_blind_unblind() {
        let server_key = [2u8; SCALAR_SIZE];
        let client = OPRFClient::new_with_server_key(server_key);
        let credential_id = "test_credential_456";

        // Test manual blind/unblind flow
        let blind_result = client.blind(credential_id).unwrap();
        let evaluated_point = client.evaluate(&blind_result.blinded_point).unwrap();
        let final_result = client.unblind(&evaluated_point, &blind_result.unblind_scalar);

        assert_eq!(final_result.len(), SCALAR_SIZE);

        // Test deterministic output
        let expected = utils::deterministic_oprf_output(credential_id, &server_key);
        assert_eq!(final_result, expected);
    }

    #[test]
    fn test_oprf_server() {
        let server_key = [3u8; SCALAR_SIZE];
        let server = OPRFServer::new_with_key(server_key);
        let client = OPRFClient::new();

        let credential_id = "test_credential_789";
        let blind_result = client.blind(credential_id).unwrap();
        
        // Server evaluates
        let evaluated_point = server.evaluate(&blind_result.blinded_point);
        
        // Client unblinds
        let final_result = client.unblind(&evaluated_point, &blind_result.unblind_scalar);
        
        // Verify result
        let expected = utils::deterministic_oprf_output(credential_id, &server_key);
        assert_eq!(final_result, expected);
    }

    #[test]
    fn test_batch_evaluation() {
        let server = OPRFServer::new();
        let client = OPRFClient::new();

        let credential_ids = vec!["cred1", "cred2", "cred3"];
        let blind_results: Vec<_> = credential_ids.iter()
            .map(|id| client.blind(id).unwrap())
            .collect();

        let blinded_points: Vec<_> = blind_results.iter()
            .map(|result| result.blinded_point)
            .collect();

        let evaluated_points = server.batch_evaluate(&blinded_points);
        assert_eq!(evaluated_points.len(), credential_ids.len());
    }

    #[test]
    fn test_cache_functionality() {
        let server_key = [4u8; SCALAR_SIZE];
        let mut client = OPRFClient::new_with_server_key(server_key);
        
        // Fill cache
        for i in 0..10 {
            let credential_id = format!("credential_{}", i);
            let result = client.get_evaluation(&credential_id).unwrap();
            assert!(!result.cached);
        }

        // Test cache hits
        for i in 0..10 {
            let credential_id = format!("credential_{}", i);
            let result = client.get_evaluation(&credential_id).unwrap();
            assert!(result.cached);
        }

        // Test cache stats
        let stats = client.get_cache_stats();
        assert_eq!(stats.get("cache_size"), Some(&10));
    }

    #[test]
    fn test_error_handling() {
        let mut client = OPRFClient::new();
        
        // Test with no server key
        let result = client.get_evaluation("test");
        assert!(result.is_err());
        
        // Test with empty credential ID
        let result = client.get_evaluation("");
        assert!(result.is_err());
    }
} 