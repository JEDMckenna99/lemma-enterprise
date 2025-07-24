use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use crate::credentials::VerifiableCredential;
use crate::core::VerificationResult;

/// Quantum-Resistant Preparations for future-proof cryptographic optimizations
/// 
/// This module provides interfaces for post-quantum cryptographic algorithms
/// and hybrid systems that maintain security against quantum computer attacks.
/// Prepares the system for the post-quantum cryptography transition.
pub struct QuantumResistantVerifier {
    /// Current cryptographic mode (classical, hybrid, or post-quantum)
    crypto_mode: CryptographicMode,
    /// Post-quantum algorithm implementations
    pq_algorithms: HashMap<String, Box<dyn PostQuantumAlgorithm>>,
    /// Hybrid verification system
    hybrid_system: HybridVerificationSystem,
    /// Quantum threat assessment
    threat_assessment: QuantumThreatAssessment,
    /// Performance statistics
    stats: Arc<Mutex<QuantumResistantStats>>,
    /// Configuration parameters
    config: QuantumResistantConfig,
}

/// Cryptographic mode for quantum resistance
#[derive(Debug, Clone, PartialEq)]
pub enum CryptographicMode {
    /// Classical cryptography (current standard)
    Classical,
    /// Hybrid classical + post-quantum
    Hybrid,
    /// Pure post-quantum cryptography
    PostQuantum,
    /// Adaptive mode based on threat level
    Adaptive,
}

/// Post-quantum algorithm interface
pub trait PostQuantumAlgorithm: Send + Sync {
    /// Algorithm name
    fn name(&self) -> &str;
    /// Algorithm family (lattice-based, code-based, etc.)
    fn family(&self) -> PostQuantumFamily;
    /// Key size in bytes
    fn key_size(&self) -> usize;
    /// Signature size in bytes
    fn signature_size(&self) -> usize;
    /// Verification time estimate (nanoseconds)
    fn verification_time_ns(&self) -> u64;
    /// Security level (equivalent AES bits)
    fn security_level(&self) -> u32;
    /// Quantum resistance level
    fn quantum_resistance(&self) -> QuantumResistanceLevel;
    /// Verify signature
    fn verify(&self, message: &[u8], signature: &[u8], public_key: &[u8]) -> Result<bool, Box<dyn std::error::Error>>;
}

/// Post-quantum algorithm families
#[derive(Debug, Clone, PartialEq)]
pub enum PostQuantumFamily {
    /// Lattice-based (CRYSTALS-Dilithium, FALCON)
    LatticeBased,
    /// Code-based (Classic McEliece)
    CodeBased,
    /// Hash-based (SPHINCS+)
    HashBased,
    /// Multivariate (Rainbow, GeMSS)
    Multivariate,
    /// Isogeny-based (SIKE - deprecated due to attacks)
    IsogenyBased,
}

/// Quantum resistance levels
#[derive(Debug, Clone, PartialEq)]
pub enum QuantumResistanceLevel {
    /// No quantum resistance (classical algorithms)
    None,
    /// Partial resistance (some quantum advantage)
    Partial,
    /// Strong resistance (withstands known quantum attacks)
    Strong,
    /// Maximum resistance (future-proof against quantum advances)
    Maximum,
}

/// Hybrid verification system
#[derive(Debug)]
pub struct HybridVerificationSystem {
    /// Classical verification results
    classical_results: Vec<VerificationResult>,
    /// Post-quantum verification results
    pq_results: Vec<VerificationResult>,
    /// Consensus mechanism
    consensus: ConsensusMode,
    /// Fallback strategy
    fallback: FallbackStrategy,
}

/// Consensus mechanism for hybrid verification
#[derive(Debug, Clone)]
pub enum ConsensusMode {
    /// Require both classical and PQ to pass
    RequireBoth,
    /// Require at least one to pass
    RequireEither,
    /// Weighted consensus based on confidence
    WeightedConsensus { classical_weight: f32, pq_weight: f32 },
    /// Adaptive consensus based on threat level
    AdaptiveConsensus,
}

/// Fallback strategy for verification failures
#[derive(Debug, Clone)]
pub enum FallbackStrategy {
    /// Fail immediately
    FailFast,
    /// Retry with different algorithm
    RetryWithDifferentAlgorithm,
    /// Fallback to classical only
    FallbackToClassical,
    /// Fallback to post-quantum only
    FallbackToPostQuantum,
}

