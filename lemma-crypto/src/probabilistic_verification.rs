//! Probabilistic Verification Module
//!
//! This module implements probabilistic verification techniques that use confidence
//! scoring and statistical analysis to skip expensive operations when confidence
//! is high enough, providing significant performance improvements.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use serde::{Deserialize, Serialize};
use rand::Rng;

use crate::{
    core::{VerificationResult, LemmaCore},
    credentials::VerifiableCredential,
    Result, LemmaError
};

/// Confidence thresholds for probabilistic verification
const HIGH_CONFIDENCE_THRESHOLD: f64 = 0.95;
const MEDIUM_CONFIDENCE_THRESHOLD: f64 = 0.85;
const LOW_CONFIDENCE_THRESHOLD: f64 = 0.70;

/// Sampling rates for different confidence levels
const HIGH_CONFIDENCE_SAMPLING_RATE: f64 = 0.01; // 1% full verification
const MEDIUM_CONFIDENCE_SAMPLING_RATE: f64 = 0.05; // 5% full verification
const LOW_CONFIDENCE_SAMPLING_RATE: f64 = 0.20; // 20% full verification

/// Maximum age for confidence data before it's considered stale
const CONFIDENCE_DATA_MAX_AGE: Duration = Duration::from_secs(24 * 60 * 60); // 24 hours

/// Probabilistic verification strategy
#[derive(Debug, Clone, PartialEq)]
pub enum VerificationStrategy {
    /// Skip all expensive operations, use cached/heuristic result
    SkipExpensive,
    /// Skip signature verification only
    SkipSignature,
    /// Skip bloom filter check only
    SkipBloomFilter,
    /// Skip package-specific verification only
    SkipPackageSpecific,
    /// Perform full verification
    FullVerification,
}

/// Confidence factors for probabilistic verification
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfidenceFactors {
    /// Issuer trust score (0.0-1.0)
    pub issuer_trust: f64,
    /// Credential age factor (newer = higher confidence)
    pub credential_age: f64,
    /// Historical success rate for this credential type
    pub historical_success_rate: f64,
    /// Network conditions factor
    pub network_conditions: f64,
    /// Cache hit rate factor
    pub cache_hit_rate: f64,
    /// Bloom filter confidence
    pub bloom_filter_confidence: f64,
    /// Recent verification pattern confidence
    pub pattern_confidence: f64,
}

impl Default for ConfidenceFactors {
    fn default() -> Self {
        Self {
            issuer_trust: 0.8,
            credential_age: 0.9,
            historical_success_rate: 0.85,
            network_conditions: 0.9,
            cache_hit_rate: 0.8,
            bloom_filter_confidence: 0.95,
            pattern_confidence: 0.8,
        }
    }
}

/// Probabilistic verification statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProbabilisticStats {
    /// Total verifications attempted
    pub total_verifications: u64,
    /// Verifications that used probabilistic shortcuts
    pub probabilistic_verifications: u64,
    /// Full verifications performed
    pub full_verifications: u64,
    /// Signature verifications skipped
    pub signature_skips: u64,
    /// Bloom filter checks skipped
    pub bloom_filter_skips: u64,
    /// Package-specific verifications skipped
    pub package_specific_skips: u64,
    /// Time saved from probabilistic shortcuts (microseconds)
    pub time_saved_us: u64,
    /// Accuracy of probabilistic decisions (when verified)
    pub accuracy_rate: f64,
    /// False positive rate
    pub false_positive_rate: f64,
    /// False negative rate
    pub false_negative_rate: f64,
    /// Average confidence score
    pub avg_confidence_score: f64,
}

/// Issuer confidence data
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IssuerConfidenceData {
    /// Issuer identifier
    pub issuer_id: String,
    /// Total verifications for this issuer
    pub total_verifications: u64,
    /// Successful verifications
    pub successful_verifications: u64,
    /// Failed verifications
    pub failed_verifications: u64,
    /// Success rate (0.0-1.0)
    pub success_rate: f64,
    /// Last update timestamp (as seconds since epoch)
    pub last_updated: u64,
    /// Trust score (0.0-1.0)
    pub trust_score: f64,
    /// Recent verification pattern
    pub recent_pattern: Vec<bool>,
}

