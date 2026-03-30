//! Python bindings for Lemma Crypto
//! 
//! Provides Python interface to cryptographic functionality

use pyo3::prelude::*;
use pyo3::exceptions::PyRuntimeError;
use crate::oprf_key_manager::{OPRFKeyManager, KeyType, KeyStatus};
use crate::minimal_core::{MinimalIssuer, MinimalVerifier};
use crate::optimized_verification::OptimizedVerifier;
use crate::Result as LemmaResult;

/// Python wrapper for MinimalIssuer
#[pyclass]
pub struct PyMinimalIssuer {
    issuer: MinimalIssuer,
}

#[pymethods]
impl PyMinimalIssuer {
    #[new]
    pub fn new() -> Self {
        Self {
            issuer: MinimalIssuer::new(),
        }
    }
    
    /// Create issuer from seed (for KMS-backed keys)
    #[staticmethod]
    pub fn from_seed(seed: Vec<u8>) -> PyResult<Self> {
        if seed.len() != 32 {
            return Err(PyRuntimeError::new_err("Seed must be exactly 32 bytes"));
        }
        let mut seed_array = [0u8; 32];
        seed_array.copy_from_slice(&seed);
        Ok(Self {
            issuer: MinimalIssuer::from_seed(&seed_array),
        })
    }
    
    /// Get DID
    pub fn get_did(&self) -> String {
        self.issuer.did().to_string()
    }
    
    /// Get public key hex
    pub fn get_public_key_hex(&self) -> String {
        self.issuer.public_key_hex()
    }
    
    /// Get signing key bytes (for KMS encryption) - Python-friendly name
    pub fn get_signing_key_bytes(&self) -> Vec<u8> {
        self.issuer.signing_key_bytes().to_vec()
    }
    
    /// Get signing key bytes (for KMS encryption) - Rust-style name
    pub fn signing_key_bytes(&self) -> Vec<u8> {
        self.issuer.signing_key_bytes().to_vec()
    }
    
    /// Issue credential (takes subject DID and claims dict)
    pub fn issue_credential(&self, subject: &str, claims: std::collections::HashMap<String, String>) -> PyResult<String> {
        use std::collections::HashMap;
        use serde_json::Value;
        
        // Convert HashMap<String, String> to HashMap<String, Value>
        let claims_json: HashMap<String, Value> = claims.into_iter()
            .map(|(k, v)| (k, Value::String(v)))
            .collect();
        
        // Issue credential
        let credential = self.issuer
            .issue_credential(subject.to_string(), claims_json)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
        
        // Serialize credential to JSON
        serde_json::to_string(&credential)
            .map_err(|e| PyRuntimeError::new_err(format!("Serialization error: {}", e)))
    }
    
    /// Issue credential (simplified: takes subject and claims as JSON)
    pub fn issue_credential_simple(&self, subject: &str, claims_json: &str) -> PyResult<String> {
        use std::collections::HashMap;
        use serde_json::Value;
        
        // Parse claims from JSON
        let claims: HashMap<String, Value> = serde_json::from_str(claims_json)
            .map_err(|e| PyRuntimeError::new_err(format!("Invalid claims JSON: {}", e)))?;
        
        // Issue credential
        let credential = self.issuer
            .issue_credential(subject.to_string(), claims)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
        
        // Serialize credential to JSON
        serde_json::to_string(&credential)
            .map_err(|e| PyRuntimeError::new_err(format!("Serialization error: {}", e)))
    }
}

/// Python wrapper for MinimalVerifier
#[pyclass]
pub struct PyMinimalVerifier {
    verifier: MinimalVerifier,
}

#[pymethods]
impl PyMinimalVerifier {
    #[new]
    pub fn new() -> Self {
        Self {
            verifier: MinimalVerifier::new(),
        }
    }
    
    /// Verify credential from JSON
    pub fn verify_credential_json(&self, credential_json: &str) -> PyResult<bool> {
        use crate::minimal_core::MinimalCredential;
        
        // Parse credential from JSON
        let credential: MinimalCredential = serde_json::from_str(credential_json)
            .map_err(|e| PyRuntimeError::new_err(format!("Invalid credential JSON: {}", e)))?;
        
        // Verify
        self.verifier
            .verify(&credential)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    }
}

/// Python wrapper for OptimizedVerifier
#[pyclass]
pub struct PyOptimizedVerifier {
    verifier: OptimizedVerifier,
}

#[pymethods]
impl PyOptimizedVerifier {
    #[new]
    pub fn new() -> PyResult<Self> {
        let verifier = OptimizedVerifier::new()
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
        Ok(Self { verifier })
    }
    