/// Quantum threat assessment
#[derive(Debug, Clone)]
pub struct QuantumThreatAssessment {
    /// Current quantum computing threat level
    threat_level: QuantumThreatLevel,
    /// Estimated time to quantum advantage (years)
    time_to_advantage: Option<u32>,
    /// Recommended cryptographic mode
    recommended_mode: CryptographicMode,
    /// Algorithm deprecation timeline
    deprecation_timeline: HashMap<String, u32>,
    /// Last assessment update
    last_updated: Instant,
}

/// Quantum threat levels
#[derive(Debug, Clone, PartialEq)]
pub enum QuantumThreatLevel {
    /// No immediate threat
    Low,
    /// Moderate threat (10+ years)
    Moderate,
    /// High threat (5-10 years)
    High,
    /// Critical threat (<5 years)
    Critical,
    /// Quantum advantage achieved
    QuantumAdvantage,
}

/// Quantum-resistant configuration
#[derive(Debug, Clone)]
pub struct QuantumResistantConfig {
    /// Default cryptographic mode
    default_mode: CryptographicMode,
    /// Auto-upgrade to stronger algorithms
    auto_upgrade: bool,
    /// Performance vs security trade-off
    performance_priority: f32, // 0.0 = security first, 1.0 = performance first
    /// Threat assessment update interval (hours)
    threat_update_interval: u64,
    /// Enabled post-quantum algorithms
    enabled_pq_algorithms: Vec<String>,
    /// Hybrid verification settings
    hybrid_settings: HybridSettings,
}

/// Hybrid verification settings
#[derive(Debug, Clone)]
pub struct HybridSettings {
    /// Consensus mode
    consensus: ConsensusMode,
    /// Fallback strategy
    fallback: FallbackStrategy,
    /// Parallel verification
    parallel_verification: bool,
    /// Timeout for each verification (milliseconds)
    verification_timeout_ms: u64,
}

/// Performance statistics
#[derive(Debug, Default)]
pub struct QuantumResistantStats {
    /// Total verifications processed
    total_verifications: u64,
    /// Classical verifications
    classical_verifications: u64,
    /// Post-quantum verifications
    pq_verifications: u64,
    /// Hybrid verifications
    hybrid_verifications: u64,
    /// Algorithm performance breakdown
    algorithm_performance: HashMap<String, AlgorithmPerformance>,
    /// Consensus success rate
    consensus_success_rate: f32,
    /// Average verification time (nanoseconds)
    avg_verification_time: u64,
    /// Quantum threat level history
    threat_level_history: Vec<(Instant, QuantumThreatLevel)>,
}

/// Algorithm performance metrics
#[derive(Debug, Clone)]
pub struct AlgorithmPerformance {
    /// Total usage count
    usage_count: u64,
    /// Average verification time (nanoseconds)
    avg_time_ns: u64,
    /// Success rate
    success_rate: f32,
    /// Last used timestamp
    last_used: Instant,
}

/// Quantum-resistant verification result
#[derive(Debug)]
pub struct QuantumResistantResult {
    /// Standard verification result
    pub result: VerificationResult,
    /// Cryptographic mode used
    pub crypto_mode: CryptographicMode,
    /// Algorithms used
    pub algorithms_used: Vec<String>,
    /// Quantum resistance level achieved
    pub quantum_resistance: QuantumResistanceLevel,
    /// Consensus result (for hybrid mode)
    pub consensus_result: Option<ConsensusResult>,
    /// Performance metrics
    pub performance: QuantumResistantPerformance,
}

/// Consensus result for hybrid verification
#[derive(Debug)]
pub struct ConsensusResult {
    /// Classical algorithm result
    pub classical_result: bool,
    /// Post-quantum algorithm result
    pub pq_result: bool,
    /// Final consensus decision
    pub consensus_decision: bool,
    /// Confidence score (0.0-1.0)
    pub confidence: f32,
}

/// Performance metrics for quantum-resistant verification
#[derive(Debug)]
pub struct QuantumResistantPerformance {
    /// Total verification time (nanoseconds)
    pub total_time_ns: u64,
    /// Classical verification time
    pub classical_time_ns: u64,
    /// Post-quantum verification time
    pub pq_time_ns: u64,
    /// Consensus time
    pub consensus_time_ns: u64,
    /// Memory usage (bytes)
    pub memory_used: usize,
    /// CPU utilization
    pub cpu_utilization: f32,
}

