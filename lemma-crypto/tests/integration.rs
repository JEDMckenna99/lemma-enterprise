use lemma_crypto::*;
use std::collections::HashMap;

#[test]
fn test_complete_oprf_flow() {
    // Test the complete OPRF flow with client and server
    let server = oprf::OPRFServer::new();
    let client = oprf::OPRFClient::new();
    
    let credential_id = "test_credential_12345";
    
    // 1. Client blinds credential
    let blind_result = client.blind(credential_id).unwrap();
    
    // 2. Server evaluates blinded point
    let evaluated_point = server.evaluate(&blind_result.blinded_point);
    
    // 3. Client unblinds result
    let final_result = client.unblind(&evaluated_point, &blind_result.unblind_scalar);
    
    // Result should be deterministic
    let blind_result2 = client.blind(credential_id).unwrap();
    let evaluated_point2 = server.evaluate(&blind_result2.blinded_point);
    let final_result2 = client.unblind(&evaluated_point2, &blind_result2.unblind_scalar);
    
    assert_eq!(final_result, final_result2);
}

#[test]
fn test_oprf_with_caching() {
    let server_key = [42u8; 32];
    let mut client = oprf::OPRFClient::new_with_server_key(server_key);
    
    let credential_id = "test_credential_caching";
    
    // First evaluation should not be cached
    let result1 = client.get_evaluation(credential_id).unwrap();
    assert!(!result1.cached);
    
    // Second evaluation should be cached
    let result2 = client.get_evaluation(credential_id).unwrap();
    assert!(result2.cached);
    assert_eq!(result1.evaluation, result2.evaluation);
    
    // Check cache stats
    let stats = client.get_cache_stats();
    assert_eq!(stats.get("cache_size"), Some(&1));
}

#[test]
fn test_cascaded_bloom_filter_levels() {
    let mut filter = bloom::CascadedBloomFilter::new(3, 1000, 0.01).unwrap();
    
    // Add items to filter
    let items = vec![
        b"credential_1".as_slice(),
        b"credential_2".as_slice(),
        b"credential_3".as_slice(),
    ];
    
    for item in &items {
        filter.add(item).unwrap();
    }
    
    // Check items are found
    for item in &items {
        let (found, level) = filter.contains(item);
        assert!(found);
        assert_eq!(level, 0); // Should be found at most precise level
    }
    
    // Check unknown item is not found
    let (found, _) = filter.contains(b"unknown_credential");
    assert!(!found);
    
    // Check cascade stats
    let stats = filter.cascade_stats();
    assert_eq!(stats.len(), 3);
    assert_eq!(stats[0].capacity, 1000);
    assert_eq!(stats[1].capacity, 10000);
    assert_eq!(stats[2].capacity, 100000);
}

#[test]
fn test_credential_lifecycle() {
    let issuer = credentials::CredentialIssuer::new();
    
    // Create credential
    let subject = "did:lemma:test_subject".to_string();
    let mut claims = HashMap::new();
    claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
    
    let credential = issuer.issue_credential(subject.clone(), claims, None).unwrap();
    
    // Verify credential properties
    assert_eq!(credential.subject, subject);
    assert_eq!(credential.issuer, issuer.get_did());
    assert!(credential.is_human_verification());
    assert!(credential.proof.is_some());
    
    // Verify signature
    assert!(issuer.verify_credential(&credential).unwrap());
    
    // Test JSON serialization
    let json = credential.to_json().unwrap();
    let deserialized = credentials::VerifiableCredential::from_json(&json).unwrap();
    assert_eq!(credential.id, deserialized.id);
    assert_eq!(credential.subject, deserialized.subject);
    
    // Verify deserialized credential
    assert!(issuer.verify_credential(&deserialized).unwrap());
}

#[test]
fn test_human_verification_credential() {
    let issuer = credentials::CredentialIssuer::new();
    
    let subject = "did:lemma:verified_human".to_string();
    let verification_method = "stripe_identity".to_string();
    
    let credential = issuer.issue_human_verification(
        subject.clone(),
        verification_method.clone(),
        None
    ).unwrap();
    
    // Check human verification properties
    assert!(credential.is_human_verification());
    assert_eq!(credential.get_claim("verificationMethod").unwrap().as_str().unwrap(), verification_method);
    assert_eq!(credential.get_claim("verificationLevel").unwrap().as_str().unwrap(), "high");
    
    // Verify signature
    assert!(issuer.verify_credential(&credential).unwrap());
}

