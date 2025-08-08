//! Lemma Crypto Library - Universal Offline Verification Engine
//! 
//! This library provides privacy-preserving verification using OPRF-Cascaded Bloom Filters
//! with a pluggable micro-package architecture for different use cases.

use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use thiserror::Error;

// Re-export core modules
pub mod constants;
pub mod bloom;
pub mod oprf;
pub mod core;
pub mod credentials;
pub mod packages;
pub mod utils;
pub mod simd_signatures;
#[cfg(not(target_arch = "wasm32"))]
pub mod zero_copy;
pub mod precomputation;
pub mod hsm;
pub mod gpu;
pub mod predictive_cache;
#[cfg(not(target_arch = "wasm32"))]
pub mod work_stealing;
pub mod probabilistic_verification;

// Phase 4 Specialized Hardware
pub mod asic;
pub mod fpga;
pub mod quantum_resistant;
pub mod distributed;

// NEW: ZKP Integration for privacy-preserving claims (not available in WebAssembly)
#[cfg(not(target_arch = "wasm32"))]
pub mod zkp_claims;

// NEW: Background Wallet for microsecond credential storage
pub mod wallet;

// NEW: True federated/decentralized credentials
pub mod federated_credentials;
pub mod decentralized_revocation;

// Re-export commonly used types
pub use crate::oprf::{OPRFClient, OPRFServer, OPRFResult, RealisticOPRFClient};
pub use crate::bloom::{BloomFilter, CascadedBloomFilter};
pub use crate::credentials::{VerifiableCredential, CredentialIssuer, Ed25519PublicKey, Ed25519PrivateKey};
pub use crate::core::{LemmaCore, VerificationResult};
pub use crate::packages::{VerificationPackage, IdentityPackage, TicketPackage, PackageAuthenticityPackage};
#[cfg(not(target_arch = "wasm32"))]
pub use crate::zkp_claims::{ZKPClaim, ZKPClaimProof, ZKPClaimType, ZKPCredential, ZKPVerifier};
pub use crate::wallet::{BackgroundWallet, WalletConfig, WalletStats, WalletStorage, PrivacyLevel};

/// Main error type for the library
#[derive(Error, Debug, Clone)]
pub enum LemmaError {
    #[error("OPRF error: {0}")]
    OPRF(String),
    #[error("Bloom filter error: {0}")]
    Bloom(String),
    #[error("Credential error: {0}")]
    Credential(String),
    #[error("Package error: {0}")]
    Package(String),
    #[error("Unsupported package type: {0}")]
    UnsupportedPackageType(String),
    #[error("Verification failed: {0}")]
    VerificationFailed(String),
    #[error("Invalid configuration: {0}")]
    InvalidConfiguration(String),
    #[error("Serialization error: {0}")]
    Serialization(String),
    #[error("Crypto error: {0}")]
    Crypto(String),
    #[error("ZKP error: {0}")]
    ZKP(String),
}

// Implement From traits for error conversion
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