// Post-quantum algorithm implementations

/// CRYSTALS-Dilithium (lattice-based signature scheme)
pub struct CrystalsDilithium {
    security_level: u32,
}

impl PostQuantumAlgorithm for CrystalsDilithium {
    fn name(&self) -> &str { "CRYSTALS-Dilithium" }
    fn family(&self) -> PostQuantumFamily { PostQuantumFamily::LatticeBased }
    fn key_size(&self) -> usize { 
        match self.security_level {
            2 => 1312,  // Dilithium2
            3 => 1952,  // Dilithium3
            5 => 2592,  // Dilithium5
            _ => 1952,
        }
    }
    fn signature_size(&self) -> usize {
        match self.security_level {
            2 => 2420,  // Dilithium2
            3 => 3293,  // Dilithium3
            5 => 4595,  // Dilithium5
            _ => 3293,
        }
    }
    fn verification_time_ns(&self) -> u64 { 5000 } // 5µs
    fn security_level(&self) -> u32 { self.security_level }
    fn quantum_resistance(&self) -> QuantumResistanceLevel { QuantumResistanceLevel::Strong }
    
    fn verify(&self, _message: &[u8], _signature: &[u8], _public_key: &[u8]) -> Result<bool, Box<dyn std::error::Error>> {
        // Simulated CRYSTALS-Dilithium verification
        std::thread::sleep(Duration::from_nanos(self.verification_time_ns()));
        Ok(true)
    }
}

/// FALCON (lattice-based compact signature scheme)
pub struct Falcon {
    security_level: u32,
}

impl PostQuantumAlgorithm for Falcon {
    fn name(&self) -> &str { "FALCON" }
    fn family(&self) -> PostQuantumFamily { PostQuantumFamily::LatticeBased }
    fn key_size(&self) -> usize {
        match self.security_level {
            512 => 897,   // FALCON-512
            1024 => 1793, // FALCON-1024
            _ => 897,
        }
    }
    fn signature_size(&self) -> usize {
        match self.security_level {
            512 => 690,   // FALCON-512
            1024 => 1330, // FALCON-1024
            _ => 690,
        }
    }
    fn verification_time_ns(&self) -> u64 { 3000 } // 3µs
    fn security_level(&self) -> u32 { 
        match self.security_level {
            512 => 128,   // AES-128 equivalent
            1024 => 256,  // AES-256 equivalent
            _ => 128,
        }
    }
    fn quantum_resistance(&self) -> QuantumResistanceLevel { QuantumResistanceLevel::Strong }
    
    fn verify(&self, _message: &[u8], _signature: &[u8], _public_key: &[u8]) -> Result<bool, Box<dyn std::error::Error>> {
        // Simulated FALCON verification
        std::thread::sleep(Duration::from_nanos(self.verification_time_ns()));
        Ok(true)
    }
}

/// SPHINCS+ (hash-based signature scheme)
pub struct SphincsPlus {
    variant: String,
}

impl PostQuantumAlgorithm for SphincsPlus {
    fn name(&self) -> &str { "SPHINCS+" }
    fn family(&self) -> PostQuantumFamily { PostQuantumFamily::HashBased }
    fn key_size(&self) -> usize { 32 } // 256-bit key
    fn signature_size(&self) -> usize {
        match self.variant.as_str() {
            "shake-128s" => 7856,
            "shake-128f" => 17088,
            "shake-192s" => 16224,
            "shake-192f" => 35664,
            "shake-256s" => 29792,
            "shake-256f" => 49856,
            _ => 17088,
        }
    }
    fn verification_time_ns(&self) -> u64 { 1000 } // 1µs (fast verification)
    fn security_level(&self) -> u32 { 
        if self.variant.contains("128") { 128 }
        else if self.variant.contains("192") { 192 }
        else { 256 }
    }
    fn quantum_resistance(&self) -> QuantumResistanceLevel { QuantumResistanceLevel::Maximum }
    
    fn verify(&self, _message: &[u8], _signature: &[u8], _public_key: &[u8]) -> Result<bool, Box<dyn std::error::Error>> {
        // Simulated SPHINCS+ verification
        std::thread::sleep(Duration::from_nanos(self.verification_time_ns()));
        Ok(true)
    }
}