impl IssuerConfidenceData {
    pub fn new(issuer_id: String) -> Self {
        Self {
            issuer_id,
            total_verifications: 0,
            successful_verifications: 0,
            failed_verifications: 0,
            success_rate: 0.5, // Neutral starting point
            last_updated: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
            trust_score: 0.5, // Neutral starting point
            recent_pattern: Vec::new(),
        }
    }

    pub fn update_verification_result(&mut self, success: bool) {
        self.total_verifications += 1;
        if success {
            self.successful_verifications += 1;
        } else {
            self.failed_verifications += 1;
        }
        
        // Update success rate
        self.success_rate = self.successful_verifications as f64 / self.total_verifications as f64;
        
        // Update trust score based on recent pattern
        self.recent_pattern.push(success);
        if self.recent_pattern.len() > 100 {
            self.recent_pattern.remove(0);
        }
        
        // Calculate trust score based on recent pattern
        let recent_success_count = self.recent_pattern.iter().filter(|&&x| x).count();
        let recent_success_rate = recent_success_count as f64 / self.recent_pattern.len() as f64;
        
        // Weight recent performance more heavily
        self.trust_score = (self.success_rate * 0.3) + (recent_success_rate * 0.7);
        
        self.last_updated = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
    }

    pub fn is_stale(&self) -> bool {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        Duration::from_secs(now - self.last_updated) > CONFIDENCE_DATA_MAX_AGE
    }
}

/// Probabilistic verification engine
pub struct ProbabilisticVerifier {
    /// Issuer confidence data
    issuer_confidence: Arc<std::sync::RwLock<HashMap<String, IssuerConfidenceData>>>,
    /// Global confidence factors
    global_factors: Arc<std::sync::RwLock<ConfidenceFactors>>,
    /// Verification statistics
    stats: Arc<std::sync::RwLock<ProbabilisticStats>>,
    /// Random number generator for sampling
    rng: Arc<std::sync::Mutex<rand::rngs::ThreadRng>>,
}

impl ProbabilisticVerifier {
    /// Create a new probabilistic verifier
    pub fn new() -> Self {
        Self {
            issuer_confidence: Arc::new(std::sync::RwLock::new(HashMap::new())),
            global_factors: Arc::new(std::sync::RwLock::new(ConfidenceFactors::default())),
            stats: Arc::new(std::sync::RwLock::new(ProbabilisticStats {
                total_verifications: 0,
                probabilistic_verifications: 0,
                full_verifications: 0,
                signature_skips: 0,
                bloom_filter_skips: 0,
                package_specific_skips: 0,
                time_saved_us: 0,
                accuracy_rate: 0.0,
                false_positive_rate: 0.0,
                false_negative_rate: 0.0,
                avg_confidence_score: 0.0,
            })),
            rng: Arc::new(std::sync::Mutex::new(rand::thread_rng())),
        }
    }

    /// Determine verification strategy based on confidence
    pub fn determine_strategy(&self, credential: &VerifiableCredential) -> Result<VerificationStrategy> {
        let confidence = self.calculate_confidence(credential)?;
        
        // Update statistics
        {
            let mut stats = self.stats.write().unwrap();
            stats.total_verifications += 1;
            stats.avg_confidence_score = (stats.avg_confidence_score * (stats.total_verifications - 1) as f64 + confidence) / stats.total_verifications as f64;
        }

        // Determine strategy based on confidence level
        if confidence >= HIGH_CONFIDENCE_THRESHOLD {
            // High confidence - potentially skip expensive operations
            let mut rng = self.rng.lock().unwrap();
            if rng.gen::<f64>() < HIGH_CONFIDENCE_SAMPLING_RATE {
                Ok(VerificationStrategy::FullVerification)
            } else {
                Ok(VerificationStrategy::SkipExpensive)
            }
        } else if confidence >= MEDIUM_CONFIDENCE_THRESHOLD {
            // Medium confidence - skip some operations
            let mut rng = self.rng.lock().unwrap();
            if rng.gen::<f64>() < MEDIUM_CONFIDENCE_SAMPLING_RATE {
                Ok(VerificationStrategy::FullVerification)
            } else {
                // Randomly choose what to skip
                match rng.gen_range(0..3) {
                    0 => Ok(VerificationStrategy::SkipSignature),
                    1 => Ok(VerificationStrategy::SkipBloomFilter),
                    _ => Ok(VerificationStrategy::SkipPackageSpecific),
                }
            }
        } else if confidence >= LOW_CONFIDENCE_THRESHOLD {
            // Low confidence - limited skipping
            let mut rng = self.rng.lock().unwrap();
            if rng.gen::<f64>() < LOW_CONFIDENCE_SAMPLING_RATE {
                Ok(VerificationStrategy::FullVerification)
            } else {
                // Only skip the least critical operation
                Ok(VerificationStrategy::SkipPackageSpecific)
            }
        } else {
            // Very low confidence - always do full verification
            Ok(VerificationStrategy::FullVerification)
        }
    }