#[test]
fn test_credential_expiration() {
    let issuer = credentials::CredentialIssuer::new();
    let subject = "did:lemma:expiring_credential".to_string();
    
    let mut claims = HashMap::new();
    claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    
    // Create credential that expires in the past
    let past_time = utils::current_timestamp() - 1000;
    let credential = issuer.issue_credential(subject, claims, Some(past_time)).unwrap();
    
    assert!(credential.is_expired());
    
    // Validation should fail for expired credentials
    assert!(credentials::utils::validate_credential(&credential).is_err());
}

#[test]
fn test_integrated_verification_flow() {
    // Set up components
    let server_key = [123u8; 32];
    let mut oprf_client = oprf::OPRFClient::new_with_server_key(server_key);
    let mut bloom_filter = bloom::CascadedBloomFilter::new(3, 10000, 0.01).unwrap();
    let issuer = credentials::CredentialIssuer::new();
    
    // 1. Issue a credential
    let subject = "did:lemma:verified_user".to_string();
    let credential = issuer.issue_human_verification(
        subject,
        "stripe_identity".to_string(),
        None
    ).unwrap();
    
    // 2. Verify credential signature
    assert!(issuer.verify_credential(&credential).unwrap());
    
    // 3. Get OPRF evaluation for credential
    let oprf_result = oprf_client.get_evaluation(&credential.id).unwrap();
    
    // 4. Check revocation status (should not be revoked)
    let (is_revoked, _) = bloom_filter.contains(&oprf_result.evaluation);
    assert!(!is_revoked);
    
    // 5. Revoke the credential
    bloom_filter.add(&oprf_result.evaluation).unwrap();
    
    // 6. Check revocation status again (should now be revoked)
    let (is_revoked, level) = bloom_filter.contains(&oprf_result.evaluation);
    assert!(is_revoked);
    assert_eq!(level, 0); // Should be found at most precise level
    
    // 7. Verify with confidence
    let (is_revoked, level, confidence) = bloom_filter.contains_with_confidence(&oprf_result.evaluation);
    assert!(is_revoked);
    assert_eq!(level, 0);
    assert!(confidence > 0.99); // High confidence
}

#[test]
fn test_batch_operations() {
    let server_key = [200u8; 32];
    let mut oprf_client = oprf::OPRFClient::new_with_server_key(server_key);
    let mut bloom_filter = bloom::CascadedBloomFilter::new(3, 10000, 0.01).unwrap();
    
    // Generate multiple credentials
    let credential_ids: Vec<String> = (0..100)
        .map(|i| format!("credential_{}", i))
        .collect();
    
    // Get OPRF evaluations for all credentials
    let mut oprf_results = Vec::new();
    for credential_id in &credential_ids {
        let result = oprf_client.get_evaluation(credential_id).unwrap();
        oprf_results.push(result.evaluation);
    }
    
    // Batch add to bloom filter
    let item_refs: Vec<&[u8]> = oprf_results.iter().map(|r| r.as_slice()).collect();
    let added_count = bloom_filter.batch_add(&item_refs).unwrap();
    assert_eq!(added_count, 100);
    
    // Batch check all items
    let results = bloom_filter.batch_contains(&item_refs);
    assert_eq!(results.len(), 100);
    
    for (found, level) in results {
        assert!(found);
        assert_eq!(level, 0); // Should be found at most precise level
    }
}

