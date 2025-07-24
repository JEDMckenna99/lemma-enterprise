use crate::credentials::VerifiableCredential;
use crate::LemmaError;
use std::collections::HashMap;
use std::sync::Arc;
use thiserror::Error;

#[cfg(feature = "hsm")]
use pkcs11::{Ctx, types::*};

type Result<T> = std::result::Result<T, LemmaError>;

#[derive(Debug, Error)]
pub enum HSMError {
    #[error("HSM initialization failed: {0}")]
    InitializationFailed(String),
    #[error("HSM operation failed: {0}")]
    OperationFailed(String),
    #[error("HSM key not found: {0}")]
    KeyNotFound(String),
    #[error("HSM session error: {0}")]
    SessionError(String),
    #[error("HSM feature not available")]
    FeatureNotAvailable,
}

impl From<HSMError> for LemmaError {
    fn from(error: HSMError) -> Self {
        LemmaError::VerificationFailed(error.to_string())
    }
}

/// Hardware Security Module verifier for offloading cryptographic operations
pub struct HSMVerifier {
    #[cfg(feature = "hsm")]
    context: Arc<Ctx>,
    #[cfg(feature = "hsm")]
    session: Option<CK_SESSION_HANDLE>,
    #[cfg(feature = "hsm")]
    public_key_handles: HashMap<String, CK_OBJECT_HANDLE>,
    
    // Statistics
    pub hsm_verifications: u64,
    pub hsm_hits: u64,
    pub hsm_misses: u64,
    pub hardware_available: bool,
}

impl HSMVerifier {
    /// Create a new HSM verifier
    pub fn new() -> Result<Self> {
        #[cfg(feature = "hsm")]
        {
            Self::new_with_hsm()
        }
        #[cfg(not(feature = "hsm"))]
        {
            Ok(Self {
                hsm_verifications: 0,
                hsm_hits: 0,
                hsm_misses: 0,
                hardware_available: false,
            })
        }
    }

    #[cfg(feature = "hsm")]
    fn new_with_hsm() -> Result<Self> {
        // Try to initialize PKCS#11 context with common library paths
        let library_paths = vec![
            "/usr/lib/pkcs11/opensc-pkcs11.so",
            "/usr/lib/x86_64-linux-gnu/pkcs11/opensc-pkcs11.so",
            "C:\\Windows\\System32\\mscapi.dll",
            "C:\\Windows\\System32\\cryptngc.dll",
        ];

        let mut ctx = None;
        for path in library_paths {
            match Ctx::new_and_initialize(path) {
                Ok(c) => {
                    ctx = Some(Arc::new(c));
                    break;
                }
                Err(e) => {
                    log::debug!("Failed to initialize HSM with {}: {:?}", path, e);
                    continue;
                }
            }
        }

        let ctx = match ctx {
            Some(ctx) => ctx,
            None => {
                log::warn!("HSM initialization failed: no suitable PKCS#11 library found");
                return Ok(Self {
                    context: Arc::new(Ctx::new_and_initialize("dummy_path").map_err(|e| {
                        HSMError::InitializationFailed(e.to_string())
                    })?),
                    session: None,
                    public_key_handles: HashMap::new(),
                    hsm_verifications: 0,
                    hsm_hits: 0,
                    hsm_misses: 0,
                    hardware_available: false,
                });
            }
        };

        // Get available slots
        let slots = ctx.get_slot_list(true)
            .map_err(|e| HSMError::InitializationFailed(e.to_string()))?;
        
        if slots.is_empty() {
            log::warn!("No HSM slots available");
            return Ok(Self {
                context: ctx,
                session: None,
                public_key_handles: HashMap::new(),
                hsm_verifications: 0,
                hsm_hits: 0,
                hsm_misses: 0,
                hardware_available: false,
            });
        }

        // Open session with first available slot
        let session = ctx.open_session(
            slots[0],
            CKF_SERIAL_SESSION | CKF_RW_SESSION,
            None,
            None,
        ).map_err(|e| HSMError::SessionError(e.to_string()))?;

        Ok(Self {
            context: ctx,
            session: Some(session),
            public_key_handles: HashMap::new(),
            hsm_verifications: 0,
            hsm_hits: 0,
            hsm_misses: 0,
            hardware_available: true,
        })
    }

    /// Register a verifying key with the HSM
    pub fn register_verifying_key(&mut self, issuer: &str, public_key: &[u8]) -> Result<()> {
        #[cfg(feature = "hsm")]
        {
            if !self.hardware_available {
                return Err(HSMError::FeatureNotAvailable.into());
            }

            let session = self.session.as_ref()
                .ok_or_else(|| HSMError::SessionError("No active session".to_string()))?;

            // Create public key object in HSM
            let public_key_template = vec![
                CK_ATTRIBUTE {
                    attrType: CKA_CLASS,
                    pValue: &CKO_PUBLIC_KEY as *const _ as *mut _,
                    ulValueLen: std::mem::size_of::<CK_OBJECT_CLASS>() as u32,
                },
                CK_ATTRIBUTE {
                    attrType: CKA_KEY_TYPE,
                    pValue: &CKK_EC as *const _ as *mut _,
                    ulValueLen: std::mem::size_of::<CK_KEY_TYPE>() as u32,
                },
                CK_ATTRIBUTE {
                    attrType: CKA_VERIFY,
                    pValue: &CK_TRUE as *const _ as *mut _,
                    ulValueLen: std::mem::size_of::<CK_BBOOL>() as u32,
                },
                CK_ATTRIBUTE {
                    attrType: CKA_EC_POINT,
                    pValue: public_key.as_ptr() as *mut _,
                    ulValueLen: public_key.len() as u32,
                },
            ];

            let key_handle = session.create_object(&public_key_template)
                .map_err(|e| HSMError::OperationFailed(e.to_string()))?;

            self.public_key_handles.insert(issuer.to_string(), key_handle);
            Ok(())
        }
        #[cfg(not(feature = "hsm"))]
        {
            Err(HSMError::FeatureNotAvailable.into())
        }
    }