impl From<credentials::CredentialError> for LemmaError {
    fn from(err: credentials::CredentialError) -> Self {
        LemmaError::Credential(err.to_string())
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

/// Type alias for Results
pub type Result<T> = std::result::Result<T, LemmaError>;

/// Claim set for credentials
pub type ClaimSet = HashMap<String, serde_json::Value>;

/// Metadata for verification results
pub type VerificationMetadata = HashMap<String, serde_json::Value>;

#[cfg(feature = "python")]
pub mod python;

#[cfg(feature = "wasm")]
pub mod wasm;

#[cfg(feature = "wasm")]
pub use wasm::*;

#[cfg(test)]
mod stress_tests {
    use super::*;
    use std::sync::{Arc, Mutex};
    use std::thread;
    use std::time::{Duration, Instant};
    
    #[test]
    fn realistic_concurrent_verification_stress_test() {
        let num_threads = 10;
        let verifications_per_thread = 1000;
        let total_verifications = num_threads * verifications_per_thread;
        
        // Create shared components
        let oprf_client = Arc::new(Mutex::new(OPRFClient::new_with_server_key([1u8; 32])));
        let bloom_filter = Arc::new(Mutex::new(CascadedBloomFilter::new(3, 10000, 0.01).unwrap()));
        let issuer = Arc::new(CredentialIssuer::new());
        
        // Pre-create credentials to simulate realistic offline verification
        let mut credentials = Vec::new();
        for i in 0..total_verifications {
            let subject = format!("did:lemma:user_{}", i);
            let mut claims = std::collections::HashMap::new();
            claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
            
            let credential = issuer.issue_credential(subject, claims, None).unwrap();
            credentials.push(credential);
        }
        
        let credentials = Arc::new(credentials);
        let success_count = Arc::new(Mutex::new(0));
        let error_count = Arc::new(Mutex::new(0));
        let timing_data = Arc::new(Mutex::new(Vec::new()));
        
        let start_time = Instant::now();
        
        // Spawn threads for concurrent verification
        let mut handles = Vec::new();
        for thread_id in 0..num_threads {
            let oprf_client = Arc::clone(&oprf_client);
            let bloom_filter = Arc::clone(&bloom_filter);
            let issuer = Arc::clone(&issuer);
            let credentials = Arc::clone(&credentials);
            let success_count = Arc::clone(&success_count);
            let error_count = Arc::clone(&error_count);
            let timing_data = Arc::clone(&timing_data);
            
            let handle = thread::spawn(move || {
                let mut thread_timings = Vec::new();
                
                for i in 0..verifications_per_thread {
                    let credential_index = thread_id * verifications_per_thread + i;
                    let credential = &credentials[credential_index];
                    
                    let verification_start = Instant::now();
                    
                    // Realistic verification flow
                    let result = (|| -> Result<bool> {
                        // 1. Verify signature
                        let is_valid = credential.verify_signature()?;
                        if !is_valid {
                            return Ok(false);
                        }
                        
                        // 2. Get OPRF evaluation (with lock contention)
                        let oprf_result = {
                            let mut client = oprf_client.lock().unwrap();
                            client.get_evaluation(&credential.id)?
                        };
                        
                        // 3. Check revocation (with lock contention)
                        let (is_revoked, _level) = {
                            let filter = bloom_filter.lock().unwrap();
                            filter.contains(&oprf_result.evaluation)
                        };
                        
                        Ok(!is_revoked)
                    })();
                    
                    let verification_duration = verification_start.elapsed();
                    thread_timings.push(verification_duration);
                    
                    match result {
                        Ok(true) => {
                            let mut count = success_count.lock().unwrap();
                            *count += 1;
                        }
                        Ok(false) => {
                            let mut count = error_count.lock().unwrap();
                            *count += 1;
                        }
                        Err(_) => {
                            let mut count = error_count.lock().unwrap();
                            *count += 1;
                        }
                    }
                    
                    // Small delay to simulate real-world usage
                    thread::sleep(Duration::from_micros(10));
                }
                
                // Store timing data
                let mut timing_data = timing_data.lock().unwrap();
                timing_data.extend(thread_timings);
            });
            
            handles.push(handle);
        }
        
        // Wait for all threads to complete
        for handle in handles {
            handle.join().unwrap();
        }
        
        let total_duration = start_time.elapsed();
        let success_count = *success_count.lock().unwrap();
        let error_count = *error_count.lock().unwrap();
        let timing_data = timing_data.lock().unwrap();
        
        // Calculate statistics
        let mut timings_us: Vec<f64> = timing_data.iter()
            .map(|d| d.as_micros() as f64)
            .collect();
        timings_us.sort_by(|a, b| a.partial_cmp(b).unwrap());
        
        let avg_time_us = timings_us.iter().sum::<f64>() / timings_us.len() as f64;
        let median_time_us = timings_us[timings_us.len() / 2];
        let p95_time_us = timings_us[(timings_us.len() as f64 * 0.95) as usize];
        let p99_time_us = timings_us[(timings_us.len() as f64 * 0.99) as usize];
        let min_time_us = timings_us[0];
        let max_time_us = timings_us[timings_us.len() - 1];
        
        let throughput = total_verifications as f64 / total_duration.as_secs_f64();
        
        println!("\n=== REALISTIC CONCURRENT VERIFICATION STRESS TEST ===");
        println!("Threads: {}", num_threads);
        println!("Verifications per thread: {}", verifications_per_thread);
        println!("Total verifications: {}", total_verifications);
        println!("Total duration: {:.2}s", total_duration.as_secs_f64());
        println!("Success rate: {:.2}%", (success_count as f64 / total_verifications as f64) * 100.0);
        println!("Error count: {}", error_count);
        println!("\nTiming Statistics (microseconds):");
        println!("  Average: {:.2} µs", avg_time_us);
        println!("  Median:  {:.2} µs", median_time_us);
        println!("  95th percentile: {:.2} µs", p95_time_us);
        println!("  99th percentile: {:.2} µs", p99_time_us);
        println!("  Min: {:.2} µs", min_time_us);
        println!("  Max: {:.2} µs", max_time_us);
        println!("\nThroughput: {:.0} verifications/second", throughput);
        
        // Validate performance claims
        assert!(success_count > total_verifications * 95 / 100, "Success rate too low");
        assert!(avg_time_us < 1000.0, "Average time too high"); // Should be < 1ms
        assert!(p95_time_us < 2000.0, "95th percentile too high"); // Should be < 2ms
        assert!(throughput > 1000.0, "Throughput too low"); // Should be > 1000/sec
    }
} 

#[cfg(test)]
mod validation_tests {
    use super::*;
    use crate::packages::{IdentityPackage, TicketPackage, PackageAuthenticityPackage, QRCodePackage};
    use std::time::Instant;
    
    #[test]
    fn validate_verification_timing_claims() {
        // Set up exactly like WebAssembly module
        let mut core = LemmaCore::new().unwrap();
        core.register_package(IdentityPackage::new());
        core.register_package(TicketPackage::new());
        core.register_package(PackageAuthenticityPackage::new());
        core.register_package(QRCodePackage::new("generic".to_string()));
        
        // Create test credential
        let issuer = CredentialIssuer::new();
        let mut claims = std::collections::HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
        let credential = issuer.issue_credential(
            "did:lemma:test_subject".to_string(),
            claims,
            None,
        ).unwrap();
        
        // Test uncached verification (cold start)
        let start = Instant::now();
        let result = core.verify(&credential).unwrap();
        let uncached_duration = start.elapsed();
        
        println!("Uncached verification: {:?} ({:.2} µs)", uncached_duration, uncached_duration.as_micros() as f64);
        assert!(result.verified, "Verification should succeed");
        
        // Test cached verification (warm)
        let mut timings = Vec::new();
        for _ in 0..1000 {
            let start = Instant::now();
            let result = core.verify(&credential).unwrap();
            let duration = start.elapsed();
            timings.push(duration.as_micros() as f64);
            assert!(result.verified, "Verification should succeed");
        }
        
        // Calculate statistics
        let min_time = timings.iter().fold(f64::INFINITY, |a, &b| a.min(b));
        let max_time = timings.iter().fold(0.0f64, |a, &b| a.max(b));
        let avg_time = timings.iter().sum::<f64>() / timings.len() as f64;
        
        timings.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let median_time = timings[timings.len() / 2];
        
        println!("Cached verification statistics (µs):");
        println!("  Min: {:.2}", min_time);
        println!("  Max: {:.2}", max_time);
        println!("  Avg: {:.2}", avg_time);
        println!("  Median: {:.2}", median_time);
        
        // Check if the 32.8 µs claim is reasonable
        let claim_time = 32.8;
        if avg_time > claim_time * 10.0 {
            println!("⚠️  WARNING: Average time ({:.2} µs) is >10x the claimed time ({:.2} µs)", avg_time, claim_time);
        } else if avg_time > claim_time * 2.0 {
            println!("⚠️  WARNING: Average time ({:.2} µs) is >2x the claimed time ({:.2} µs)", avg_time, claim_time);
        } else {
            println!("✅ Performance claim appears reasonable");
        }
    }
} 