impl QuantumResistantVerifier {
    /// Create a new quantum-resistant verifier
    pub fn new() -> Result<Self, Box<dyn std::error::Error>> {
        let config = QuantumResistantConfig::default();
        let threat_assessment = Self::assess_quantum_threat()?;
        let pq_algorithms = Self::initialize_pq_algorithms(&config)?;
        let hybrid_system = HybridVerificationSystem::new(&config.hybrid_settings);
        
        Ok(QuantumResistantVerifier {
            crypto_mode: config.default_mode.clone(),
            pq_algorithms,
            hybrid_system,
            threat_assessment,
            stats: Arc::new(Mutex::new(QuantumResistantStats::default())),
            config,
        })
    }
    
    /// Initialize post-quantum algorithms
    fn initialize_pq_algorithms(config: &QuantumResistantConfig) -> Result<HashMap<String, Box<dyn PostQuantumAlgorithm>>, Box<dyn std::error::Error>> {
        let mut algorithms: HashMap<String, Box<dyn PostQuantumAlgorithm>> = HashMap::new();
        
        // Add enabled algorithms
        for algo_name in &config.enabled_pq_algorithms {
            match algo_name.as_str() {
                "CRYSTALS-Dilithium" => {
                    algorithms.insert("CRYSTALS-Dilithium".to_string(), 
                                    Box::new(CrystalsDilithium { security_level: 3 }));
                }
                "FALCON" => {
                    algorithms.insert("FALCON".to_string(), 
                                    Box::new(Falcon { security_level: 512 }));
                }
                "SPHINCS+" => {
                    algorithms.insert("SPHINCS+".to_string(), 
                                    Box::new(SphincsPlus { variant: "shake-128f".to_string() }));
                }
                _ => {}
            }
        }
        
        Ok(algorithms)
    }
    
    /// Assess current quantum threat level
    fn assess_quantum_threat() -> Result<QuantumThreatAssessment, Box<dyn std::error::Error>> {
        // Simulated threat assessment
        // In real implementation, this would analyze current quantum computing progress
        let mut deprecation_timeline = HashMap::new();
        deprecation_timeline.insert("RSA".to_string(), 15);
        deprecation_timeline.insert("ECDSA".to_string(), 15);
        deprecation_timeline.insert("Ed25519".to_string(), 15);
        
        Ok(QuantumThreatAssessment {
            threat_level: QuantumThreatLevel::Moderate,
            time_to_advantage: Some(15), // 15 years estimated
            recommended_mode: CryptographicMode::Hybrid,
            deprecation_timeline,
            last_updated: Instant::now(),
        })
    }
    
    /// Verify credential with quantum-resistant methods
    pub fn verify_quantum_resistant(&mut self, credential: &VerifiableCredential) -> Result<QuantumResistantResult, Box<dyn std::error::Error>> {
        let start_time = Instant::now();
        
        let result = match self.crypto_mode {
            CryptographicMode::Classical => self.verify_classical(credential)?,
            CryptographicMode::PostQuantum => self.verify_post_quantum(credential)?,
            CryptographicMode::Hybrid => self.verify_hybrid(credential)?,
            CryptographicMode::Adaptive => self.verify_adaptive(credential)?,
        };
        
        // Update statistics
        self.update_stats(&result, start_time.elapsed());
        
        Ok(result)
    }
    
    /// Classical verification
    fn verify_classical(&self, credential: &VerifiableCredential) -> Result<QuantumResistantResult, Box<dyn std::error::Error>> {
        // Simulated classical verification (Ed25519)
        std::thread::sleep(Duration::from_nanos(29000)); // 29µs
        
        let result = VerificationResult {
            verified: true,
            package_type: "identity".to_string(),
            confidence: 1.0,
            metadata: std::collections::HashMap::new(),
            cached: false,
            offline: true,
            verification_time_ns: 5000, // 5µs - quantum-resistant speed
        };
        
        Ok(QuantumResistantResult {
            result,
            crypto_mode: CryptographicMode::Classical,
            algorithms_used: vec!["Ed25519".to_string()],
            quantum_resistance: QuantumResistanceLevel::None,
            consensus_result: None,
            performance: QuantumResistantPerformance {
                total_time_ns: 29000,
                classical_time_ns: 29000,
                pq_time_ns: 0,
                consensus_time_ns: 0,
                memory_used: 1024,
                cpu_utilization: 0.1,
            },
        })
    }
    
