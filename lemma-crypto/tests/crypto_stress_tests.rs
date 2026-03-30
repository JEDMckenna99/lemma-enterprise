use lemma_crypto::*;
use std::collections::HashMap;
use std::time::{Duration, Instant};

/// Stress test OPRF operations under heavy load
#[test]
fn stress_test_oprf_operations() {
    let server_key = [123u8; 32];
    let mut client = oprf::OPRFClient::new_with_server_key(server_key);
    
    let iterations = 10000;
    let mut timings = Vec::new();
    
    // Test unique credential IDs
    for i in 0..iterations {
        let credential_id = format!("stress_test_credential_{}", i);
        
        let start = Instant::now();
        let result = client.get_evaluation(&credential_id).unwrap();
        let duration = start.elapsed();
        
        timings.push(duration);
        
        assert_eq!(result.evaluation.len(), 32);
        assert!(!result.cached); // Each should be unique
    }
    
    // Calculate statistics
    let total_time: Duration = timings.iter().sum();
    let avg_time = total_time / iterations as u32;
    let max_time = timings.iter().max().unwrap();
    let min_time = timings.iter().min().unwrap();
    
    println!("OPRF Stress Test Results:");
    println!("  Iterations: {}", iterations);
    println!("  Total time: {:?}", total_time);
    println!("  Average time: {:?}", avg_time);
    println!("  Max time: {:?}", max_time);
    println!("  Min time: {:?}", min_time);
    
    // Performance requirements
    assert!(avg_time < Duration::from_millis(1), "Average OPRF time should be <1ms");
    assert!(max_time < Duration::from_millis(10), "Max OPRF time should be <10ms");
    
    // Test cache performance with repeated IDs
    let test_id = "repeated_credential_id";
    let start = Instant::now();
    let result1 = client.get_evaluation(test_id).unwrap();
    let first_time = start.elapsed();
    
    let start = Instant::now();
    let result2 = client.get_evaluation(test_id).unwrap();
    let cached_time = start.elapsed();
    
    assert_eq!(result1.evaluation, result2.evaluation);
    assert!(!result1.cached);
    assert!(result2.cached);
    assert!(cached_time < first_time, "Cached operation should be faster");
    assert!(cached_time < Duration::from_micros(100), "Cached OPRF should be <100μs");
}

/// Stress test cascaded bloom filter under heavy load
#[test]
fn stress_test_cascaded_bloom_filter() {
    let mut filter = bloom::CascadedBloomFilter::new(3, 100000, 0.001).unwrap();
    
    let num_items = 50000;
    let mut added_items = Vec::new();
    
    // Add many items
    let start = Instant::now();
    for i in 0..num_items {
        let item = format!("item_{}", i);
        let item_bytes = item.as_bytes();
        
        filter.add(item_bytes).unwrap();
        added_items.push(item);
    }
    let add_time = start.elapsed();
    
    // Check all added items are found
    let start = Instant::now();
    for item in &added_items {
        let (found, _level) = filter.contains(item.as_bytes());
        assert!(found, "Added item should be found");
    }
    let check_time = start.elapsed();
    
    // Check false positive rate with random items
    let test_items = 10000;
    let mut false_positives = 0;
    
    let start = Instant::now();
    for i in num_items..(num_items + test_items) {
        let item = format!("test_item_{}", i);
        let (found, _level) = filter.contains(item.as_bytes());
        if found {
            false_positives += 1;
        }
    }
    let false_positive_time = start.elapsed();
    
    let false_positive_rate = false_positives as f64 / test_items as f64;
    
    println!("Cascaded Bloom Filter Stress Test Results:");
    println!("  Items added: {}", num_items);
    println!("  Add time: {:?}", add_time);
    println!("  Check time: {:?}", check_time);
    println!("  False positive time: {:?}", false_positive_time);
    println!("  False positive rate: {:.6}", false_positive_rate);
    
    // Performance requirements
    let avg_add_time = add_time / num_items as u32;
    let avg_check_time = check_time / num_items as u32;
    
    assert!(avg_add_time < Duration::from_micros(10), "Average add time should be <10μs");
    assert!(avg_check_time < Duration::from_micros(5), "Average check time should be <5μs");
    assert!(false_positive_rate < 0.01, "False positive rate should be <1%");
    
    // Check cascade statistics
    let stats = filter.cascade_stats();
    println!("  Cascade stats: {:?}", stats);
    
    assert!(stats[0].items_added > 0);
    assert!(stats[0].memory_usage > 0);
}