#[test]
fn test_bloom_filter_error_rates() {
    let mut filter = bloom::CascadedBloomFilter::new(3, 1000, 0.01).unwrap();
    
    // Add known items
    let known_items: Vec<Vec<u8>> = (0..500)
        .map(|i| format!("known_item_{}", i).into_bytes())
        .collect();
    
    for item in &known_items {
        filter.add(item).unwrap();
    }
    
    // Test known items (should all be found)
    let mut found_count = 0;
    for item in &known_items {
        let (found, _) = filter.contains(item);
        if found {
            found_count += 1;
        }
    }
    assert_eq!(found_count, known_items.len());
    
    // Test unknown items (should have low false positive rate)
    let unknown_items: Vec<Vec<u8>> = (1000..1500)
        .map(|i| format!("unknown_item_{}", i).into_bytes())
        .collect();
    
    let mut false_positives = 0;
    for item in &unknown_items {
        let (found, _) = filter.contains(item);
        if found {
            false_positives += 1;
        }
    }
    
    let false_positive_rate = false_positives as f64 / unknown_items.len() as f64;
    assert!(false_positive_rate < 0.05); // Should be less than 5%
}

#[test]
fn test_bloom_filter_serialization() {
    let mut original_filter = bloom::CascadedBloomFilter::new(3, 1000, 0.01).unwrap();
    
    // Add some items
    let items = vec![b"item1", b"item2", b"item3"];
    for item in &items {
        original_filter.add(item).unwrap();
    }
    
    // Serialize
    let serialized = bloom::utils::to_bytes(&original_filter.levels[0]).unwrap();
    
    // Deserialize
    let deserialized_filter = bloom::utils::from_bytes(&serialized).unwrap();
    
    // Check items are still found
    for item in &items {
        assert!(deserialized_filter.contains(item));
    }
    
    // Check properties match
    assert_eq!(original_filter.levels[0].capacity(), deserialized_filter.capacity());
    assert_eq!(original_filter.levels[0].len(), deserialized_filter.len());
}

#[test]
fn test_did_operations() {
    let (private_key, public_key) = credentials::generate_keypair();
    let did = credentials::generate_did(&public_key);
    
    // Check DID format
    assert!(did.starts_with("did:lemma:"));
    
    // Parse DID
    let parsed_identifier = credentials::utils::parse_did(&did).unwrap();
    assert!(!parsed_identifier.is_empty());
    
    // Create public key from DID
    let recovered_key = credentials::utils::public_key_from_did(&did).unwrap();
    assert_eq!(public_key.bytes, recovered_key.bytes);
}

#[test]
fn test_signature_operations() {
    let (private_key, public_key) = credentials::generate_keypair();
    let message = b"test message for signing";
    
    // Sign message
    let signature = credentials::sign(&private_key, message);
    
    // Verify signature
    assert!(credentials::verify(&public_key, message, &signature));
    
    // Verify with wrong message should fail
    let wrong_message = b"wrong message";
    assert!(!credentials::verify(&public_key, wrong_message, &signature));
}

#[test]
fn test_performance_requirements() {
    // Test that operations complete within reasonable time
    let start = std::time::Instant::now();
    
    // OPRF operations
    let mut oprf_client = oprf::OPRFClient::new_with_server_key([1u8; 32]);
    for i in 0..100 {
        let credential_id = format!("perf_test_{}", i);
        oprf_client.get_evaluation(&credential_id).unwrap();
    }
    
    let oprf_time = start.elapsed();
    assert!(oprf_time.as_millis() < 1000); // Should complete 100 operations in < 1 second
    
    // Bloom filter operations
    let mut bloom_filter = bloom::CascadedBloomFilter::new(3, 10000, 0.01).unwrap();
    let start = std::time::Instant::now();
    
    for i in 0..1000 {
        let item = format!("bloom_test_{}", i);
        bloom_filter.add(item.as_bytes()).unwrap();
    }
    
    let bloom_time = start.elapsed();
    assert!(bloom_time.as_millis() < 100); // Should complete 1000 operations in < 100ms
}

#[test]
fn test_memory_efficiency() {
    // Test that data structures use reasonable memory
    let bloom_filter = bloom::CascadedBloomFilter::new(3, 10000, 0.01).unwrap();
    let memory_usage = bloom_filter.total_memory_usage();
    
    // Should use less than 1MB for default configuration
    assert!(memory_usage < 1024 * 1024);
    
    // Test memory grows predictably
    let large_filter = bloom::CascadedBloomFilter::new(3, 100000, 0.01).unwrap();
    let large_memory = large_filter.total_memory_usage();
    
    assert!(large_memory > memory_usage);
    assert!(large_memory < 10 * 1024 * 1024); // Should be < 10MB
}

