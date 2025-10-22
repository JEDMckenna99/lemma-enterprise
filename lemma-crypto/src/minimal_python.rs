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
        self.issuer.get_did()
    }
    
    /// Get public key hex
    pub fn get_public_key_hex(&self) -> String {
        self.issuer.get_public_key_hex()
    }
    
    /// Get signing key bytes (for KMS encryption)
    pub fn signing_key_bytes(&self) -> Vec<u8> {
        self.issuer.signing_key_bytes().to_vec()
    }
    
    /// Issue credential
    pub fn issue_credential(&self, credential_json: &str) -> PyResult<String> {
        self.issuer
            .issue_credential(credential_json)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    }
}

/// Python wrapper for MinimalVerifier
#[pyclass]
pub struct PyMinimalVerifier {
    verifier: MinimalVerifier,
}

#[pymethods]
impl PyMinimalVerifier {
    /// Create verifier from public key hex
    #[staticmethod]
    pub fn from_public_key_hex(public_key_hex: &str) -> PyResult<Self> {
        let verifier = MinimalVerifier::from_public_key_hex(public_key_hex)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
        Ok(Self { verifier })
    }
    
    /// Verify credential
    pub fn verify_credential(&self, credential_json: &str, signature_hex: &str) -> PyResult<bool> {
        self.verifier
            .verify_credential(credential_json, signature_hex)
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
    pub fn new() -> Self {
        Self {
            verifier: OptimizedVerifier::new(),
        }
    }
    
    /// Verify credential (optimized)
    pub fn verify(&self, credential_json: &str, signature_hex: &str, public_key_hex: &str) -> PyResult<bool> {
        let result = self.verifier
            .verify(credential_json, signature_hex, public_key_hex);
        Ok(result.verified)
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
#[pymodule]
fn lemma_crypto(_py: Python, m: &PyModule) -> PyResult<()> {
    // Core classes
    m.add_class::<PyMinimalIssuer>()?;
    m.add_class::<PyMinimalVerifier>()?;
    m.add_class::<PyOptimizedVerifier>()?;
    
    // OPRF Key Management
    m.add_class::<PyOPRFKeyManager>()?;
    
    Ok(())
}