    /// Verify credential from JSON (optimized with OPRF + Bloom filter)
    pub fn verify_credential_json(&mut self, credential_json: &str) -> PyResult<bool> {
        use crate::minimal_core::MinimalCredential;
        
        // Parse credential from JSON
        let credential: MinimalCredential = serde_json::from_str(credential_json)
            .map_err(|e| PyRuntimeError::new_err(format!("Invalid credential JSON: {}", e)))?;
        
        // Verify using optimized verifier (includes OPRF + Bloom revocation check)
        let result = self.verifier.verify_optimized(&credential)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
        
        Ok(result.verified)
    }
    
    /// Add revoked credential ID to Bloom filter (via OPRF)
    pub fn revoke_credential(&mut self, credential_id: &str) -> PyResult<()> {
        self.verifier.add_revocation(credential_id)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    }
    
    /// Check if credential is revoked (OPRF + Bloom filter)
    pub fn is_revoked(&mut self, credential_id: &str) -> PyResult<bool> {
        self.verifier.check_revocation_status(credential_id)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    }
    
    /// Get verification statistics
    pub fn get_stats(&self) -> PyResult<pyo3::Py<pyo3::types::PyDict>> {
        let stats = self.verifier.get_stats();
        Python::with_gil(|py| {
            let dict = pyo3::types::PyDict::new(py);
            dict.set_item("total_verifications", stats.total_verifications)?;
            dict.set_item("cache_hits", stats.cache_hits)?;
            dict.set_item("cache_misses", stats.cache_misses)?;
            dict.set_item("cache_hit_rate", stats.cache_hit_rate)?;
            dict.set_item("public_key_cache_size", stats.public_key_cache_size)?;
            dict.set_item("oprf_cache_size", stats.oprf_cache_size)?;
            Ok(dict.into())
        })
    }
}

/// Python wrapper for OPRF Key Manager
#[pyclass]
pub struct PyOPRFKeyManager {
    manager: OPRFKeyManager,
}

#[pymethods]
impl PyOPRFKeyManager {
    #[new]
    pub fn new(key_type: String) -> PyResult<Self> {
        let kt = match key_type.as_str() {
            "network" => KeyType::Network,
            site_id => KeyType::Site(site_id.to_string()),
        };
        
        Ok(Self {
            manager: OPRFKeyManager::new(kt),
        })
    }
    
    /// Generate a new key version
    pub fn generate_new_version(&mut self) -> PyResult<u32> {
        self.manager
            .generate_new_version()
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    }
    
    /// Activate a key version (initiate rotation)
    pub fn activate_key(&mut self, version: u32) -> PyResult<pyo3::Py<pyo3::types::PyDict>> {
        let plan = self.manager
            .activate_key(version)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
        
        Python::with_gil(|py| {
            let dict = pyo3::types::PyDict::new(py);
            dict.set_item("old_version", plan.old_version)?;
            dict.set_item("new_version", plan.new_version)?;
            dict.set_item("grace_period_days", plan.grace_period_days)?;
            dict.set_item("estimated_completion", plan.estimated_completion)?;
            Ok(dict.into())
        })
    }
    
    /// Get active key version
    pub fn get_active_version(&self) -> u32 {
        self.manager.get_active_version()
    }
    
    /// Get supported versions for verification
    pub fn get_supported_versions(&self) -> Vec<u32> {
        self.manager.get_supported_versions()
    }
    
    /// Revoke a key
    pub fn revoke_key(&mut self, version: u32, reason: String) -> PyResult<()> {
        self.manager
            .revoke_key(version, &reason)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    }
    
    /// Get key for verification
    pub fn get_key_for_verification(&self, version: u32) -> PyResult<Vec<u8>> {
        let key = self.manager
            .get_key_for_verification(version)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
        Ok(key.to_vec())
    }
    
    /// Get active key for signing
    pub fn get_active_key(&self) -> PyResult<Vec<u8>> {
        let key = self.manager
            .get_active_key()
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
        Ok(key.to_vec())
    }
}

/// Register Python module
/// Python wrapper for OPRF Server (for server-side evaluation)
#[pyclass]
pub struct PyOPRFServer {
    server: crate::oprf::OPRFServer,
}

#[pymethods]
impl PyOPRFServer {
    #[new]
    pub fn new() -> Self {
        Self {
            server: crate::oprf::OPRFServer::new(),
        }
    }
    
