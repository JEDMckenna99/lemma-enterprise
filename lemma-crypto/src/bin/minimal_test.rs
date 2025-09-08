//! Standalone minimal crypto test
//! Tests basic Ed25519 signature verification without dependencies on broken modules

use lemma_crypto::minimal_core::*;
use std::collections::HashMap;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("🔐 MINIMAL LEMMA CRYPTO TEST");
    println!("Testing basic Ed25519 signature verification");
    println!("{}", "=".repeat(50));
    
    // Step 1: Create issuer
    println!("\n1. Creating issuer with Ed25519 keypair...");
    let issuer = MinimalIssuer::new();
    let issuer_did = issuer.did();
    let public_key_hex = issuer.public_key_hex();
    
    println!("✅ Issuer created:");
    println!("   DID: {}", issuer_did);
    println!("   Public Key: {}...{}", &public_key_hex[0..16], &public_key_hex[48..64]);
    
    // Step 2: Create claims
    println!("\n2. Creating credential claims...");
    let mut claims = HashMap::new();
    claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
    claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
    
    println!("✅ Claims created: {:?}", claims);
    
    // Step 3: Issue and sign credential
    println!("\n3. Issuing and signing credential...");
    let subject_did = "did:lemma:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef";
    let credential = issuer.issue_credential(subject_did.to_string(), claims)?;
    
    println!("✅ Credential issued:");
    println!("   ID: {}", credential.id);
    println!("   Issuer: {}", credential.issuer);
    println!("   Subject: {}", credential.subject);
    println!("   Has Proof: {}", credential.proof.is_some());
    
    if let Some(ref proof) = credential.proof {
        println!("   Signature: {}...{}", &proof.signature_value[0..16], &proof.signature_value[112..128]);
    }
    
    // Step 4: Verify signature
    println!("\n4. Verifying Ed25519 signature...");
    let verifier = MinimalCore::new();
    
    let start = std::time::Instant::now();
    let result = verifier.verify(&credential)?;
    let verification_time = start.elapsed();
    
    println!("✅ Verification result:");
    println!("   Verified: {}", result.verified);
    println!("   Time: {} ns ({:.3} μs)", result.verification_time_ns, result.verification_time_ns as f64 / 1000.0);
    println!("   Total Time: {:?}", verification_time);
    
    if !result.verified {
        return Err("❌ Signature verification failed!".into());
    }
    
    // Step 5: Test invalid signature
    println!("\n5. Testing invalid signature detection...");
    let mut invalid_credential = credential.clone();
    if let Some(ref mut proof) = invalid_credential.proof {
        proof.signature_value = "invalid_signature_that_should_fail".to_string();
    }
    
    let invalid_result = match verifier.verify(&invalid_credential) {
        Ok(result) => result,
        Err(e) => {
            println!("✅ Invalid signature correctly rejected: {}", e);
            MinimalVerificationResult {
                verified: false,
                issuer_did: invalid_credential.issuer.clone(),
                verification_time_ns: 0,
            }
        }
    };
    println!("✅ Invalid signature test:");
    println!("   Verified: {} (should be false)", invalid_result.verified);
    
    if invalid_result.verified {
        return Err("❌ Invalid signature was accepted - security failure!".into());
    }
    
    // Step 6: Performance test
    println!("\n6. Performance testing...");
    let num_tests = 1000;
    let mut times = Vec::new();
    
    for _ in 0..num_tests {
        let start = std::time::Instant::now();
        let _ = verifier.verify(&credential)?;
        times.push(start.elapsed().as_nanos() as u64);
    }
    
    let avg_time = times.iter().sum::<u64>() as f64 / times.len() as f64;
    let min_time = *times.iter().min().unwrap();
    let max_time = *times.iter().max().unwrap();
    
    println!("✅ Performance results ({} tests):", num_tests);
    println!("   Average: {:.3} μs", avg_time / 1000.0);
    println!("   Min: {:.3} μs", min_time as f64 / 1000.0);
    println!("   Max: {:.3} μs", max_time as f64 / 1000.0);
    println!("   Throughput: {:.0} verifications/second", 1_000_000_000.0 / avg_time);
    
    println!("\n🏆 MINIMAL CRYPTO TEST PASSED!");
    println!("✅ Real Ed25519 signature verification is working");
    println!("✅ Real DID public key extraction is working");
    println!("✅ Real cryptographic timing measured");
    
    Ok(())
}
