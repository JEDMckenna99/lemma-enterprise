//! Lemma Crypto Library - Clean Working Implementation
//! 
//! Provides real cryptographic verification with Ed25519 signatures,
//! OPRF privacy-preserving revocation, and ZKP claims.

use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use thiserror::Error;

// WORKING CORE MODULES
pub mod minimal_core;
pub mod complete_verification;
pub mod zkp_claims;

// PERFORMANCE OPTIMIZATIONS
pub mod optimized_verification;
// pub mod encrypted_browser_wallet;  // Skip for now - AES-GCM version issue

// WORKING CRYPTO PRIMITIVES
pub mod constants;
pub mod oprf;
pub mod bloom;
pub mod utils;

// WORKING INTEGRATIONS (WASM removed for clean build)

// Minimal Python bindings (only if Python feature enabled)
#[cfg(feature = "python")]
pub mod minimal_python;

// Re-export WORKING types
pub use crate::minimal_core::{MinimalIssuer, MinimalCore, MinimalCredential, MinimalVerificationResult, MinimalError};
pub use crate::complete_verification::{CompleteVerifier, CompleteVerificationResult};
pub use crate::zkp_claims::{ZKPCredential, ZKPClaimType, ZKPClaimProof, ZKPVerifier};
pub use crate::optimized_verification::{OptimizedVerifier, OptimizedVerificationResult, OptimizationStats};
// pub use crate::encrypted_browser_wallet::{EncryptedBrowserWallet, EncryptedCredentialEntry, EncryptionConfig, WalletStats, CredentialMetadata};
pub use crate::oprf::{OPRFClient, OPRFServer, OPRFResult};
pub use crate::bloom::{CascadedBloomFilter};
pub use crate::utils::{bytes_to_hex, hex_to_bytes, current_timestamp};
pub use crate::constants::*;

/// Main error type for the library
#[derive(Error, Debug, Clone)]
pub enum LemmaError {
    #[error("OPRF error: {0}")]
    OPRF(String),
    #[error("Bloom filter error: {0}")]
    Bloom(String),
    #[error("Minimal error: {0}")]
    Minimal(String),
    #[error("Serialization error: {0}")]
    Serialization(String),
    #[error("Crypto error: {0}")]
    Crypto(String),
    #[error("ZKP error: {0}")]
    ZKP(String),
}

// Error conversions
impl From<oprf::OPRFError> for LemmaError {
    fn from(err: oprf::OPRFError) -> Self {
        LemmaError::OPRF(err.to_string())
    }
}

impl From<bloom::BloomError> for LemmaError {
    fn from(err: bloom::BloomError) -> Self {
        LemmaError::Bloom(err.to_string())
    }
}

impl From<MinimalError> for LemmaError {
    fn from(err: MinimalError) -> Self {
        LemmaError::Minimal(err.to_string())
    }
}

impl From<ed25519_dalek::ed25519::Error> for LemmaError {
    fn from(err: ed25519_dalek::ed25519::Error) -> Self {
        LemmaError::Crypto(format!("Ed25519 error: {}", err))
    }
}

impl From<std::io::Error> for LemmaError {
    fn from(err: std::io::Error) -> Self {
        LemmaError::Crypto(format!("IO error: {}", err))
    }
}

/// Type alias for Results in this crate
pub type Result<T> = std::result::Result<T, LemmaError>;

/// Library metadata
pub const VERSION: &str = env!("CARGO_PKG_VERSION");
pub const NAME: &str = env!("CARGO_PKG_NAME");

/// Get library information
pub fn library_info() -> HashMap<String, String> {
    let mut info = HashMap::new();
    info.insert("name".to_string(), NAME.to_string());
    info.insert("version".to_string(), VERSION.to_string());
    info.insert("features".to_string(), "ed25519,oprf,bloom,zkp".to_string());
    info.insert("status".to_string(), "working".to_string());
    info
} 