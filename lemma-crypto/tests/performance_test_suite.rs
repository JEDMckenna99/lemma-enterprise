use lemma_crypto::*;
use std::time::{Duration, Instant};
use std::collections::HashMap;

/// Performance test suite for continuous monitoring
/// Runs under various conditions to detect performance regressions
pub struct PerformanceTestSuite {
    results: HashMap<String, PerformanceResult>,
    thresholds: HashMap<String, Duration>,
}

#[derive(Debug, Clone)]
pub struct PerformanceResult {
    pub test_name: String,
    pub duration: Duration,
    pub iterations: u32,
    pub avg_per_iteration: Duration,
    pub passed: bool,
    pub threshold: Duration,
}

impl PerformanceTestSuite {
    pub fn new() -> Self {
        let mut thresholds = HashMap::new();
        
        // Define performance thresholds based on validated benchmarks
        thresholds.insert("verification_cached".to_string(), Duration::from_nanos(500_000)); // 0.5ms
        thresholds.insert("verification_uncached".to_string(), Duration::from_micros(200)); // 200µs
        thresholds.insert("full_flow_cached".to_string(), Duration::from_micros(50)); // 50µs
        thresholds.insert("full_flow_uncached".to_string(), Duration::from_micros(200)); // 200µs
        thresholds.insert("credential_generation".to_string(), Duration::from_micros(30)); // 30µs
        thresholds.insert("oprf_evaluation".to_string(), Duration::from_micros(100)); // 100µs
        thresholds.insert("bloom_filter_check".to_string(), Duration::from_micros(5)); // 5µs
        thresholds.insert("serialization".to_string(), Duration::from_micros(2)); // 2µs
        
        Self {
            results: HashMap::new(),
            thresholds,
        }
    }
    
    /// Run all performance tests
    pub fn run_all_tests(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        println!("🚀 Starting Performance Test Suite");
        println!("==================================");
        
        // Test 1: Cold start performance
        self.test_cold_start_performance()?;
        
        // Test 2: Warm cache performance
        self.test_warm_cache_performance()?;
        
        // Test 3: Different credential types
        self.test_credential_type_performance()?;
        
        // Test 4: Batch operations
        self.test_batch_performance()?;
        
        // Test 5: Memory pressure conditions
        self.test_memory_pressure_performance()?;
        
        // Test 6: Concurrent operations
        self.test_concurrent_performance()?;
        
        // Test 7: Edge cases
        self.test_edge_case_performance()?;
        
        // Generate summary report
        self.generate_report();
        
        Ok(())
    }
    
    /// Test cold start performance (no cache)
    fn test_cold_start_performance(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        println!("📊 Testing Cold Start Performance...");
        
        // Create fresh core instance
        let core = LemmaCore::new();
        let issuer = CredentialIssuer::new();
        
        // Create test credential
        let mut claims = HashMap::new();
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
        
        let credential = issuer.issue_credential(
            "test_subject".to_string(),
            claims,
            None,
        )?;
        
        // Measure cold start verification
        let start = Instant::now();
        let iterations = 10;
        
        for _ in 0..iterations {
            let fresh_core = LemmaCore::new();
            fresh_core.verify(&credential)?;
        }
        
        let duration = start.elapsed();
        self.record_result("verification_uncached", duration, iterations);
        
        Ok(())
    }
    
    /// Test warm cache performance
    fn test_warm_cache_performance(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        println!("🔥 Testing Warm Cache Performance...");
        
        let core = LemmaCore::new();
        let issuer = CredentialIssuer::new();
        
        // Create test credential
        let mut claims = HashMap::new();
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
        
        let credential = issuer.issue_credential(
            "test_subject".to_string(),
            claims,
            None,
        )?;
        
        // Warm up cache
        core.verify(&credential)?;
        
        // Measure warm cache verification
        let start = Instant::now();
        let iterations = 1000;
        
        for _ in 0..iterations {
            core.verify(&credential)?;
        }
        
        let duration = start.elapsed();
        self.record_result("verification_cached", duration, iterations);
        
        Ok(())
    }
    