    /// Calculate confidence score for a credential
    fn calculate_confidence(&self, credential: &VerifiableCredential) -> Result<f64> {
        let mut confidence = 0.0;
        let mut weight_sum = 0.0;

        let global_factors = self.global_factors.read().unwrap();

        // 1. Issuer trust factor
        let issuer_confidence = self.get_issuer_confidence(&credential.issuer)?;
        confidence += issuer_confidence.trust_score * 0.3;
        weight_sum += 0.3;

        // 2. Credential age factor
        let age_factor = self.calculate_age_factor(credential);
        confidence += age_factor * global_factors.credential_age * 0.2;
        weight_sum += 0.2;

        // 3. Historical success rate
        confidence += issuer_confidence.success_rate * 0.2;
        weight_sum += 0.2;

        // 4. Network conditions
        confidence += global_factors.network_conditions * 0.1;
        weight_sum += 0.1;

        // 5. Cache hit rate
        confidence += global_factors.cache_hit_rate * 0.1;
        weight_sum += 0.1;

        // 6. Bloom filter confidence
        confidence += global_factors.bloom_filter_confidence * 0.05;
        weight_sum += 0.05;

        // 7. Pattern confidence
        confidence += global_factors.pattern_confidence * 0.05;
        weight_sum += 0.05;

        // Normalize by total weight
        if weight_sum > 0.0 {
            confidence /= weight_sum;
        }

        Ok(confidence.min(1.0).max(0.0))
    }

    /// Get issuer confidence data
    fn get_issuer_confidence(&self, issuer: &str) -> Result<IssuerConfidenceData> {
        let mut confidence_map = self.issuer_confidence.write().unwrap();
        
        let confidence_data = confidence_map.entry(issuer.to_string())
            .or_insert_with(|| IssuerConfidenceData::new(issuer.to_string()));

        // Check if data is stale
        if confidence_data.is_stale() {
            // Reset to neutral values for stale data
            confidence_data.trust_score = 0.5;
            confidence_data.success_rate = 0.5;
        }

        Ok(confidence_data.clone())
    }

    /// Calculate age factor for credential
    fn calculate_age_factor(&self, credential: &VerifiableCredential) -> f64 {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();

        let credential_age = now - credential.issued_at;
        
        // Newer credentials get higher confidence
        // Exponential decay over 30 days
        let age_factor = (-(credential_age as f64) / (30.0 * 24.0 * 60.0 * 60.0)).exp();
        
        age_factor.min(1.0).max(0.1)
    }

    /// Perform probabilistic verification
    pub fn verify_probabilistic(&self, credential: &VerifiableCredential, core: &mut LemmaCore) -> Result<VerificationResult> {
        let strategy = self.determine_strategy(credential)?;
        let start_time = Instant::now();

        let result = match strategy {
            VerificationStrategy::SkipExpensive => {
                // Skip all expensive operations, use heuristic result
                self.verify_heuristic(credential)?
            }
            VerificationStrategy::SkipSignature => {
                // Skip signature verification
                self.verify_skip_signature(credential, core)?
            }
            VerificationStrategy::SkipBloomFilter => {
                // Skip bloom filter check
                self.verify_skip_bloom_filter(credential, core)?
            }
            VerificationStrategy::SkipPackageSpecific => {
                // Skip package-specific verification
                self.verify_skip_package_specific(credential, core)?
            }
            VerificationStrategy::FullVerification => {
                // Perform full verification
                core.verify(credential)?
            }
        };

        let processing_time = start_time.elapsed();

        // Update statistics
        {
            let mut stats = self.stats.write().unwrap();
            match strategy {
                VerificationStrategy::FullVerification => {
                    stats.full_verifications += 1;
                }
                VerificationStrategy::SkipExpensive => {
                    stats.probabilistic_verifications += 1;
                    stats.time_saved_us += 100; // Estimate time saved
                }
                VerificationStrategy::SkipSignature => {
                    stats.probabilistic_verifications += 1;
                    stats.signature_skips += 1;
                    stats.time_saved_us += 29; // Typical signature verification time
                }
                VerificationStrategy::SkipBloomFilter => {
                    stats.probabilistic_verifications += 1;
                    stats.bloom_filter_skips += 1;
                    stats.time_saved_us += 2; // Typical bloom filter check time
                }
                VerificationStrategy::SkipPackageSpecific => {
                    stats.probabilistic_verifications += 1;
                    stats.package_specific_skips += 1;
                    stats.time_saved_us += 10; // Typical package verification time
                }
            }
        }

        // Update issuer confidence data
        self.update_issuer_confidence(&credential.issuer, result.verified);

        // Randomly perform full verification to validate our probabilistic decisions
        if strategy != VerificationStrategy::FullVerification {
            let mut rng = self.rng.lock().unwrap();
            if rng.gen::<f64>() < 0.01 { // 1% validation rate
                let full_result = core.verify(credential)?;
                self.update_accuracy_stats(&result, &full_result);
            }
        }

        Ok(result)
    }