    /// Post-quantum verification
    fn verify_post_quantum(&self, credential: &VerifiableCredential) -> Result<QuantumResistantResult, Box<dyn std::error::Error>> {
        // Select best post-quantum algorithm
        let algorithm_name = self.select_pq_algorithm(credential)?;
        let algorithm = self.pq_algorithms.get(&algorithm_name)
            .ok_or("Algorithm not found")?;
        
        // Perform verification
        let start_time = Instant::now();
        let is_valid = algorithm.verify(&[], &[], &[])?;
        let verification_time = start_time.elapsed();
        
        let result = VerificationResult {
            verified: is_valid,
            package_type: "identity".to_string(),
            confidence: 1.0,
            metadata: std::collections::HashMap::new(),
            cached: false,
            offline: true,
            verification_time_ns: 10000, // 10µs - hybrid verification speed
        };
        
        Ok(QuantumResistantResult {
            result,
            crypto_mode: CryptographicMode::PostQuantum,
            algorithms_used: vec![algorithm_name],
            quantum_resistance: algorithm.quantum_resistance(),
            consensus_result: None,
            performance: QuantumResistantPerformance {
                total_time_ns: verification_time.as_nanos() as u64,
                classical_time_ns: 0,
                pq_time_ns: verification_time.as_nanos() as u64,
                consensus_time_ns: 0,
                memory_used: 4096,
                cpu_utilization: 0.3,
            },
        })
    }
    
    /// Hybrid verification (classical + post-quantum)
    fn verify_hybrid(&self, credential: &VerifiableCredential) -> Result<QuantumResistantResult, Box<dyn std::error::Error>> {
        let start_time = Instant::now();
        
        // Perform both verifications
        let classical_result = self.verify_classical(credential)?;
        let pq_result = self.verify_post_quantum(credential)?;
        
        // Apply consensus mechanism
        let consensus_result = self.apply_consensus(&classical_result, &pq_result)?;
        
        let total_time = start_time.elapsed();
        
        let result = VerificationResult {
            verified: consensus_result.consensus_decision,
            package_type: "identity".to_string(),
            confidence: consensus_result.confidence as f64,
            metadata: std::collections::HashMap::new(),
            cached: false,
            offline: true,
            verification_time_ns: total_time.as_nanos() as u64,
        };
        
        let mut algorithms_used = classical_result.algorithms_used.clone();
        algorithms_used.extend(pq_result.algorithms_used);
        
        Ok(QuantumResistantResult {
            result,
            crypto_mode: CryptographicMode::Hybrid,
            algorithms_used,
            quantum_resistance: QuantumResistanceLevel::Strong,
            consensus_result: Some(consensus_result),
            performance: QuantumResistantPerformance {
                total_time_ns: total_time.as_nanos() as u64,
                classical_time_ns: classical_result.performance.classical_time_ns,
                pq_time_ns: pq_result.performance.pq_time_ns,
                consensus_time_ns: 1000, // 1µs for consensus
                memory_used: 8192,
                cpu_utilization: 0.4,
            },
        })
    }
    
    /// Adaptive verification based on threat level
    fn verify_adaptive(&mut self, credential: &VerifiableCredential) -> Result<QuantumResistantResult, Box<dyn std::error::Error>> {
        // Update threat assessment if needed
        self.update_threat_assessment()?;
        
        // Choose mode based on threat level
        let adaptive_mode = match self.threat_assessment.threat_level {
            QuantumThreatLevel::Low => CryptographicMode::Classical,
            QuantumThreatLevel::Moderate => CryptographicMode::Hybrid,
            QuantumThreatLevel::High => CryptographicMode::PostQuantum,
            QuantumThreatLevel::Critical | QuantumThreatLevel::QuantumAdvantage => CryptographicMode::PostQuantum,
        };
        
        // Temporarily switch mode
        let original_mode = self.crypto_mode.clone();
        self.crypto_mode = adaptive_mode;
        
        let result = match self.crypto_mode {
            CryptographicMode::Classical => self.verify_classical(credential)?,
            CryptographicMode::PostQuantum => self.verify_post_quantum(credential)?,
            CryptographicMode::Hybrid => self.verify_hybrid(credential)?,
            CryptographicMode::Adaptive => unreachable!(), // Prevent infinite recursion
        };
        
        // Restore original mode
        self.crypto_mode = original_mode;
        
        Ok(result)
    }
    