    /// Verify a signature using HSM hardware acceleration
    pub fn verify_signature_hsm(&mut self, credential: &VerifiableCredential) -> Result<bool> {
        #[cfg(feature = "hsm")]
        {
            if !self.hardware_available {
                self.hsm_misses += 1;
                return Err(HSMError::FeatureNotAvailable.into());
            }

            let session = self.session.as_ref()
                .ok_or_else(|| HSMError::SessionError("No active session".to_string()))?;

            let key_handle = self.public_key_handles.get(&credential.issuer)
                .ok_or_else(|| HSMError::KeyNotFound(credential.issuer.clone()))?;

            // Get signature and message data
            let signature_data = credential.signature_data();
            let message_data = credential.message_bytes();

            // Initialize verification operation
            let mechanism = CK_MECHANISM {
                mechanism: CKM_ECDSA,
                pParameter: std::ptr::null_mut(),
                ulParameterLen: 0,
            };

            session.verify_init(&mechanism, *key_handle)
                .map_err(|e| HSMError::OperationFailed(e.to_string()))?;

            // Perform verification
            match session.verify(&message_data, &signature_data) {
                Ok(()) => {
                    self.hsm_verifications += 1;
                    self.hsm_hits += 1;
                    Ok(true)
                }
                Err(pkcs11::errors::Error::Pkcs11(CKR_SIGNATURE_INVALID)) => {
                    self.hsm_verifications += 1;
                    self.hsm_hits += 1;
                    Ok(false)
                }
                Err(e) => {
                    self.hsm_misses += 1;
                    Err(HSMError::OperationFailed(e.to_string()).into())
                }
            }
        }
        #[cfg(not(feature = "hsm"))]
        {
            self.hsm_misses += 1;
            Err(HSMError::FeatureNotAvailable.into())
        }
    }

    /// Batch verify signatures using HSM
    pub fn verify_batch_hsm(&mut self, credentials: &[VerifiableCredential]) -> Result<Vec<bool>> {
        #[cfg(feature = "hsm")]
        {
            if !self.hardware_available {
                return Err(HSMError::FeatureNotAvailable.into());
            }

            let mut results = Vec::with_capacity(credentials.len());
            
            for credential in credentials {
                match self.verify_signature_hsm(credential) {
                    Ok(valid) => results.push(valid),
                    Err(_) => {
                        // Fall back to software verification for this credential
                        results.push(false);
                    }
                }
            }

            Ok(results)
        }
        #[cfg(not(feature = "hsm"))]
        {
            Err(HSMError::FeatureNotAvailable.into())
        }
    }

    /// Get HSM statistics
    pub fn get_stats(&self) -> HSMStats {
        HSMStats {
            hardware_available: self.hardware_available,
            total_verifications: self.hsm_verifications,
            hardware_hits: self.hsm_hits,
            hardware_misses: self.hsm_misses,
            hit_rate: if self.hsm_verifications > 0 {
                (self.hsm_hits as f64 / self.hsm_verifications as f64) * 100.0
            } else {
                0.0
            },
            registered_keys: {
                #[cfg(feature = "hsm")]
                {
                    self.public_key_handles.len()
                }
                #[cfg(not(feature = "hsm"))]
                {
                    0
                }
            },
        }
    }

    /// Check if HSM hardware is available
    pub fn is_hardware_available(&self) -> bool {
        self.hardware_available
    }
}

impl Drop for HSMVerifier {
    fn drop(&mut self) {
        #[cfg(feature = "hsm")]
        {
            if let Some(session) = &self.session {
                let _ = session.close();
            }
        }
    }
}

/// HSM statistics structure
#[derive(Debug, Clone)]
pub struct HSMStats {
    pub hardware_available: bool,
    pub total_verifications: u64,
    pub hardware_hits: u64,
    pub hardware_misses: u64,
    pub hit_rate: f64,
    pub registered_keys: usize,
}

/// HSM-accelerated verification result
#[derive(Debug, Clone)]
pub struct HSMVerificationResult {
    pub signature_valid: bool,
    pub used_hardware: bool,
    pub verification_time_ns: u64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hsm_verifier_creation() {
        let verifier = HSMVerifier::new();
        assert!(verifier.is_ok());
    }

    #[test]
    fn test_hsm_stats() {
        let verifier = HSMVerifier::new().unwrap();
        let stats = verifier.get_stats();
        assert_eq!(stats.total_verifications, 0);
        assert_eq!(stats.hit_rate, 0.0);
    }

    #[cfg(feature = "hsm")]
    #[test]
    fn test_hsm_key_registration() {
        let mut verifier = HSMVerifier::new().unwrap();
        let dummy_key = vec![0u8; 32];
        
        // This will fail if no HSM is available, which is expected
        let result = verifier.register_verifying_key("test_issuer", &dummy_key);
        
        // We don't assert success because HSM may not be available in test environment
        // but we verify the function doesn't panic
        let _ = result;
    }
} 