#[test]
fn test_edge_cases() {
    // Test empty strings
    let oprf_client = oprf::OPRFClient::new_with_server_key([1u8; 32]);
    assert!(oprf_client.blind("").is_err());
    
    // Test invalid bloom filter parameters
    assert!(bloom::CascadedBloomFilter::new(0, 1000, 0.01).is_err());
    assert!(bloom::CascadedBloomFilter::new(3, 0, 0.01).is_err());
    assert!(bloom::CascadedBloomFilter::new(3, 1000, 0.0).is_err());
    assert!(bloom::CascadedBloomFilter::new(3, 1000, 1.0).is_err());
    
    // Test invalid credential data
    let issuer = credentials::CredentialIssuer::new();
    let empty_subject = String::new();
    let claims = HashMap::new();
    assert!(issuer.issue_credential(empty_subject, claims, None).is_ok()); // Empty subject should be allowed
    
    // Test invalid DID format
    assert!(credentials::utils::parse_did("invalid:did:format").is_err());
    assert!(credentials::utils::parse_did("did:wrong:identifier").is_err());
}

#[test]
fn test_concurrency_safety() {
    use std::sync::Arc;
    use std::thread;
    
    let server_key = [100u8; 32];
    let oprf_client = Arc::new(std::sync::Mutex::new(oprf::OPRFClient::new_with_server_key(server_key)));
    
    let handles: Vec<_> = (0..10)
        .map(|i| {
            let client = Arc::clone(&oprf_client);
            thread::spawn(move || {
                let credential_id = format!("concurrent_test_{}", i);
                let mut client = client.lock().unwrap();
                client.get_evaluation(&credential_id).unwrap()
            })
        })
        .collect();
    
    // All threads should complete successfully
    for handle in handles {
        handle.join().unwrap();
    }
}

#[test]
fn test_deterministic_behavior() {
    // Test that operations are deterministic
    let server_key = [42u8; 32];
    let credential_id = "deterministic_test";
    
    // OPRF should be deterministic
    let oprf_result1 = {
        let mut client = oprf::OPRFClient::new_with_server_key(server_key);
        client.get_evaluation(credential_id).unwrap()
    };
    
    let oprf_result2 = {
        let mut client = oprf::OPRFClient::new_with_server_key(server_key);
        client.get_evaluation(credential_id).unwrap()
    };
    
    assert_eq!(oprf_result1.evaluation, oprf_result2.evaluation);
    
    // DID generation should be deterministic for same key
    let (_, public_key) = credentials::generate_keypair();
    let did1 = credentials::generate_did(&public_key);
    let did2 = credentials::generate_did(&public_key);
    assert_eq!(did1, did2);
}

#[test]
fn test_compatibility_with_specifications() {
    // Test that implementation matches protocol specifications
    
    // Test cascade levels match specification
    let filter = bloom::CascadedBloomFilter::default_config().unwrap();
    assert_eq!(filter.levels(), constants::DEFAULT_CASCADE_LEVELS);
    
    let stats = filter.cascade_stats();
    assert_eq!(stats[0].capacity, constants::DEFAULT_BASE_CAPACITY);
    assert_eq!(stats[1].capacity, constants::DEFAULT_BASE_CAPACITY * 10);
    assert_eq!(stats[2].capacity, constants::DEFAULT_BASE_CAPACITY * 100);
    
    // Test key sizes match specification
    assert_eq!(constants::SCALAR_SIZE, 32);
    assert_eq!(constants::POINT_SIZE, 32);
    assert_eq!(constants::PUBLIC_KEY_SIZE, 32);
    assert_eq!(constants::PRIVATE_KEY_SIZE, 32);
    assert_eq!(constants::SIGNATURE_SIZE, 64);
    
    // Test DID format matches specification
    let (_, public_key) = credentials::generate_keypair();
    let did = credentials::generate_did(&public_key);
    assert!(did.starts_with("did:lemma:"));
} 