/// Stress test lemma verification under concurrent load
#[test]
fn stress_test_concurrent_verification() {
    use std::sync::{Arc, Mutex};
    use std::thread;
    
    let core = Arc::new(Mutex::new(LemmaCore::new().unwrap()));
    let identity_package = IdentityPackage::new();
    core.lock().unwrap().register_package(identity_package);
    
    let issuer = CredentialIssuer::new();
    let num_threads = 10;
    let verifications_per_thread = 100;
    
    // Create test credentials
    let mut credentials = Vec::new();
    for i in 0..(num_threads * verifications_per_thread) {
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
        
        let credential = issuer.issue_credential(
            format!("did:lemma:concurrent_stress_{}", i),
            claims,
            None,
        ).unwrap();
        credentials.push(credential);
    }
    
    let credentials = Arc::new(credentials);
    let mut handles = Vec::new();
    
    let start = Instant::now();
    
    // Spawn concurrent threads
    for thread_id in 0..num_threads {
        let core_clone = Arc::clone(&core);
        let credentials_clone = Arc::clone(&credentials);
        
        let handle = thread::spawn(move || {
            let mut results = Vec::new();
            let start_idx = thread_id * verifications_per_thread;
            let end_idx = start_idx + verifications_per_thread;
            
            for i in start_idx..end_idx {
                let mut core = core_clone.lock().unwrap();
                let result = core.verify(&credentials_clone[i]).unwrap();
                results.push((i, result.verified, result.cached));
            }
            
            (thread_id, results)
        });
        
        handles.push(handle);
    }
    
    // Wait for all threads
    let mut all_results = Vec::new();
    for handle in handles {
        let (thread_id, results) = handle.join().unwrap();
        all_results.extend(results);
        println!("Thread {} completed {} verifications", thread_id, results.len());
    }
    
    let total_time = start.elapsed();
    
    // Verify all results
    assert_eq!(all_results.len(), num_threads * verifications_per_thread);
    let successful_verifications = all_results.iter().filter(|(_, verified, _)| *verified).count();
    let cached_verifications = all_results.iter().filter(|(_, _, cached)| *cached).count();
    
    println!("Concurrent Verification Stress Test Results:");
    println!("  Total verifications: {}", all_results.len());
    println!("  Successful verifications: {}", successful_verifications);
    println!("  Cached verifications: {}", cached_verifications);
    println!("  Total time: {:?}", total_time);
    println!("  Verifications per second: {:.2}", all_results.len() as f64 / total_time.as_secs_f64());
    
    assert_eq!(successful_verifications, all_results.len());
    assert!(total_time < Duration::from_secs(10), "Should complete in <10s");
    
    let throughput = all_results.len() as f64 / total_time.as_secs_f64();
    assert!(throughput > 100.0, "Should achieve >100 verifications/second");
}

/// Test memory usage under heavy load
#[test]
fn stress_test_memory_usage() {
    let mut core = LemmaCore::new().unwrap();
    let identity_package = IdentityPackage::new();
    core.register_package(identity_package);
    
    let issuer = CredentialIssuer::new();
    let num_credentials = 10000;
    
    let start = Instant::now();
    
    // Create and verify many credentials
    for i in 0..num_credentials {
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
        
        let credential = issuer.issue_credential(
            format!("did:lemma:memory_stress_{}", i),
            claims,
            None,
        ).unwrap();
        
        let result = core.verify(&credential).unwrap();
        assert!(result.verified);
        
        // Periodic stats check
        if i % 1000 == 0 {
            let stats = core.get_stats();
            println!("Progress: {} credentials processed", i);
            println!("  Cached results: {}", stats.get("cached_results").unwrap().as_u64().unwrap());
        }
    }
    
    let total_time = start.elapsed();
    
    // Final statistics
    let stats = core.get_stats();
    println!("Memory Stress Test Results:");
    println!("  Total credentials: {}", num_credentials);
    println!("  Total time: {:?}", total_time);
    println!("  Cached results: {}", stats.get("cached_results").unwrap().as_u64().unwrap());
    println!("  OPRF cache size: {}", 
        stats.get("oprf_cache_stats").unwrap().as_object().unwrap()
            .get("cache_size").unwrap().as_u64().unwrap()
    );
    
    // Performance requirements
    let avg_time = total_time / num_credentials as u32;
    assert!(avg_time < Duration::from_millis(5), "Average verification should be <5ms");
    
    // Test cache cleanup
    let cached_before = stats.get("cached_results").unwrap().as_u64().unwrap();
    core.clear_caches();
    let stats_after = core.get_stats();
    let cached_after = stats_after.get("cached_results").unwrap().as_u64().unwrap();
    
    assert!(cached_before > 0);
    assert_eq!(cached_after, 0);
    
    println!("  Cache cleared: {} -> {}", cached_before, cached_after);
}

