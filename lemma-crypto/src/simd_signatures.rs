//! SIMD-optimized signature verification
//! 
//! This module implements batched Ed25519 signature verification using SIMD instructions
//! for significant performance improvements as described in the optimization guide.

use ed25519_dalek::{
    Signature, VerifyingKey, Verifier, verify_batch,
};
use std::collections::HashMap;
use serde::{Deserialize, Serialize};

use crate::{
    credentials::VerifiableCredential,
    Result, LemmaError,
};

/// SIMD-optimized signature verifier
pub struct SIMDVerifier {
    verifying_keys: HashMap<String, VerifyingKey>,
    // Batch size for optimal SIMD performance
    batch_size: usize,
    // Pre-allocated buffers for batch operations
    signature_buffer: Vec<Signature>,
    message_buffer: Vec<Vec<u8>>,
    key_buffer: Vec<VerifyingKey>,
    result_buffer: Vec<bool>,
}

impl SIMDVerifier {
    /// Create a new SIMD verifier with optimal batch size
    pub fn new() -> Self {
        const OPTIMAL_BATCH_SIZE: usize = 8; // Process 8 signatures at once for AVX2
        
        Self {
            verifying_keys: HashMap::new(),
            batch_size: OPTIMAL_BATCH_SIZE,
            signature_buffer: Vec::with_capacity(OPTIMAL_BATCH_SIZE),
            message_buffer: Vec::with_capacity(OPTIMAL_BATCH_SIZE),
            key_buffer: Vec::with_capacity(OPTIMAL_BATCH_SIZE),
            result_buffer: Vec::with_capacity(OPTIMAL_BATCH_SIZE),
        }
    }
    
    /// Add a verifying key for an issuer
    pub fn add_verifying_key(&mut self, issuer: String, key: VerifyingKey) {
        self.verifying_keys.insert(issuer, key);
    }
    
    /// Verify a single signature (fallback for non-batch operations)
    pub fn verify_single(&self, 
        credential: &VerifiableCredential
    ) -> Result<bool> {
        // Get the verification key
        let key = self.verifying_keys.get(&credential.issuer)
            .ok_or_else(|| LemmaError::VerificationFailed(
                format!("No verifying key for issuer: {}", credential.issuer)
            ))?;
        
        // Get the signature from the credential
        let proof = credential.proof.as_ref()
            .ok_or_else(|| LemmaError::VerificationFailed("No proof found".to_string()))?;
        
        let signature = Signature::from_slice(&hex::decode(&proof.signature_value)
            .map_err(|e| LemmaError::VerificationFailed(format!("Invalid signature hex: {}", e)))?)
            .map_err(|e| LemmaError::VerificationFailed(format!("Invalid signature: {}", e)))?;
        
        // Create the message to verify
        let message = credential.create_verification_message()
            .map_err(|e| LemmaError::Credential(e.to_string()))?;
        
        // Verify the signature
        match key.verify(&message, &signature) {
            Ok(()) => Ok(true),
            Err(_) => Ok(false),
        }
    }
    
    /// Verify multiple signatures in batch using SIMD instructions
    pub fn verify_batch(&mut self, 
        credentials: &[VerifiableCredential]
    ) -> Result<Vec<bool>> {
        if credentials.is_empty() {
            return Ok(Vec::new());
        }
        
        let mut results = Vec::with_capacity(credentials.len());
        
        // Process in chunks of batch_size for optimal SIMD performance
        for chunk in credentials.chunks(self.batch_size) {
            let chunk_results = self.verify_batch_chunk(chunk)?;
            results.extend(chunk_results);
        }
        
        Ok(results)
    }
    
    /// Verify a chunk of signatures using SIMD instructions
    fn verify_batch_chunk(&mut self, 
        credentials: &[VerifiableCredential]
    ) -> Result<Vec<bool>> {
        // Clear buffers
        self.signature_buffer.clear();
        self.message_buffer.clear();
        self.key_buffer.clear();
        self.result_buffer.clear();
        
        // Prepare batch data
        for credential in credentials {
            // Get the verification key
            let key = self.verifying_keys.get(&credential.issuer)
                .ok_or_else(|| LemmaError::VerificationFailed(
                    format!("No verifying key for issuer: {}", credential.issuer)
                ))?;
            
            // Get the signature from the credential
            let proof = credential.proof.as_ref()
                .ok_or_else(|| LemmaError::VerificationFailed("No proof found".to_string()))?;
            
            let signature = Signature::from_slice(&hex::decode(&proof.signature_value)
                .map_err(|e| LemmaError::VerificationFailed(format!("Invalid signature hex: {}", e)))?)
                .map_err(|e| LemmaError::VerificationFailed(format!("Invalid signature: {}", e)))?;
            
            // Create the message to verify
            let message = credential.create_verification_message()
                .map_err(|e| LemmaError::Credential(e.to_string()))?;
            
            // Add to batch buffers
            self.signature_buffer.push(signature);
            self.message_buffer.push(message);
            self.key_buffer.push(*key);
        }
        
        // Perform batch verification using SIMD instructions
        let batch_result = self.verify_batch_simd();
        
        Ok(batch_result)
    }
    
