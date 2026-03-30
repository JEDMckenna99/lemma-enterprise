use lemma_crypto::{MinimalCore, MinimalCredential, MinimalIssuer};
use std::collections::HashMap;
use std::result::Result as StdResult;
use std::time::{Duration, Instant};

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
        thresholds.insert("verification_uncached".to_string(), Duration::from_micros(200));
        thresholds.insert("verification_cached".to_string(), Duration::from_micros(80));
        thresholds.insert("batch_verification".to_string(), Duration::from_micros(200));
        Self {
            results: HashMap::new(),
            thresholds,
        }
    }

    pub fn run_all_tests(&mut self) -> StdResult<(), Box<dyn std::error::Error>> {
        println!("Starting performance suite...");
        self.test_cold_start_performance()?;
        self.test_warm_cache_performance()?;
        self.test_batch_performance()?;
        self.generate_report();
        Ok(())
    }

    fn issue_test_credential(&self, suffix: &str) -> StdResult<MinimalCredential, Box<dyn std::error::Error>> {
        let issuer = MinimalIssuer::new();
        let mut claims = HashMap::new();
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert(
            "verificationLevel".to_string(),
            serde_json::Value::String("high".to_string()),
        );
        claims.insert(
            "subjectTag".to_string(),
            serde_json::Value::String(format!("subject_{suffix}")),
        );
        Ok(issuer.issue_credential(format!("did:lemma:{suffix}"), claims)?)
    }

    fn test_cold_start_performance(&mut self) -> StdResult<(), Box<dyn std::error::Error>> {
        let credential = self.issue_test_credential("cold")?;
        let iterations = 20;
        let start = Instant::now();
        for _ in 0..iterations {
            let core = MinimalCore::new();
            let _ = core.verify(&credential)?;
        }
        self.record_result("verification_uncached", start.elapsed(), iterations);
        Ok(())
    }

    fn test_warm_cache_performance(&mut self) -> StdResult<(), Box<dyn std::error::Error>> {
        let credential = self.issue_test_credential("warm")?;
        let core = MinimalCore::new();
        let _ = core.verify(&credential)?;
        let iterations = 2000;
        let start = Instant::now();
        for _ in 0..iterations {
            let _ = core.verify(&credential)?;
        }
        self.record_result("verification_cached", start.elapsed(), iterations);
        Ok(())
    }

    fn test_batch_performance(&mut self) -> StdResult<(), Box<dyn std::error::Error>> {
        let issuer = MinimalIssuer::new();
        let core = MinimalCore::new();
        let mut credentials = Vec::new();
        for i in 0..100 {
            let mut claims = HashMap::new();
            claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
            claims.insert("idx".to_string(), serde_json::Value::String(i.to_string()));
            credentials.push(issuer.issue_credential(format!("did:lemma:user_{i}"), claims)?);
        }
        let iterations = credentials.len() as u32;
        let start = Instant::now();
        for c in &credentials {
            let _ = core.verify(c)?;
        }
        self.record_result("batch_verification", start.elapsed(), iterations);
        Ok(())
    }

    fn record_result(&mut self, test_name: &str, duration: Duration, iterations: u32) {
        let avg_per_iteration = duration / iterations;
        let threshold = self
            .thresholds
            .get(test_name)
            .cloned()
            .unwrap_or(Duration::from_secs(1));
        let passed = avg_per_iteration <= threshold;
        println!(
            "{} {} avg={:.3}us threshold={:.3}us",
            if passed { "PASS" } else { "FAIL" },
            test_name,
            avg_per_iteration.as_nanos() as f64 / 1000.0,
            threshold.as_nanos() as f64 / 1000.0
        );
        self.results.insert(
            test_name.to_string(),
            PerformanceResult {
                test_name: test_name.to_string(),
                duration,
                iterations,
                avg_per_iteration,
                passed,
                threshold,
            },
        );
    }

    fn generate_report(&self) {
        let passed = self.results.values().filter(|r| r.passed).count();
        let failed = self.results.len().saturating_sub(passed);
        println!("Summary: passed={passed} failed={failed}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_performance_suite() {
        let mut suite = PerformanceTestSuite::new();
        suite.run_all_tests().expect("suite should run");
        assert!(!suite.results.is_empty());
    }

    #[test]
    fn test_individual_components() {
        let mut suite = PerformanceTestSuite::new();
        suite
            .test_warm_cache_performance()
            .expect("warm cache should run");
        suite
            .test_cold_start_performance()
            .expect("cold start should run");
        let cached = suite
            .results
            .get("verification_cached")
            .expect("missing cached result");
        let uncached = suite
            .results
            .get("verification_uncached")
            .expect("missing uncached result");
        assert!(
            cached.avg_per_iteration <= uncached.avg_per_iteration,
            "cached should be no slower than uncached"
        );
    }
}