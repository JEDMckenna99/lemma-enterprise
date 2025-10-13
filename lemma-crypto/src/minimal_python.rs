//! Minimal Python bindings for OPRF Key Manager
//! 
//! Provides Python interface to key management functionality

use pyo3::prelude::*;
use pyo3::exceptions::PyRuntimeError;
use crate::oprf_key_manager::{OPRFKeyManager, KeyType, KeyStatus};
use crate::Result as LemmaResult;

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
fn oprf_key_management(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<PyOPRFKeyManager>()?;
    Ok(())
}
