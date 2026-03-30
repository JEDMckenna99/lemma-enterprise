use lemma_crypto::*;
use std::collections::HashMap;
use std::time::Instant;

/// Test the complete lemma_verify function with identity verification
#[test]
fn test_lemma_verify_identity_success() {
    let mut core = LemmaCore::new().unwrap();
    let identity_package = IdentityPackage::new();
    core.register_package(identity_package);

    // Create valid identity credential
    let issuer = CredentialIssuer::new();
    let mut claims = HashMap::new();
    claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
    claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
    claims.insert("verificationMethod".to_string(), serde_json::Value::String("stripe_identity".to_string()));

    let credential = issuer.issue_credential(
        "did:lemma:test_human".to_string(),
        claims,
        None,
    ).unwrap();

    // Verify credential through lemma_verify
    let result = core.verify(&credential).unwrap();
    
    assert!(result.verified, "Identity credential should be verified");
    assert_eq!(result.package_type, "identity");
    assert!(result.confidence > 0.9);
    assert!(result.offline, "Should be offline verification");
    assert_eq!(result.metadata.get("human_verified"), Some(&serde_json::Value::Bool(true)));
}

/// Test lemma_verify with invalid credential signature
#[test]
fn test_lemma_verify_invalid_signature() {
    let mut core = LemmaCore::new().unwrap();
    let identity_package = IdentityPackage::new();
    core.register_package(identity_package);

    let issuer = CredentialIssuer::new();
    let mut claims = HashMap::new();
    claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
    claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));

    let mut credential = issuer.issue_credential(
        "did:lemma:test_human".to_string(),
        claims,
        None,
    ).unwrap();

    // Corrupt the signature
    if let Some(ref mut proof) = credential.proof {
        proof.signature_value = "corrupted_signature".to_string();
    }

    // Verification should fail due to invalid signature
    let result = core.verify(&credential).unwrap();
    assert!(!result.verified, "Credential with corrupted signature should not verify");
}

/// Test lemma_verify with revoked credential
#[test]
fn test_lemma_verify_revoked_credential() {
    let mut core = LemmaCore::new().unwrap();
    let identity_package = IdentityPackage::new();
    core.register_package(identity_package);

    let issuer = CredentialIssuer::new();
    let mut claims = HashMap::new();
    claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
    claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));

    let credential = issuer.issue_credential(
        "did:lemma:test_human".to_string(),
        claims,
        None,
    ).unwrap();

    // First verification should succeed
    let result = core.verify(&credential).unwrap();
    assert!(result.verified, "Initial verification should succeed");

    // Revoke the credential
    core.revoke("identity", &credential).unwrap();

    // Second verification should fail
    let result = core.verify(&credential).unwrap();
    assert!(!result.verified, "Revoked credential should not verify");
}

/// Test OPRF operations for privacy-preserving verification
#[test]
fn test_oprf_privacy_preserving_operations() {
    let server_key = [42u8; 32];
    let mut client = oprf::OPRFClient::new_with_server_key(server_key);
    
    let credential_id = "test_credential_privacy";
    
    // Get OPRF evaluation
    let result = client.get_evaluation(credential_id).unwrap();
    assert_eq!(result.evaluation.len(), 32);
    assert!(!result.cached);
    
    // Same input should produce same output (deterministic)
    let result2 = client.get_evaluation(credential_id).unwrap();
    assert_eq!(result.evaluation, result2.evaluation);
    assert!(result2.cached, "Second evaluation should be cached");
    
    // Different input should produce different output
    let result3 = client.get_evaluation("different_credential").unwrap();
    assert_ne!(result.evaluation, result3.evaluation);
}

/// Test cascaded bloom filter for revocation checking
#[test]
fn test_cascaded_bloom_filter_revocation() {
    let mut filter = bloom::CascadedBloomFilter::new(3, 1000, 0.01).unwrap();
    
    // Test data
    let revoked_items = vec![
        b"revoked_credential_1".as_slice(),
        b"revoked_credential_2".as_slice(),
        b"revoked_credential_3".as_slice(),
    ];
    
    let valid_items = vec![
        b"valid_credential_1".as_slice(),
        b"valid_credential_2".as_slice(),
    ];
    
    // Add revoked items to filter
    for item in &revoked_items {
        filter.add(item).unwrap();
    }
    
    // Check revoked items are detected
    for item in &revoked_items {
        let (is_revoked, level) = filter.contains(item);
        assert!(is_revoked, "Revoked item should be detected");
        assert_eq!(level, 0, "Should be found at most precise level");
    }
    
    // Check valid items are not detected
    for item in &valid_items {
        let (is_revoked, _) = filter.contains(item);
        assert!(!is_revoked, "Valid item should not be detected as revoked");
    }
    
    // Test cascade statistics
    let stats = filter.cascade_stats();
    assert_eq!(stats.len(), 3);
    assert_eq!(stats[0].items_added, 3);
    assert!(stats[0].memory_usage > 0);
}

