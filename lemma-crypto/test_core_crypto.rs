use lemma_crypto::*;
use std::collections::HashMap;

fn main() {
    println!("🔐 Testing Lemma Core Crypto Components...");
    
    // Test 1: Basic OPRF operations
    println!("\n1. Testing OPRF Operations:");
    test_oprf_operations();
    
    // Test 2: Bloom filter operations  
    println!("\n2. Testing Bloom Filter Operations:");
    test_bloom_filter_operations();
    
    // Test 3: Credential operations
    println!("\n3. Testing Credential Operations:");
    test_credential_operations();
    
    // Test 4: LemmaCore verification
    println!("\n4. Testing LemmaCore Verification:");
    test_lemma_core_verification();
    
    println!("\n✅ All core crypto tests completed successfully!");
}

fn test_oprf_operations() {
    let server_key = [42u8; 32];
    let mut client = oprf::OPRFClient::new_with_server_key(server_key);
    
    let credential_id = "test_credential_123";
    
    // Test OPRF evaluation
    let result = client.get_evaluation(credential_id).unwrap();
    println!("  ✓ OPRF evaluation successful");
    println!("  ✓ Result length: {} bytes", result.evaluation.len());
    
    // Test caching
    let result2 = client.get_evaluation(credential_id).unwrap();
    assert_eq!(result.evaluation, result2.evaluation);
    assert!(result2.cached);
    println!("  ✓ OPRF caching works");
    
    // Test cache stats
    let stats = client.get_cache_stats();
    println!("  ✓ Cache stats: {:?}", stats);
}

fn test_bloom_filter_operations() {
    let mut filter = bloom::CascadedBloomFilter::new(3, 1000, 0.01).unwrap();
    
    // Test adding items
    filter.add(b"credential_1").unwrap();
    filter.add(b"credential_2").unwrap();
    filter.add(b"credential_3").unwrap();
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
}

fn test_credential_operations() {
    let issuer = CredentialIssuer::new();
    
    // Create a credential
    let mut claims = HashMap::new();
    claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
    
    let credential = issuer.issue_credential(
        "did:lemma:test_subject".to_string(),
        claims,
        None,
    ).unwrap();
    
    println!("  ✓ Credential created successfully");
    println!("  ✓ Credential ID: {}", credential.id);
    
    // Test verification
    let is_valid = credential.verify_signature().unwrap();
    assert!(is_valid);
    println!("  ✓ Credential verification successful");
    
    // Test signature verification
    let signature_valid = credential.verify_signature().unwrap();
    assert!(signature_valid);
    println!("  ✓ Credential signature verification successful");
}

fn test_lemma_core_verification() {
    let mut core = LemmaCore::new().unwrap();
    let identity_package = IdentityPackage::new();
    core.register_package(identity_package);
    
    // Create a test credential
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
    
    // Test verification through LemmaCore
    let result = core.verify(&credential).unwrap();
    assert!(result.verified);
    println!("  ✓ LemmaCore verification successful");
    println!("  ✓ Package type: {}", result.package_type);
    println!("  ✓ Confidence: {}", result.confidence);
    println!("  ✓ Offline: {}", result.offline);
    
    // Test revocation
    core.revoke("identity", &credential).unwrap();
    let result = core.verify(&credential).unwrap();
    assert!(!result.verified);
    println!("  ✓ Revocation works correctly");
    
    // Test stats
    let stats = core.get_stats();
    println!("  ✓ LemmaCore stats: registered packages = {}", 
        stats.get("registered_packages").unwrap());
} 