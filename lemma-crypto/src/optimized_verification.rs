//! Optimized Verification Engine
//! 
//! Performance optimizations for the working crypto foundation:
//! - Public key caching (eliminate repeated DID parsing)
//! - OPRF result caching (eliminate repeated evaluations)
//! - Pre-allocated buffers (eliminate memory allocation overhead)
//! - Batch verification (process multiple credentials efficiently)

use crate::minimal_core::{MinimalCredential, MinimalError};
use crate::complete_verification::{CompleteVerificationResult, CompleteVerifier};
use crate::oprf::{OPRFClient, OPRFResult};
use crate::bloom::CascadedBloomFilter;

use ed25519_dalek::{Verifier, VerifyingKey, Signature};
use std::collections::HashMap;
use sha2::{Sha256, Digest};

/// Optimized verifier with caching and pre-allocation
pub struct OptimizedVerifier {
    // Caching layers
    public_key_cache: HashMap<String, VerifyingKey>, // Cache DIDs → public keys
    oprf_result_cache: HashMap<String, OPRFResult>,   // Cache credential IDs → OPRF results
    
    // Core components
    oprf_client: OPRFClient,
    revocation_filter: CascadedBloomFilter,
    
    // Pre-allocated buffers
    message_buffer: Vec<u8>,
    signature_buffer: [u8; 64],
    
    // Performance stats
    cache_hits: u64,
    cache_misses: u64,
    total_verifications: u64,
}

impl OptimizedVerifier {
    /// Create optimized verifier with caching
    pub fn new() -> std::result::Result<Self, MinimalError> {
        let server_key = [42u8; 32]; // Network-shared OPRF key
        let oprf_client = OPRFClient::new_with_server_key(server_key);
        let revocation_filter = CascadedBloomFilter::new(3, 10000, 0.001)
            .map_err(|_| MinimalError::InvalidKey)?;
        
        Ok(Self {
            public_key_cache: HashMap::with_capacity(1000), // Pre-allocate for 1000 issuers
            oprf_result_cache: HashMap::with_capacity(10000), // Pre-allocate for 10000 credentials
            oprf_client,
            revocation_filter,
            message_buffer: Vec::with_capacity(1024), // Pre-allocate message buffer
            signature_buffer: [0u8; 64],
            cache_hits: 0,
            cache_misses: 0,
            total_verifications: 0,
        })
    }
    
    /// Optimized complete verification with caching
    pub fn verify_optimized(&mut self, credential: &MinimalCredential) -> std::result::Result<OptimizedVerificationResult, MinimalError> {
        let total_start = std::time::Instant::now();
        self.total_verifications += 1;
        
        // OPTIMIZATION 1: Cached public key extraction
        let sig_start = std::time::Instant::now();
        let public_key = self.get_cached_public_key(&credential.issuer)?;
        let signature_valid = self.verify_signature_optimized(credential, &public_key)?;
        let signature_time_ns = sig_start.elapsed().as_nanos() as u64;
        
        // OPTIMIZATION 2: Cached OPRF evaluation
        let revocation_start = std::time::Instant::now();
        let not_revoked = if signature_valid {
            self.check_revocation_cached(&credential.id)?
        } else {
            false // Skip revocation check if signature invalid
        };
        let revocation_time_ns = revocation_start.elapsed().as_nanos() as u64;
        
        let total_time_ns = total_start.elapsed().as_nanos() as u64;
        let verified = signature_valid && not_revoked;
        
        Ok(OptimizedVerificationResult {
            verified,
            signature_valid,
            not_revoked,
            issuer_did: credential.issuer.clone(),
            verification_time_ns: total_time_ns,
            signature_time_ns,
            revocation_time_ns,
            confidence: if verified { 1.0 } else { 0.0 },
            cache_hit: self.cache_hits > 0,
            optimization_used: true,
        })
    }
    