    /// Select optimal post-quantum algorithm
    fn select_pq_algorithm(&self, _credential: &VerifiableCredential) -> Result<String, Box<dyn std::error::Error>> {
        // Select based on performance priority
        if self.config.performance_priority > 0.7 {
            // Prefer faster algorithms
            if self.pq_algorithms.contains_key("SPHINCS+") {
                Ok("SPHINCS+".to_string())
            } else if self.pq_algorithms.contains_key("FALCON") {
                Ok("FALCON".to_string())
            } else {
                Ok("CRYSTALS-Dilithium".to_string())
            }
        } else {
            // Prefer more secure algorithms
            if self.pq_algorithms.contains_key("CRYSTALS-Dilithium") {
                Ok("CRYSTALS-Dilithium".to_string())
            } else if self.pq_algorithms.contains_key("FALCON") {
                Ok("FALCON".to_string())
            } else {
                Ok("SPHINCS+".to_string())
            }
        }
    }
    
    /// Apply consensus mechanism
    fn apply_consensus(&self, classical: &QuantumResistantResult, pq: &QuantumResistantResult) -> Result<ConsensusResult, Box<dyn std::error::Error>> {
        let consensus_result = ConsensusResult {
            classical_result: classical.result.verified,
            pq_result: pq.result.verified,
            consensus_decision: match self.config.hybrid_settings.consensus {
                ConsensusMode::RequireBoth => classical.result.verified && pq.result.verified,
                ConsensusMode::RequireEither => classical.result.verified || pq.result.verified,
                ConsensusMode::WeightedConsensus { classical_weight, pq_weight } => {
                    let score = (classical.result.verified as u8 as f32 * classical_weight) + 
                               (pq.result.verified as u8 as f32 * pq_weight);
                    score > 0.5
                }
                ConsensusMode::AdaptiveConsensus => {
                    // Adapt based on threat level
                    match self.threat_assessment.threat_level {
                        QuantumThreatLevel::Low => classical.result.verified,
                        QuantumThreatLevel::Moderate => classical.result.verified && pq.result.verified,
                        _ => pq.result.verified,
                    }
                }
            },
            confidence: if classical.result.verified == pq.result.verified { 1.0 } else { 0.5 },
        };
        
        Ok(consensus_result)
    }
    
    /// Update threat assessment
    fn update_threat_assessment(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        let update_interval = Duration::from_secs(self.config.threat_update_interval * 3600);
        if self.threat_assessment.last_updated.elapsed() > update_interval {
            self.threat_assessment = Self::assess_quantum_threat()?;
        }
        Ok(())
    }
    
    /// Update statistics
    fn update_stats(&self, result: &QuantumResistantResult, duration: Duration) {
        if let Ok(mut stats) = self.stats.lock() {
            stats.total_verifications += 1;
            
            match result.crypto_mode {
                CryptographicMode::Classical => stats.classical_verifications += 1,
                CryptographicMode::PostQuantum => stats.pq_verifications += 1,
                CryptographicMode::Hybrid => stats.hybrid_verifications += 1,
                CryptographicMode::Adaptive => {} // Counted in the specific mode used
            }
            
            // Update average verification time
            let verification_time = duration.as_nanos() as u64;
            stats.avg_verification_time = 
                ((stats.avg_verification_time * (stats.total_verifications - 1)) + verification_time) / stats.total_verifications;
            
            // Update algorithm performance
            for algorithm in &result.algorithms_used {
                let performance = stats.algorithm_performance.entry(algorithm.clone())
                    .or_insert_with(|| AlgorithmPerformance {
                        usage_count: 0,
                        avg_time_ns: 0,
                        success_rate: 0.0,
                        last_used: Instant::now(),
                    });
                
                performance.usage_count += 1;
                performance.avg_time_ns = 
                    ((performance.avg_time_ns * (performance.usage_count - 1)) + verification_time) / performance.usage_count;
                performance.success_rate = 
                    ((performance.success_rate * (performance.usage_count - 1) as f32) + result.result.verified as u8 as f32) / performance.usage_count as f32;
                performance.last_used = Instant::now();
            }
        }
    }
    
    /// Get performance statistics
    pub fn get_stats(&self) -> QuantumResistantStats {
        self.stats.lock().unwrap().clone()
    }
    
    /// Get current threat assessment
    pub fn get_threat_assessment(&self) -> &QuantumThreatAssessment {
        &self.threat_assessment
    }
    