/// Test performance characteristics of lemma_verify
#[test]
fn test_lemma_verify_performance() {
    let mut core = LemmaCore::new().unwrap();
    let identity_package = IdentityPackage::new();
    core.register_package(identity_package);

    let issuer = CredentialIssuer::new();
    let mut claims = HashMap::new();
    claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
    claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));

    let credential = issuer.issue_credential(
        "did:lemma:perf_test".to_string(),
        claims,
        None,
    ).unwrap();

    // Measure first verification (cold cache)
    let start = Instant::now();
    let result = core.verify(&credential).unwrap();
    let cold_duration = start.elapsed();
    
    assert!(result.verified);
    assert!(!result.cached);
    
    // Measure second verification (warm cache)
    let start = Instant::now();
    let result = core.verify(&credential).unwrap();
    let warm_duration = start.elapsed();
    
    assert!(result.verified);
    assert!(result.cached);
    
    // Warm cache should be significantly faster
    assert!(warm_duration < cold_duration, "Cached verification should be faster");
    
    // Both should be under 10ms (target is <2ms)
    assert!(cold_duration.as_millis() < 10, "Cold verification should be <10ms");
    assert!(warm_duration.as_millis() < 5, "Warm verification should be <5ms");
}

/// Test batch verification performance
#[test]
fn test_batch_verification_performance() {
    let mut core = LemmaCore::new().unwrap();
    let identity_package = IdentityPackage::new();
    core.register_package(identity_package);

    let issuer = CredentialIssuer::new();
    let mut credentials = Vec::new();
    
    // Create 100 test credentials
    for i in 0..100 {
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));

        let credential = issuer.issue_credential(
            format!("did:lemma:batch_test_{}", i),
            claims,
            None,
        ).unwrap();
        credentials.push(credential);
    }

    // Measure batch verification
    let start = Instant::now();
    let results = core.verify_batch(&credentials).unwrap();
    let batch_duration = start.elapsed();
    
    assert_eq!(results.len(), 100);
    assert!(results.iter().all(|r| r.verified));
    
    // Should process 100 credentials in reasonable time
    assert!(batch_duration.as_millis() < 1000, "Batch verification should be <1s for 100 credentials");
    
    let per_credential_ms = batch_duration.as_millis() / 100;
    assert!(per_credential_ms < 10, "Per-credential time should be <10ms");
}

/// Test error handling in lemma_verify
#[test]
fn test_lemma_verify_error_handling() {
    let mut core = LemmaCore::new().unwrap();
    let identity_package = IdentityPackage::new();
    core.register_package(identity_package);

    let issuer = CredentialIssuer::new();
    
    // Test missing packageType claim
    let mut claims = HashMap::new();
    claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    
    let credential = issuer.issue_credential(
        "did:lemma:missing_package".to_string(),
        claims,
        None,
    ).unwrap();

    let result = core.verify(&credential);
    assert!(result.is_err());
    assert!(result.unwrap_err().to_string().contains("Missing packageType claim"));
    
    // Test unsupported package type
    let mut claims = HashMap::new();
    claims.insert("packageType".to_string(), serde_json::Value::String("unsupported".to_string()));
    claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    
    let credential = issuer.issue_credential(
        "did:lemma:unsupported".to_string(),
        claims,
        None,
    ).unwrap();

    let result = core.verify(&credential);
    assert!(result.is_err());
    assert!(result.unwrap_err().to_string().contains("UnsupportedPackageType"));
}

/// Test offline verification capabilities
#[test]
fn test_offline_verification_rate() {
    let mut core = LemmaCore::new().unwrap();
    let identity_package = IdentityPackage::new();
    core.register_package(identity_package);

    let issuer = CredentialIssuer::new();
    let mut offline_count = 0;
    let total_verifications = 100;
    
    // Create and verify multiple credentials
    for i in 0..total_verifications {
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));

        let credential = issuer.issue_credential(
            format!("did:lemma:offline_test_{}", i),
            claims,
            None,
        ).unwrap();
        
        let result = core.verify(&credential).unwrap();
        if result.offline {
            offline_count += 1;
        }
    }
    
    let offline_rate = offline_count as f64 / total_verifications as f64;
    assert!(offline_rate > 0.99, "Offline rate should be >99%, got {}", offline_rate);
}