    /// OPTIMIZATION 1: Get public key with caching
    fn get_cached_public_key(&mut self, issuer_did: &str) -> std::result::Result<VerifyingKey, MinimalError> {
        // Check cache first
        if let Some(cached_key) = self.public_key_cache.get(issuer_did) {
            self.cache_hits += 1;
            return Ok(*cached_key);
        }
        
        self.cache_misses += 1;
        
        // Extract public key from DID (expensive operation)
        let parts: Vec<&str> = issuer_did.split(':').collect();
        if parts.len() != 3 || parts[0] != "did" || parts[1] != "lemma" {
            return Err(MinimalError::InvalidDID);
        }
        
        let public_key_hex = parts[2];
        let public_key_bytes = hex::decode(public_key_hex)
            .map_err(|_| MinimalError::InvalidKey)?;
        
        if public_key_bytes.len() != 32 {
            return Err(MinimalError::InvalidKey);
        }
        
        let mut key_array = [0u8; 32];
        key_array.copy_from_slice(&public_key_bytes);
        
        let verifying_key = VerifyingKey::from_bytes(&key_array)
            .map_err(MinimalError::Ed25519)?;
        
        // Cache for future use
        self.public_key_cache.insert(issuer_did.to_string(), verifying_key);
        
        Ok(verifying_key)
    }
    
    /// OPTIMIZATION 2: Verify signature with pre-allocated buffers
    fn verify_signature_optimized(
        &mut self, 
        credential: &MinimalCredential, 
        public_key: &VerifyingKey
    ) -> std::result::Result<bool, MinimalError> {
        let proof = credential.proof.as_ref()
            .ok_or(MinimalError::InvalidSignature)?;
        
        // Create verification message using pre-allocated buffer
        self.message_buffer.clear();
        self.create_verification_message_buffered(credential)?;
        
        // Decode signature into pre-allocated buffer
        let signature_bytes = hex::decode(&proof.signature_value)
            .map_err(|_| MinimalError::InvalidSignature)?;
        
        if signature_bytes.len() != 64 {
            return Err(MinimalError::InvalidSignature);
        }
        
        self.signature_buffer.copy_from_slice(&signature_bytes);
        let signature = Signature::from_bytes(&self.signature_buffer);
        
        // Verify signature
        match public_key.verify(&self.message_buffer, &signature) {
            Ok(()) => Ok(true),
            Err(_) => Ok(false),
        }
    }
    
    /// OPTIMIZATION 3: Cached OPRF revocation check
    fn check_revocation_cached(&mut self, credential_id: &str) -> std::result::Result<bool, MinimalError> {
        // Check OPRF cache first
        let oprf_result = if let Some(cached_result) = self.oprf_result_cache.get(credential_id) {
            self.cache_hits += 1;
            cached_result.clone()
        } else {
            self.cache_misses += 1;
            let result = self.oprf_client.get_evaluation(credential_id)
                .map_err(|e| MinimalError::Serialization(e.to_string()))?;
            
            // Cache for future use
            self.oprf_result_cache.insert(credential_id.to_string(), result.clone());
            result
        };
        
        // Check bloom filter
        let (is_revoked, _level) = self.revocation_filter.contains(&oprf_result.evaluation);
        Ok(!is_revoked)
    }
    
    /// Create verification message using pre-allocated buffer
    fn create_verification_message_buffered(&mut self, credential: &MinimalCredential) -> std::result::Result<(), MinimalError> {
        let mut hasher = Sha256::new();
        
        // Add credential fields in deterministic order
        hasher.update(credential.id.as_bytes());
        hasher.update(credential.issuer.as_bytes());
        hasher.update(credential.subject.as_bytes());
        hasher.update(credential.issued_at.to_le_bytes());
        
        if let Some(expires_at) = credential.expires_at {
            hasher.update(expires_at.to_le_bytes());
        }
        
        // Add claims in sorted order
        let mut claim_keys: Vec<_> = credential.claims.keys().collect();
        claim_keys.sort();
        
        for key in claim_keys {
            hasher.update(key.as_bytes());
            let value_str = serde_json::to_string(&credential.claims[key])
                .map_err(|e| MinimalError::Serialization(e.to_string()))?;
            hasher.update(value_str.as_bytes());
        }
        
        // Write directly to pre-allocated buffer
        self.message_buffer = hasher.finalize().to_vec();
        Ok(())
    }
    
    /// Batch verification for multiple credentials
    pub fn verify_batch(&mut self, credentials: &[MinimalCredential]) -> std::result::Result<Vec<OptimizedVerificationResult>, MinimalError> {
        let mut results = Vec::with_capacity(credentials.len());
        
        for credential in credentials {
            let result = self.verify_optimized(credential)?;
            results.push(result);
        }
        
        Ok(results)
    }
    