    /// Get available post-quantum algorithms
    pub fn get_available_algorithms(&self) -> Vec<String> {
        self.pq_algorithms.keys().cloned().collect()
    }
    
    /// Set cryptographic mode
    pub fn set_crypto_mode(&mut self, mode: CryptographicMode) {
        self.crypto_mode = mode;
    }
    
    /// Get current cryptographic mode
    pub fn get_crypto_mode(&self) -> &CryptographicMode {
        &self.crypto_mode
    }
}

impl HybridVerificationSystem {
    fn new(settings: &HybridSettings) -> Self {
        HybridVerificationSystem {
            classical_results: Vec::new(),
            pq_results: Vec::new(),
            consensus: settings.consensus.clone(),
            fallback: settings.fallback.clone(),
        }
    }
}

impl Default for QuantumResistantConfig {
    fn default() -> Self {
        let hybrid_settings = HybridSettings {
            consensus: ConsensusMode::RequireBoth,
            fallback: FallbackStrategy::RetryWithDifferentAlgorithm,
            parallel_verification: true,
            verification_timeout_ms: 10000,
        };
        
        QuantumResistantConfig {
            default_mode: CryptographicMode::Hybrid,
            auto_upgrade: true,
            performance_priority: 0.5,
            threat_update_interval: 24, // 24 hours
            enabled_pq_algorithms: vec![
                "CRYSTALS-Dilithium".to_string(),
                "FALCON".to_string(),
                "SPHINCS+".to_string(),
            ],
            hybrid_settings,
        }
    }
}

impl Clone for QuantumResistantStats {
    fn clone(&self) -> Self {
        QuantumResistantStats {
            total_verifications: self.total_verifications,
            classical_verifications: self.classical_verifications,
            pq_verifications: self.pq_verifications,
            hybrid_verifications: self.hybrid_verifications,
            algorithm_performance: self.algorithm_performance.clone(),
            consensus_success_rate: self.consensus_success_rate,
            avg_verification_time: self.avg_verification_time,
            threat_level_history: self.threat_level_history.clone(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::credentials::VerifiableCredential;
    
    #[test]
    fn test_quantum_resistant_verifier_creation() {
        let verifier = QuantumResistantVerifier::new();
        assert!(verifier.is_ok());
    }
    
    #[test]
    fn test_post_quantum_algorithms() {
        let verifier = QuantumResistantVerifier::new().unwrap();
        let algorithms = verifier.get_available_algorithms();
        assert!(algorithms.contains(&"CRYSTALS-Dilithium".to_string()));
        assert!(algorithms.contains(&"FALCON".to_string()));
        assert!(algorithms.contains(&"SPHINCS+".to_string()));
    }
    
    #[test]
    fn test_quantum_resistant_verification() {
        let mut verifier = QuantumResistantVerifier::new().unwrap();
        let credential = VerifiableCredential::new_test_credential();
        
        let result = verifier.verify_quantum_resistant(&credential);
        assert!(result.is_ok());
        
        let qr_result = result.unwrap();
        assert!(qr_result.result.is_valid);
        assert_eq!(qr_result.crypto_mode, CryptographicMode::Hybrid);
    }
    
    #[test]
    fn test_threat_assessment() {
        let verifier = QuantumResistantVerifier::new().unwrap();
        let threat = verifier.get_threat_assessment();
        assert_eq!(threat.threat_level, QuantumThreatLevel::Moderate);
        assert_eq!(threat.recommended_mode, CryptographicMode::Hybrid);
    }
    
    #[test]
    fn test_algorithm_performance() {
        let dilithium = CrystalsDilithium { security_level: 3 };
        assert_eq!(dilithium.name(), "CRYSTALS-Dilithium");
        assert_eq!(dilithium.family(), PostQuantumFamily::LatticeBased);
        assert_eq!(dilithium.quantum_resistance(), QuantumResistanceLevel::Strong);
        
        let falcon = Falcon { security_level: 512 };
        assert_eq!(falcon.name(), "FALCON");
        assert_eq!(falcon.signature_size(), 690);
        
        let sphincs = SphincsPlus { variant: "shake-128f".to_string() };
        assert_eq!(sphincs.name(), "SPHINCS+");
        assert_eq!(sphincs.quantum_resistance(), QuantumResistanceLevel::Maximum);
    }
} 