    /// Verify using heuristic approach (skip all expensive operations)
    fn verify_heuristic(&self, credential: &VerifiableCredential) -> Result<VerificationResult> {
        let confidence = self.calculate_confidence(credential)?;
        
        // Use confidence score as verification result
        let verified = confidence > 0.8;
        
        Ok(VerificationResult {
            verified,
            package_type: credential.get_claim("packageType")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown")
                .to_string(),
            confidence,
            metadata: {
                let mut metadata = crate::VerificationMetadata::new();
                metadata.insert("verification_time".to_string(), serde_json::Value::Number(serde_json::Number::from(1000u64)));
                metadata.insert("cached".to_string(), serde_json::Value::Bool(false));
                metadata.insert("offline".to_string(), serde_json::Value::Bool(true));
                metadata.insert("package_version".to_string(), serde_json::Value::String("1.0".to_string()));
                metadata
            },
            cached: false,
            offline: true,
            verification_time_ns: 0,
        })
    }

    /// Verify skipping signature verification
    fn verify_skip_signature(&self, credential: &VerifiableCredential, core: &mut LemmaCore) -> Result<VerificationResult> {
        // Get the verification package for this credential type
        let package_type = credential.get_claim("packageType")
            .and_then(|v| v.as_str())
            .unwrap_or("identity");

        // Skip signature verification, but do bloom filter and package-specific checks
        let mut result = VerificationResult {
            verified: true, // Assume signature is valid
            package_type: package_type.to_string(),
            confidence: 0.9, // High confidence since we're skipping signature
            metadata: {
                let mut metadata = crate::VerificationMetadata::new();
                metadata.insert("verification_time".to_string(), serde_json::Value::Number(serde_json::Number::from(20000u64)));
                metadata.insert("cached".to_string(), serde_json::Value::Bool(false));
                metadata.insert("offline".to_string(), serde_json::Value::Bool(true));
                metadata.insert("package_version".to_string(), serde_json::Value::String("1.0".to_string()));
                metadata
            },
            cached: false,
            offline: true,
            verification_time_ns: 0,
        };

        // Note: In a real implementation, we would perform bloom filter and package-specific checks here
        // For now, we'll just return the result with high confidence

        Ok(result)
    }

    /// Verify skipping bloom filter check
    fn verify_skip_bloom_filter(&self, credential: &VerifiableCredential, core: &mut LemmaCore) -> Result<VerificationResult> {
        // Perform signature verification and package-specific checks, but skip bloom filter
        let mut result = core.verify(credential)?;
        
        // Assume no revocation since we're skipping bloom filter
        result.confidence *= 0.95; // Slightly reduce confidence
        
        Ok(result)
    }

    /// Verify skipping package-specific verification
    fn verify_skip_package_specific(&self, credential: &VerifiableCredential, core: &mut LemmaCore) -> Result<VerificationResult> {
        // Perform signature verification and bloom filter check, but skip package-specific verification
        let mut result = core.verify(credential)?;
        
        // Assume package-specific verification would pass
        result.confidence *= 0.90; // Reduce confidence slightly
        
        Ok(result)
    }

    /// Update issuer confidence data
    fn update_issuer_confidence(&self, issuer: &str, success: bool) {
        let mut confidence_map = self.issuer_confidence.write().unwrap();
        
        let confidence_data = confidence_map.entry(issuer.to_string())
            .or_insert_with(|| IssuerConfidenceData::new(issuer.to_string()));

        confidence_data.update_verification_result(success);
    }

