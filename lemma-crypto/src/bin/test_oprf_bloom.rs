//! Test OPRF and Bloom filter independently

use lemma_crypto::oprf::OPRFClient;
use lemma_crypto::bloom::CascadedBloomFilter;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("🔍 Testing OPRF and Bloom Filter Components");
    println!("{}", "=".repeat(50));
    
    // Test 1: OPRF Operations
    println!("\n1. Testing OPRF Operations:");
    test_oprf_operations()?;
    
    // Test 2: Bloom Filter Operations  
    println!("\n2. Testing Bloom Filter Operations:");
    test_bloom_filter_operations()?;
    
    // Test 3: Combined OPRF + Bloom (Revocation Check)
    println!("\n3. Testing Combined OPRF + Bloom (Revocation System):");
    test_oprf_bloom_revocation()?;
    
    println!("\n✅ All OPRF and Bloom filter tests passed!");
    Ok(())
}

fn test_oprf_operations() -> Result<(), Box<dyn std::error::Error>> {
    let server_key = [42u8; 32];
    let mut client = OPRFClient::new_with_server_key(server_key);
    
    let credential_id = "test_credential_123";
    
    // Test OPRF evaluation
    let result = client.get_evaluation(credential_id)?;
    println!("  ✓ OPRF evaluation successful");
    println!("  ✓ Result length: {} bytes", result.evaluation.len());
    
    // Test caching
    let result2 = client.get_evaluation(credential_id)?;
    assert_eq!(result.evaluation, result2.evaluation);
    assert!(result2.cached);
    println!("  ✓ OPRF caching works");
    
    // Test cache stats
    println!("  ✓ OPRF caching verified (deterministic results)");
    
    Ok(())
}

fn test_bloom_filter_operations() -> Result<(), Box<dyn std::error::Error>> {
    let mut filter = CascadedBloomFilter::new(3, 1000, 0.01)?;
    
    // Test adding items
    filter.add(b"credential_1")?;
    filter.add(b"credential_2")?;
    filter.add(b"credential_3")?;
    println!("  ✓ Added 3 items to bloom filter");
    
    // Test checking items
    let (found, level) = filter.contains(b"credential_1");
    assert!(found);
    assert_eq!(level, 0);
    println!("  ✓ Found item in bloom filter at level {}", level);
    
    let (found, _) = filter.contains(b"nonexistent");
    assert!(!found);
    println!("  ✓ Correctly identified nonexistent item");
    
    // Test stats
    let stats = filter.cascade_stats();
    println!("  ✓ Bloom filter stats: {} levels", stats.len());
    
    Ok(())
}

fn test_oprf_bloom_revocation() -> Result<(), Box<dyn std::error::Error>> {
    // Create OPRF client for privacy-preserving revocation
    let server_key = [42u8; 32];
    let mut oprf_client = OPRFClient::new_with_server_key(server_key);
    
    // Create Bloom filter for revoked credentials
    let mut revocation_filter = CascadedBloomFilter::new(3, 1000, 0.01)?;
    
    // Simulate some revoked credentials
    let revoked_credentials = vec![
        "revoked_credential_1",
        "revoked_credential_2", 
        "revoked_credential_3"
    ];
    
    println!("  📝 Adding {} revoked credentials to system...", revoked_credentials.len());
    
    // Add revoked credentials using OPRF + Bloom
    for cred_id in &revoked_credentials {
        // Step 1: OPRF evaluation for privacy
        let oprf_result = oprf_client.get_evaluation(cred_id)?;
        
        // Step 2: Add OPRF result to Bloom filter
        revocation_filter.add(&oprf_result.evaluation)?;
        
        println!("    ✓ Revoked: {} (OPRF: {}...)", 
            cred_id, 
            hex::encode(&oprf_result.evaluation[0..8]));
    }
    
    // Test revocation checking
    println!("  🔍 Testing revocation checks...");
    
    // Check revoked credential (should be found)
    let revoked_oprf = oprf_client.get_evaluation("revoked_credential_1")?;
    let (is_revoked, level) = revocation_filter.contains(&revoked_oprf.evaluation);
    assert!(is_revoked);
    println!("    ✓ Revoked credential correctly identified at level {}", level);
    
    // Check valid credential (should NOT be found)
    let valid_oprf = oprf_client.get_evaluation("valid_credential_123")?;
    let (is_revoked, _) = revocation_filter.contains(&valid_oprf.evaluation);
    assert!(!is_revoked);
    println!("    ✓ Valid credential correctly identified as non-revoked");
    
    // Performance test
    println!("  ⚡ Performance testing OPRF + Bloom revocation check...");
    let test_credential = "performance_test_credential";
    
    let mut times = Vec::new();
    for _ in 0..100 {
        let start = std::time::Instant::now();
        
        // Complete revocation check: OPRF + Bloom
        let oprf_result = oprf_client.get_evaluation(test_credential)?;
        let (_, _) = revocation_filter.contains(&oprf_result.evaluation);
        
        times.push(start.elapsed().as_nanos() as u64);
    }
    
    let avg_time = times.iter().sum::<u64>() as f64 / times.len() as f64;
    println!("    ✓ Average OPRF + Bloom check: {:.3} μs", avg_time / 1000.0);
    
    Ok(())
}