    /// Perform SIMD batch verification
    fn verify_batch_simd(&self) -> Vec<bool> {
        if self.signature_buffer.is_empty() {
            return Vec::new();
        }
        
        // Prepare data for batch verification
        let messages: Vec<&[u8]> = self.message_buffer.iter().map(|m| m.as_slice()).collect();
        let signatures: &[Signature] = &self.signature_buffer;
        let keys: &[VerifyingKey] = &self.key_buffer;
        
        // Use ed25519-dalek's batch verification with SIMD
        // This leverages AVX2/AVX-512 instructions when available
        match verify_batch(&messages, signatures, keys) {
            Ok(()) => {
                // All signatures valid
                vec![true; signatures.len()]
            }
            Err(_) => {
                // At least one signature invalid - fall back to individual verification
                self.fallback_individual_verification()
            }
        }
    }
    
    /// Fallback to individual verification when batch fails
    fn fallback_individual_verification(&self) -> Vec<bool> {
        let mut results = Vec::with_capacity(self.signature_buffer.len());
        
        for i in 0..self.signature_buffer.len() {
            let result = self.key_buffer[i].verify(
                &self.message_buffer[i],
                &self.signature_buffer[i]
            );
            results.push(result.is_ok());
        }
        
        results
    }
    
    /// Get performance statistics
    pub fn get_stats(&self) -> SIMDVerifierStats {
        SIMDVerifierStats {
            batch_size: self.batch_size,
            keys_count: self.verifying_keys.len(),
            buffer_capacity: self.signature_buffer.capacity(),
        }
    }
}

/// SIMD verifier statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SIMDVerifierStats {
    pub batch_size: usize,
    pub keys_count: usize,
    pub buffer_capacity: usize,
}

/// Convenience function for batch signature verification
pub fn verify_signatures_batch(
    credentials: &[VerifiableCredential],
    verifying_keys: &HashMap<String, VerifyingKey>,
) -> Result<Vec<bool>> {
    let mut verifier = SIMDVerifier::new();
    
    // Add all verifying keys
    for (issuer, key) in verifying_keys {
        verifier.add_verifying_key(issuer.clone(), *key);
    }
    
    // Verify batch
    verifier.verify_batch(credentials)
}

/// Optimized signature verification for the core verification engine
pub fn verify_credential_signatures_optimized(
    credentials: &[VerifiableCredential],
    verifying_keys: &HashMap<String, VerifyingKey>,
) -> Result<Vec<bool>> {
    if credentials.len() >= 4 {
        // Use batch verification for 4+ credentials
        verify_signatures_batch(credentials, verifying_keys)
    } else {
        // Use individual verification for small batches
        let mut results = Vec::with_capacity(credentials.len());
        let mut verifier = SIMDVerifier::new();
        
        for (issuer, key) in verifying_keys {
            verifier.add_verifying_key(issuer.clone(), *key);
        }
        
        for credential in credentials {
            let result = verifier.verify_single(credential)?;
            results.push(result);
        }
        
        Ok(results)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::SigningKey;
    use rand::rngs::OsRng;
    
    #[test]
    fn test_simd_batch_verification() {
        let mut verifier = SIMDVerifier::new();
        
        // Generate test key
        let signing_key = SigningKey::generate(&mut OsRng);
        let verifying_key = signing_key.verifying_key();
        
        verifier.add_verifying_key("test_issuer".to_string(), verifying_key);
        
        // TODO: Add test credentials and verify batch operation
        // This would require creating valid test credentials
        assert_eq!(verifier.batch_size, 8);
    }
    
    #[test]
    fn test_simd_verifier_stats() {
        let verifier = SIMDVerifier::new();
        let stats = verifier.get_stats();
        
        assert_eq!(stats.batch_size, 8);
        assert_eq!(stats.keys_count, 0);
        assert_eq!(stats.buffer_capacity, 8);
    }
} 