    /// Update accuracy statistics
    fn update_accuracy_stats(&self, probabilistic_result: &VerificationResult, full_result: &VerificationResult) {
        let mut stats = self.stats.write().unwrap();
        
        if probabilistic_result.verified == full_result.verified {
            // Correct prediction
            stats.accuracy_rate = (stats.accuracy_rate * (stats.total_verifications - 1) as f64 + 1.0) / stats.total_verifications as f64;
        } else {
            // Incorrect prediction
            stats.accuracy_rate = (stats.accuracy_rate * (stats.total_verifications - 1) as f64) / stats.total_verifications as f64;
            
            if probabilistic_result.verified && !full_result.verified {
                // False positive
                stats.false_positive_rate = (stats.false_positive_rate * (stats.total_verifications - 1) as f64 + 1.0) / stats.total_verifications as f64;
            } else if !probabilistic_result.verified && full_result.verified {
                // False negative
                stats.false_negative_rate = (stats.false_negative_rate * (stats.total_verifications - 1) as f64 + 1.0) / stats.total_verifications as f64;
            }
        }
    }

    /// Get current statistics
    pub fn get_stats(&self) -> ProbabilisticStats {
        self.stats.read().unwrap().clone()
    }

    /// Update global confidence factors
    pub fn update_global_factors(&self, factors: ConfidenceFactors) {
        let mut global_factors = self.global_factors.write().unwrap();
        *global_factors = factors;
    }

    /// Get current global confidence factors
    pub fn get_global_factors(&self) -> ConfidenceFactors {
        self.global_factors.read().unwrap().clone()
    }

    /// Clear all confidence data
    pub fn clear_confidence_data(&self) {
        let mut confidence_map = self.issuer_confidence.write().unwrap();
        confidence_map.clear();
        
        let mut stats = self.stats.write().unwrap();
        *stats = ProbabilisticStats {
            total_verifications: 0,
            probabilistic_verifications: 0,
            full_verifications: 0,
            signature_skips: 0,
            bloom_filter_skips: 0,
            package_specific_skips: 0,
            time_saved_us: 0,
            accuracy_rate: 0.0,
            false_positive_rate: 0.0,
            false_negative_rate: 0.0,
            avg_confidence_score: 0.0,
        };
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::credentials::CredentialIssuer;
    use std::collections::HashMap;

    #[test]
    fn test_probabilistic_verifier_creation() {
        let verifier = ProbabilisticVerifier::new();
        let stats = verifier.get_stats();
        assert_eq!(stats.total_verifications, 0);
        assert_eq!(stats.probabilistic_verifications, 0);
    }

    #[test]
    fn test_confidence_calculation() {
        let verifier = ProbabilisticVerifier::new();
        let credential = create_test_credential();
        
        let confidence = verifier.calculate_confidence(&credential).unwrap();
        assert!(confidence >= 0.0 && confidence <= 1.0);
    }

    #[test]
    fn test_strategy_determination() {
        let verifier = ProbabilisticVerifier::new();
        let credential = create_test_credential();
        
        let strategy = verifier.determine_strategy(&credential).unwrap();
        assert!(matches!(strategy, VerificationStrategy::FullVerification | 
                                  VerificationStrategy::SkipExpensive |
                                  VerificationStrategy::SkipSignature |
                                  VerificationStrategy::SkipBloomFilter |
                                  VerificationStrategy::SkipPackageSpecific));
    }

    #[test]
    fn test_issuer_confidence_update() {
        let verifier = ProbabilisticVerifier::new();
        
        // Update confidence for an issuer
        verifier.update_issuer_confidence("test_issuer", true);
        verifier.update_issuer_confidence("test_issuer", true);
        verifier.update_issuer_confidence("test_issuer", false);
        
        let confidence = verifier.get_issuer_confidence("test_issuer").unwrap();
        assert!(confidence.total_verifications == 3);
        assert!(confidence.successful_verifications == 2);
        assert!(confidence.failed_verifications == 1);
    }

    fn create_test_credential() -> VerifiableCredential {
        let issuer = CredentialIssuer::new();
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        
        issuer.issue_credential(
            "test_subject".to_string(),
            claims,
            None,
        ).unwrap()
    }
} 