    /// Evaluate OPRF on a blinded point (server-side)
    pub fn evaluate(&self, blinded_hex: String) -> PyResult<String> {
        use curve25519_dalek::ristretto::CompressedRistretto;
        
        let blinded_bytes = hex::decode(&blinded_hex)
            .map_err(|e| PyRuntimeError::new_err(format!("Invalid hex: {}", e)))?;
        
        // Parse blinded point from bytes
        if blinded_bytes.len() != 32 {
            return Err(PyRuntimeError::new_err("Blinded point must be 32 bytes"));
        }
        
        let mut point_bytes = [0u8; 32];
        point_bytes.copy_from_slice(&blinded_bytes);
        
        let compressed = CompressedRistretto(point_bytes);
        let blinded_point = compressed.decompress()
            .ok_or_else(|| PyRuntimeError::new_err("Invalid blinded point"))?;
        
        // Evaluate OPRF
        let evaluated_point = self.server.evaluate(&blinded_point);
        
        // Return as hex
        Ok(hex::encode(&evaluated_point.compress().to_bytes()))
    }
    
    /// Batch evaluate multiple blinded points
    pub fn batch_evaluate(&self, blinded_hex_list: Vec<String>) -> PyResult<Vec<String>> {
        use curve25519_dalek::ristretto::CompressedRistretto;
        
        blinded_hex_list.iter().map(|blinded_hex| {
            let blinded_bytes = hex::decode(blinded_hex)
                .map_err(|e| PyRuntimeError::new_err(format!("Invalid hex: {}", e)))?;
            
            if blinded_bytes.len() != 32 {
                return Err(PyRuntimeError::new_err("Blinded point must be 32 bytes"));
            }
            
            let mut point_bytes = [0u8; 32];
            point_bytes.copy_from_slice(&blinded_bytes);
            
            let compressed = CompressedRistretto(point_bytes);
            let blinded_point = compressed.decompress()
                .ok_or_else(|| PyRuntimeError::new_err("Invalid blinded point"))?;
            
            let evaluated_point = self.server.evaluate(&blinded_point);
            Ok(hex::encode(&evaluated_point.compress().to_bytes()))
        }).collect()
    }
}

/// Python wrapper for Cascaded Bloom Filter
#[pyclass]
pub struct PyCascadedBloomFilter {
    filter: crate::bloom::CascadedBloomFilter,
}

#[pymethods]
impl PyCascadedBloomFilter {
    #[new]
    pub fn new(levels: usize, base_capacity: usize, base_error: f64) -> PyResult<Self> {
        let filter = crate::bloom::CascadedBloomFilter::new(levels, base_capacity, base_error)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to create Bloom filter: {}", e)))?;
        
        Ok(Self { filter })
    }
    
    /// Add item to Bloom filter
    pub fn add(&mut self, item: Vec<u8>) -> PyResult<()> {
        self.filter.add(&item)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to add item: {}", e)))
    }
    
    /// Check if item is in Bloom filter
    pub fn contains(&self, item: Vec<u8>) -> bool {
        let (found, _level) = self.filter.contains(&item);
        found
    }
    
    /// Serialize to bytes
    pub fn to_bytes(&self) -> PyResult<Vec<u8>> {
        self.filter.to_bytes()
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to serialize: {}", e)))
    }
    
    /// Deserialize from bytes
    #[staticmethod]
    pub fn from_bytes(bytes: Vec<u8>) -> PyResult<Self> {
        let filter = crate::bloom::CascadedBloomFilter::from_bytes(&bytes)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to deserialize: {}", e)))?;
        
        Ok(Self { filter })
    }
}

// Helper module for hex encoding
mod hex {
    pub fn encode(bytes: &[u8]) -> String {
        bytes.iter().map(|b| format!("{:02x}", b)).collect()
    }
    
    pub fn decode(s: &str) -> Result<Vec<u8>, String> {
        if s.len() % 2 != 0 {
            return Err("Hex string must have even length".to_string());
        }
        
        (0..s.len())
            .step_by(2)
            .map(|i| {
                u8::from_str_radix(&s[i..i + 2], 16)
                    .map_err(|e| format!("Invalid hex: {}", e))
            })
            .collect()
    }
}

#[pymodule]
fn lemma_crypto(_py: Python, m: &PyModule) -> PyResult<()> {
    // Core classes
    m.add_class::<PyMinimalIssuer>()?;
    m.add_class::<PyMinimalVerifier>()?;
    m.add_class::<PyOptimizedVerifier>()?;
    
    // OPRF Key Management
    m.add_class::<PyOPRFKeyManager>()?;
    
    // OPRF Server & Bloom Filter (for WASM integration)
    m.add_class::<PyOPRFServer>()?;
    m.add_class::<PyCascadedBloomFilter>()?;
    
    Ok(())
}