    /// Test performance across different credential types
    fn test_credential_type_performance(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        println!("🎭 Testing Credential Type Performance...");
        
        let core = LemmaCore::new();
        let issuer = CredentialIssuer::new();
        
        // Test different credential types
        let credential_types = vec![
            ("identity", vec![
                ("isHuman", serde_json::Value::Bool(true)),
                ("verificationLevel", serde_json::Value::String("high".to_string())),
            ]),
            ("ticket", vec![
                ("eventId", serde_json::Value::String("event_123".to_string())),
                ("seatNumber", serde_json::Value::String("A1".to_string())),
                ("ticketHash", serde_json::Value::String("hash_123".to_string())),
            ]),
            ("package_authenticity", vec![
                ("productId", serde_json::Value::String("product_123".to_string())),
                ("manufacturerDID", serde_json::Value::String("did:lemma:manufacturer".to_string())),
                ("batchNumber", serde_json::Value::String("batch_123".to_string())),
            ]),
        ];
        
        for (cred_type, claims_data) in credential_types {
            let mut claims = HashMap::new();
            claims.insert("packageType".to_string(), serde_json::Value::String(cred_type.to_string()));
            
            for (key, value) in claims_data {
                claims.insert(key.to_string(), value);
            }
            
            let credential = issuer.issue_credential(
                "test_subject".to_string(),
                claims,
                None,
            )?;
            
            // Warm up
            core.verify(&credential)?;
            
            // Measure performance
            let start = Instant::now();
            let iterations = 100;
            
            for _ in 0..iterations {
                core.verify(&credential)?;
            }
            
            let duration = start.elapsed();
            self.record_result(&format!("{}_performance", cred_type), duration, iterations);
        }
        
        Ok(())
    }
    
    /// Test batch operation performance
    fn test_batch_performance(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        println!("📦 Testing Batch Performance...");
        
        let core = LemmaCore::new();
        let issuer = CredentialIssuer::new();
        
        // Create multiple credentials
        let mut credentials = Vec::new();
        for i in 0..100 {
            let mut claims = HashMap::new();
            claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
            claims.insert("userId".to_string(), serde_json::Value::String(format!("user_{}", i)));
            
            let credential = issuer.issue_credential(
                format!("test_subject_{}", i),
                claims,
                None,
            )?;
            
            credentials.push(credential);
        }
        
        // Warm up
        for credential in &credentials[0..10] {
            core.verify(credential)?;
        }
        
        // Measure batch verification
        let start = Instant::now();
        let iterations = credentials.len() as u32;
        
        for credential in &credentials {
            core.verify(credential)?;
        }
        
        let duration = start.elapsed();
        self.record_result("batch_verification", duration, iterations);
        
        Ok(())
    }
    
    /// Test performance under memory pressure
    fn test_memory_pressure_performance(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        println!("🧠 Testing Memory Pressure Performance...");
        
        let core = LemmaCore::new();
        let issuer = CredentialIssuer::new();
        
        // Create test credential
        let mut claims = HashMap::new();
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
        
        let credential = issuer.issue_credential(
            "test_subject".to_string(),
            claims,
            None,
        )?;
        
        // Allocate memory to simulate pressure
        let _memory_pressure: Vec<Vec<u8>> = (0..1000)
            .map(|_| vec![0u8; 1024 * 1024]) // 1MB each
            .collect();
        
        // Warm up
        core.verify(&credential)?;
        
        // Measure performance under memory pressure
        let start = Instant::now();
        let iterations = 100;
        
        for _ in 0..iterations {
            core.verify(&credential)?;
        }
        
        let duration = start.elapsed();
        self.record_result("memory_pressure", duration, iterations);
        
        Ok(())
    }
    
    /// Test concurrent operation performance
    fn test_concurrent_performance(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        println!("🔄 Testing Concurrent Performance...");
        
        let core = std::sync::Arc::new(LemmaCore::new());
        let issuer = CredentialIssuer::new();
        
        // Create test credential
        let mut claims = HashMap::new();
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
        
        let credential = std::sync::Arc::new(issuer.issue_credential(
            "test_subject".to_string(),
            claims,
            None,
        )?);
        
        // Warm up
        core.verify(&credential)?;
        
        // Measure concurrent performance
        let start = Instant::now();
        let iterations = 100;
        let num_threads = 4;
        
        let handles: Vec<_> = (0..num_threads)
            .map(|_| {
                let core = core.clone();
                let credential = credential.clone();
                let thread_iterations = iterations / num_threads;
                
                std::thread::spawn(move || {
                    for _ in 0..thread_iterations {
                        core.verify(&credential).unwrap();
                    }
                })
            })
            .collect();
        
        for handle in handles {
            handle.join().unwrap();
        }
        
        let duration = start.elapsed();
        self.record_result("concurrent_verification", duration, iterations);
        
        Ok(())
    }
    
