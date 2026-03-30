//! Test Complete Authentication System
//! 
//! Tests the complete system: Ed25519 signature + OPRF revocation
//! This is what REAL authentication should be

use lemma_crypto::complete_verification::*;
use lemma_crypto::minimal_core::*;
use std::collections::HashMap;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("🔐 COMPLETE LEMMA AUTHENTICATION SYSTEM TEST");
    println!("Testing: Ed25519 Signature + OPRF Revocation");
    println!("{}", "=".repeat(60));
    
    // Step 1: Create complete verifier
    println!("\n1. Creating complete verification system...");
    let mut verifier = CompleteVerifier::new()?;
    println!("✅ Complete verifier created (Ed25519 + OPRF + Bloom)");
    
    // Step 2: Create issuer and credentials
    println!("\n2. Creating test credentials...");
    let issuer = MinimalIssuer::new();
    
    let mut claims = HashMap::new();
    claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
    claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
    
    let credential1 = issuer.issue_credential(
        "did:lemma:user_alice".to_string(),
        claims.clone(),
    )?;
    
    let credential2 = issuer.issue_credential(
        "did:lemma:user_bob".to_string(),
        claims.clone(),
    )?;
    
    println!("✅ Created 2 test credentials:");
    println!("   Alice: {}", credential1.id);
    println!("   Bob: {}", credential2.id);
    
    // Step 3: Test valid credentials (both should pass)
    println!("\n3. Testing valid credentials...");
    
    let result1 = verifier.verify_complete(&credential1)?;
    println!("✅ Alice verification:");
    println!("   Verified: {} (signature: {}, not_revoked: {})", 
        result1.verified, result1.signature_valid, result1.not_revoked);
    println!("   Time: {:.3} μs (sig: {:.3} μs, rev: {:.3} μs)",
        result1.verification_time_ns as f64 / 1000.0,
        result1.signature_time_ns as f64 / 1000.0,
        result1.revocation_time_ns as f64 / 1000.0);
    
    assert!(result1.verified);
    assert!(result1.signature_valid);
    assert!(result1.not_revoked);
    
    let result2 = verifier.verify_complete(&credential2)?;
    println!("✅ Bob verification:");
    println!("   Verified: {} (signature: {}, not_revoked: {})", 
        result2.verified, result2.signature_valid, result2.not_revoked);
    
    assert!(result2.verified);
    
    // Step 4: Revoke one credential
    println!("\n4. Testing revocation system...");
    println!("   Revoking Alice's credential...");
    verifier.revoke_credential(&credential1.id)?;
    
    // Step 5: Test revoked credential (should fail)
    let result1_revoked = verifier.verify_complete(&credential1)?;
    println!("✅ Alice after revocation:");
    println!("   Verified: {} (signature: {}, not_revoked: {})", 
        result1_revoked.verified, result1_revoked.signature_valid, result1_revoked.not_revoked);
    
    assert!(!result1_revoked.verified);     // Overall verification fails
    assert!(result1_revoked.signature_valid); // Signature still valid
    assert!(!result1_revoked.not_revoked);    // But revoked
    
    // Step 6: Test Bob still works (should still pass)
    let result2_after_revocation = verifier.verify_complete(&credential2)?;
    println!("✅ Bob after Alice's revocation:");
    println!("   Verified: {} (signature: {}, not_revoked: {})", 
        result2_after_revocation.verified, result2_after_revocation.signature_valid, result2_after_revocation.not_revoked);
    
    assert!(result2_after_revocation.verified); // Bob should still work
    
    // Step 7: Performance testing
    println!("\n5. Performance testing complete authentication...");
    let mut times = Vec::new();
    
    for _ in 0..100 {
        let start = std::time::Instant::now();
        let _ = verifier.verify_complete(&credential2)?;
        times.push(start.elapsed().as_nanos() as u64);
    }
    
    let avg_time = times.iter().sum::<u64>() as f64 / times.len() as f64;
    let min_time = *times.iter().min().unwrap();
    let max_time = *times.iter().max().unwrap();
    
    println!("✅ Complete Authentication Performance (100 tests):");
    println!("   Average: {:.3} μs", avg_time / 1000.0);
    println!("   Min: {:.3} μs", min_time as f64 / 1000.0);
    println!("   Max: {:.3} μs", max_time as f64 / 1000.0);
    println!("   Throughput: {:.0} authentications/second", 1_000_000_000.0 / avg_time);
    
    println!("\n{}", "=".repeat(60));
    println!("🏆 COMPLETE AUTHENTICATION SYSTEM WORKING!");
    println!("✅ Real Ed25519 signature verification");
    println!("✅ Real OPRF privacy-preserving revocation");
    println!("✅ Real Bloom filter revocation checking");
    println!("✅ Complete authentication pipeline functional");
    println!("{}", "=".repeat(60));
    
    Ok(())
}