    /// Add credential to revocation list
    pub fn revoke_credential(&mut self, credential_id: &str) -> std::result::Result<(), MinimalError> {
        let oprf_result = self.oprf_client.get_evaluation(credential_id)
            .map_err(|e| MinimalError::Serialization(e.to_string()))?;
        
        self.revocation_filter.add(&oprf_result.evaluation)
            .map_err(|e| MinimalError::Serialization(e.to_string()))?;
        
        // Remove from OPRF cache to force re-evaluation
        self.oprf_result_cache.remove(credential_id);
        
        Ok(())
    }
    
    /// Get performance statistics
    pub fn get_performance_stats(&self) -> OptimizationStats {
        OptimizationStats {
            total_verifications: self.total_verifications,
            cache_hits: self.cache_hits,
            cache_misses: self.cache_misses,
            cache_hit_rate: if self.cache_hits + self.cache_misses > 0 {
                self.cache_hits as f64 / (self.cache_hits + self.cache_misses) as f64
            } else {
                0.0
            },
            public_key_cache_size: self.public_key_cache.len(),
            oprf_cache_size: self.oprf_result_cache.len(),
        }
    }
}

/// Optimized verification result with performance data
#[derive(Debug, Clone)]
pub struct OptimizedVerificationResult {
    pub verified: bool,
    pub signature_valid: bool,
    pub not_revoked: bool,
    pub issuer_did: String,
    pub verification_time_ns: u64,
    pub signature_time_ns: u64,
    pub revocation_time_ns: u64,
    pub confidence: f64,
    pub cache_hit: bool,
    pub optimization_used: bool,
}

/// Performance statistics for optimization analysis
#[derive(Debug, Clone)]
pub struct OptimizationStats {
    pub total_verifications: u64,
    pub cache_hits: u64,
    pub cache_misses: u64,
    pub cache_hit_rate: f64,
    pub public_key_cache_size: usize,
    pub oprf_cache_size: usize,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::minimal_core::MinimalIssuer;
    use std::collections::HashMap;
    
    #[test]
    fn test_optimization_performance() {
        let mut optimized_verifier = OptimizedVerifier::new().unwrap();
        
        // Create test credentials
        let issuer = MinimalIssuer::new();
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        
        let credential = issuer.issue_credential(
            "did:lemma:test_subject".to_string(),
            claims,
        ).unwrap();
        
        println!("🔍 Testing optimization performance...");
        
        // Test 1: First verification (cache miss)
        let result1 = optimized_verifier.verify_optimized(&credential).unwrap();
        println!("✅ First verification (cache miss): {:.3}μs", result1.verification_time_ns as f64 / 1000.0);
        
        // Test 2: Second verification (cache hit)
        let result2 = optimized_verifier.verify_optimized(&credential).unwrap();
        println!("✅ Second verification (cache hit): {:.3}μs", result2.verification_time_ns as f64 / 1000.0);
        
        // Test 3: Performance comparison
        let mut baseline_times = Vec::new();
        let mut optimized_times = Vec::new();
        
        // Baseline (no optimization)
        let mut baseline_verifier = CompleteVerifier::new().unwrap();
        for _ in 0..50 {
            let start = std::time::Instant::now();
            let _ = baseline_verifier.verify_complete(&credential).unwrap();
            baseline_times.push(start.elapsed().as_nanos() as u64);
        }
        
        // Optimized (with caching)
        for _ in 0..50 {
            let start = std::time::Instant::now();
            let _ = optimized_verifier.verify_optimized(&credential).unwrap();
            optimized_times.push(start.elapsed().as_nanos() as u64);
        }
        
        let baseline_avg = baseline_times.iter().sum::<u64>() as f64 / baseline_times.len() as f64;
        let optimized_avg = optimized_times.iter().sum::<u64>() as f64 / optimized_times.len() as f64;
        let speedup = baseline_avg / optimized_avg;
        
        println!("\n📊 Performance Comparison:");
        println!("   Baseline: {:.3}μs", baseline_avg / 1000.0);
        println!("   Optimized: {:.3}μs", optimized_avg / 1000.0);
        println!("   Speedup: {:.2}x faster", speedup);
        
        // Get cache statistics
        let stats = optimized_verifier.get_performance_stats();
        println!("\n📈 Cache Performance:");
        println!("   Hit rate: {:.1}%", stats.cache_hit_rate * 100.0);
        println!("   Public key cache: {} entries", stats.public_key_cache_size);
        println!("   OPRF cache: {} entries", stats.oprf_cache_size);
        
        assert!(speedup > 1.0, "Optimization should provide speedup");
        assert!(stats.cache_hit_rate > 0.5, "Cache hit rate should be >50%");
    }
}