/// Test concurrent verification safety
#[test]
fn test_concurrent_verification() {
    use std::sync::{Arc, Mutex};
    use std::thread;
    
    let core = Arc::new(Mutex::new(LemmaCore::new().unwrap()));
    let identity_package = IdentityPackage::new();
    core.lock().unwrap().register_package(identity_package);

    let issuer = CredentialIssuer::new();
    let mut claims = HashMap::new();
    claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
    claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));

    let credential = Arc::new(issuer.issue_credential(
        "did:lemma:concurrent_test".to_string(),
        claims,
        None,
    ).unwrap());

    let mut handles = vec![];
    
    // Spawn 10 concurrent verification threads
    for i in 0..10 {
        let core_clone = Arc::clone(&core);
        let credential_clone = Arc::clone(&credential);
        
        let handle = thread::spawn(move || {
            let mut core = core_clone.lock().unwrap();
            let result = core.verify(&credential_clone).unwrap();
            (i, result.verified)
        });
        handles.push(handle);
    }
    
    // Wait for all threads and check results
    for handle in handles {
        let (thread_id, verified) = handle.join().unwrap();
        assert!(verified, "Thread {} verification should succeed", thread_id);
    }
}

/// Test memory usage and cleanup
#[test]
fn test_memory_management() {
    let mut core = LemmaCore::new().unwrap();
    let identity_package = IdentityPackage::new();
    core.register_package(identity_package);

    let issuer = CredentialIssuer::new();
    
    // Create many credentials to fill caches
    for i in 0..1000 {
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));

        let credential = issuer.issue_credential(
            format!("did:lemma:memory_test_{}", i),
            claims,
            None,
        ).unwrap();
        
        core.verify(&credential).unwrap();
    }
    
    // Check stats before cleanup
    let stats_before = core.get_stats();
    let cached_before = stats_before.get("cached_results").unwrap().as_u64().unwrap();
    assert!(cached_before > 0);
    
    // Clear caches
    core.clear_caches();
    
    // Check stats after cleanup
    let stats_after = core.get_stats();
    let cached_after = stats_after.get("cached_results").unwrap().as_u64().unwrap();
    assert_eq!(cached_after, 0);
}

/// Test edge cases and boundary conditions
#[test]
fn test_edge_cases() {
    let mut core = LemmaCore::new().unwrap();
    let identity_package = IdentityPackage::new();
    core.register_package(identity_package);

    let issuer = CredentialIssuer::new();
    
    // Test with minimal claims
    let mut claims = HashMap::new();
    claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
    claims.insert("isHuman".to_string(), serde_json::Value::Bool(false)); // Not human
    
    let credential = issuer.issue_credential(
        "did:lemma:not_human".to_string(),
        claims,
        None,
    ).unwrap();
    
    let result = core.verify(&credential).unwrap();
    assert!(!result.verified, "Non-human credential should not verify");
    assert!(result.confidence < 0.5);
    
    // Test with expired credential
    let mut claims = HashMap::new();
    claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
    claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
    
    let past_timestamp = crate::utils::current_timestamp() - 1000;
    let credential = issuer.issue_credential(
        "did:lemma:expired".to_string(),
        claims,
        Some(past_timestamp),
    ).unwrap();
    
    assert!(credential.is_expired());
    
    // Verification should still work (expiration is checked at application level)
    let result = core.verify(&credential).unwrap();
    assert!(result.verified); // Core crypto doesn't check expiration
}

/// Test statistics and monitoring
#[test]
fn test_verification_stats() {
    let mut core = LemmaCore::new().unwrap();
    let identity_package = IdentityPackage::new();
    core.register_package(identity_package);

    let issuer = CredentialIssuer::new();
    
    // Initial stats
    let stats = core.get_stats();
    assert_eq!(stats.get("registered_packages").unwrap().as_u64().unwrap(), 1);
    assert_eq!(stats.get("cached_results").unwrap().as_u64().unwrap(), 0);
    
    // Verify some credentials
    for i in 0..10 {
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));

        let credential = issuer.issue_credential(
            format!("did:lemma:stats_test_{}", i),
            claims,
            None,
        ).unwrap();
        
        core.verify(&credential).unwrap();
    }
    
    // Check updated stats
    let stats = core.get_stats();
    assert_eq!(stats.get("cached_results").unwrap().as_u64().unwrap(), 10);
    
    // Check OPRF stats
    let oprf_stats = stats.get("oprf_cache_stats").unwrap().as_object().unwrap();
    assert!(oprf_stats.contains_key("cache_size"));
    
    // Check bloom filter stats
    let bloom_stats = stats.get("bloom_stats").unwrap().as_object().unwrap();
    assert!(bloom_stats.contains_key("level_0"));
    assert!(bloom_stats.contains_key("level_1"));
    assert!(bloom_stats.contains_key("level_2"));
} 