    /// Test edge case performance
    fn test_edge_case_performance(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        println!("🔍 Testing Edge Case Performance...");
        
        let core = LemmaCore::new();
        let issuer = CredentialIssuer::new();
        
        // Test with large claims
        let mut large_claims = HashMap::new();
        large_claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        large_claims.insert("largeData".to_string(), 
            serde_json::Value::String("x".repeat(10000))); // 10KB of data
        
        let large_credential = issuer.issue_credential(
            "test_subject".to_string(),
            large_claims,
            None,
        )?;
        
        // Warm up
        core.verify(&large_credential)?;
        
        // Measure large credential performance
        let start = Instant::now();
        let iterations = 50;
        
        for _ in 0..iterations {
            core.verify(&large_credential)?;
        }
        
        let duration = start.elapsed();
        self.record_result("large_credential", duration, iterations);
        
        Ok(())
    }
    
    /// Record a performance result
    fn record_result(&mut self, test_name: &str, duration: Duration, iterations: u32) {
        let avg_per_iteration = duration / iterations;
        let threshold = self.thresholds.get(test_name)
            .unwrap_or(&Duration::from_secs(1))
            .clone();
        let passed = avg_per_iteration <= threshold;
        
        let result = PerformanceResult {
            test_name: test_name.to_string(),
            duration,
            iterations,
            avg_per_iteration,
            passed,
            threshold,
        };
        
        // Print immediate result
        let status = if passed { "✅ PASS" } else { "❌ FAIL" };
        println!("  {} {}: {:.3}µs (threshold: {:.3}µs)", 
            status, test_name, 
            avg_per_iteration.as_nanos() as f64 / 1000.0,
            threshold.as_nanos() as f64 / 1000.0
        );
        
        self.results.insert(test_name.to_string(), result);
    }
    
    /// Generate comprehensive performance report
    fn generate_report(&self) {
        println!("\n📊 Performance Test Suite Report");
        println!("=====================================");
        
        let mut passed = 0;
        let mut failed = 0;
        
        for result in self.results.values() {
            if result.passed {
                passed += 1;
            } else {
                failed += 1;
            }
        }
        
        println!("📈 Summary: {} passed, {} failed", passed, failed);
        println!();
        
        // Detailed results
        println!("🔍 Detailed Results:");
        for result in self.results.values() {
            let status = if result.passed { "✅" } else { "❌" };
            println!("  {} {}: {:.3}µs/{:.3}µs (avg: {:.3}µs, {} iterations)",
                status,
                result.test_name,
                result.avg_per_iteration.as_nanos() as f64 / 1000.0,
                result.threshold.as_nanos() as f64 / 1000.0,
                result.duration.as_nanos() as f64 / 1000.0 / result.iterations as f64,
                result.iterations
            );
        }
        
        // Performance insights
        println!("\n💡 Performance Insights:");
        
        // Find fastest and slowest operations
        let mut sorted_results: Vec<_> = self.results.values().collect();
        sorted_results.sort_by(|a, b| a.avg_per_iteration.cmp(&b.avg_per_iteration));
        
        if let Some(fastest) = sorted_results.first() {
            println!("  🚀 Fastest operation: {} ({:.3}µs)", 
                fastest.test_name, 
                fastest.avg_per_iteration.as_nanos() as f64 / 1000.0
            );
        }
        
        if let Some(slowest) = sorted_results.last() {
            println!("  🐌 Slowest operation: {} ({:.3}µs)", 
                slowest.test_name, 
                slowest.avg_per_iteration.as_nanos() as f64 / 1000.0
            );
        }
        
        // Calculate throughput
        if let Some(cached_result) = self.results.get("verification_cached") {
            let throughput = 1_000_000.0 / cached_result.avg_per_iteration.as_nanos() as f64;
            println!("  📊 Verification throughput: {:.0} ops/sec", throughput);
        }
        
        println!("\n{} Overall Status: {}", 
            if failed == 0 { "✅" } else { "❌" },
            if failed == 0 { "ALL TESTS PASSED" } else { "SOME TESTS FAILED" }
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_performance_suite() {
        let mut suite = PerformanceTestSuite::new();
        
        // This test should pass in development
        // In CI, you might want to use different thresholds
        match suite.run_all_tests() {
            Ok(_) => println!("Performance test suite completed"),
            Err(e) => panic!("Performance test suite failed: {}", e),
        }
    }
    
    #[test]
    fn test_individual_components() {
        let mut suite = PerformanceTestSuite::new();
        
        // Test individual components
        suite.test_warm_cache_performance().unwrap();
        suite.test_cold_start_performance().unwrap();
        
        // Verify we have results
        assert!(suite.results.len() >= 2);
        
        // Check that cached is faster than uncached
        let cached = suite.results.get("verification_cached").unwrap();
        let uncached = suite.results.get("verification_uncached").unwrap();
        
        assert!(cached.avg_per_iteration < uncached.avg_per_iteration,
            "Cached verification should be faster than uncached");
    }
} 