/// Test cryptographic security properties
#[test]
fn stress_test_crypto_security() {
    let server_key1 = [1u8; 32];
    let server_key2 = [2u8; 32];
    
    let mut client1 = oprf::OPRFClient::new_with_server_key(server_key1);
    let mut client2 = oprf::OPRFClient::new_with_server_key(server_key2);
    
    let test_credentials = 1000;
    
    // Test that different server keys produce different outputs
    for i in 0..test_credentials {
        let credential_id = format!("security_test_credential_{}", i);
        
        let result1 = client1.get_evaluation(&credential_id).unwrap();
        let result2 = client2.get_evaluation(&credential_id).unwrap();
        
        assert_ne!(result1.evaluation, result2.evaluation,
            "Different server keys should produce different outputs");
    }
    
    // Test that same inputs produce same outputs (deterministic)
    let test_id = "deterministic_test";
    let result1 = client1.get_evaluation(test_id).unwrap();
    let result2 = client1.get_evaluation(test_id).unwrap();
    
    assert_eq!(result1.evaluation, result2.evaluation,
        "Same input should produce same output");
    assert!(result2.cached, "Second evaluation should be cached");
    
    // Test output distribution (should appear random)
    let mut outputs = Vec::new();
    for i in 0..1000 {
        let credential_id = format!("distribution_test_{}", i);
        let result = client1.get_evaluation(&credential_id).unwrap();
        outputs.push(result.evaluation);
    }
    
    // Check that all outputs are unique (extremely high probability)
    let mut unique_outputs = outputs.clone();
    unique_outputs.sort();
    unique_outputs.dedup();
    
    assert_eq!(outputs.len(), unique_outputs.len(),
        "All OPRF outputs should be unique");
    
    // Test that outputs look random (simple entropy check)
    let mut bit_counts = [0u32; 256];
    for output in &outputs {
        for &byte in output {
            bit_counts[byte as usize] += 1;
        }
    }
    
    // Each byte value should appear roughly equally often
    let expected_count = (outputs.len() * 32) / 256;
    for (byte_val, &count) in bit_counts.iter().enumerate() {
        let ratio = count as f64 / expected_count as f64;
        assert!(ratio > 0.7 && ratio < 1.3,
            "Byte value {} appears {} times (expected ~{}), ratio: {:.2}",
            byte_val, count, expected_count, ratio);
    }
    
    println!("Cryptographic Security Test Results:");
    println!("  Tested {} credentials", test_credentials);
    println!("  All outputs unique: ✓");
    println!("  Output distribution appears random: ✓");
    println!("  Deterministic behavior: ✓");
}

/// Test revocation under heavy load
#[test]
fn stress_test_revocation_performance() {
    let mut core = LemmaCore::new().unwrap();
    let identity_package = IdentityPackage::new();
    core.register_package(identity_package);
    
    let issuer = CredentialIssuer::new();
    let num_credentials = 1000;
    let revocation_percentage = 0.1; // Revoke 10% of credentials
    
    // Create credentials
    let mut credentials = Vec::new();
    for i in 0..num_credentials {
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
        
        let credential = issuer.issue_credential(
            format!("did:lemma:revocation_stress_{}", i),
            claims,
            None,
        ).unwrap();
        credentials.push(credential);
    }
    
    // Initial verification - all should pass
    let start = Instant::now();
    for credential in &credentials {
        let result = core.verify(credential).unwrap();
        assert!(result.verified);
    }
    let initial_verify_time = start.elapsed();
    
    // Revoke some credentials
    let revocation_count = (num_credentials as f64 * revocation_percentage) as usize;
    let start = Instant::now();
    for i in 0..revocation_count {
        core.revoke("identity", &credentials[i]).unwrap();
    }
    let revocation_time = start.elapsed();
    
    // Verify all credentials again
    let start = Instant::now();
    let mut revoked_found = 0;
    let mut valid_found = 0;
    
    for (i, credential) in credentials.iter().enumerate() {
        let result = core.verify(credential).unwrap();
        if i < revocation_count {
            assert!(!result.verified, "Revoked credential should not verify");
            revoked_found += 1;
        } else {
            assert!(result.verified, "Non-revoked credential should verify");
            valid_found += 1;
        }
    }
    let post_revocation_verify_time = start.elapsed();
    
    println!("Revocation Stress Test Results:");
    println!("  Total credentials: {}", num_credentials);
    println!("  Revoked credentials: {}", revocation_count);
    println!("  Initial verification time: {:?}", initial_verify_time);
    println!("  Revocation time: {:?}", revocation_time);
    println!("  Post-revocation verification time: {:?}", post_revocation_verify_time);
    println!("  Revoked found: {}", revoked_found);
    println!("  Valid found: {}", valid_found);
    
    assert_eq!(revoked_found, revocation_count);
    assert_eq!(valid_found, num_credentials - revocation_count);
    
    // Performance requirements
    let avg_revocation_time = revocation_time / revocation_count as u32;
    assert!(avg_revocation_time < Duration::from_millis(10), "Average revocation should be <10ms");
    
    // Post-revocation verification should be fast
    let avg_post_verify = post_revocation_verify_time / num_credentials as u32;
    assert!(avg_post_verify < Duration::from_millis(5), "Post-revocation verification should be <5ms");
}

/// Test system limits and edge cases
#[test]
fn stress_test_system_limits() {
    let mut core = LemmaCore::new().unwrap();
    let identity_package = IdentityPackage::new();
    core.register_package(identity_package);
    
    let issuer = CredentialIssuer::new();
    
    // Test with very long credential IDs
    let long_id = "a".repeat(10000);
    let mut claims = HashMap::new();
    claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
    claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
    
    let credential = issuer.issue_credential(
        format!("did:lemma:{}", long_id),
        claims,
        None,
    ).unwrap();
    
    let result = core.verify(&credential).unwrap();
    assert!(result.verified, "Long credential ID should work");
    
    // Test with many claims
    let mut many_claims = HashMap::new();
    many_claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
    many_claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    many_claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
    
    for i in 0..1000 {
        many_claims.insert(format!("claim_{}", i), serde_json::Value::String(format!("value_{}", i)));
    }
    
    let credential = issuer.issue_credential(
        "did:lemma:many_claims".to_string(),
        many_claims,
        None,
    ).unwrap();
    
    let result = core.verify(&credential).unwrap();
    assert!(result.verified, "Credential with many claims should work");
    
    // Test rapid succession
    let rapid_count = 10000;
    let start = Instant::now();
    
    for i in 0..rapid_count {
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
        
        let credential = issuer.issue_credential(
            format!("did:lemma:rapid_{}", i),
            claims,
            None,
        ).unwrap();
        
        let result = core.verify(&credential).unwrap();
        assert!(result.verified);
    }
    
    let rapid_time = start.elapsed();
    let ops_per_second = rapid_count as f64 / rapid_time.as_secs_f64();
    
    println!("System Limits Test Results:");
    println!("  Long credential ID: ✓");
    println!("  Many claims (1000): ✓");
    println!("  Rapid succession ({} ops): ✓", rapid_count);
    println!("  Operations per second: {:.2}", ops_per_second);
    
    assert!(ops_per_second > 500.0, "Should achieve >500 ops/second");
} 