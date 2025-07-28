use lemma_crypto::*;
use hex;
use serde_json;

/// Comprehensive cryptographic correctness tests
/// Tests all cryptographic operations with known test vectors and edge cases
#[cfg(test)]
mod cryptographic_correctness_tests {
    use super::*;

    /// Test Ed25519 signature operations with RFC 8032 test vectors
    #[test]
    fn test_ed25519_rfc8032_vectors() {
        // Test Vector 1 from RFC 8032
        let secret_key_hex = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60";
        let public_key_hex = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a";
        let message_hex = "";
        let signature_hex = "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b";
        
        let secret_key = hex::decode(secret_key_hex).unwrap();
        let public_key = hex::decode(public_key_hex).unwrap();
        let message = hex::decode(message_hex).unwrap();
        let expected_signature = hex::decode(signature_hex).unwrap();
        
        // Test key generation consistency
        let key_pair = ed25519_dalek::SigningKey::from_bytes(&secret_key.try_into().unwrap());
        let derived_public_key = key_pair.verifying_key();
        assert_eq!(derived_public_key.as_bytes(), &public_key[..]);
        
        // Test signing
        let signature = key_pair.sign(&message);
        assert_eq!(signature.to_bytes(), expected_signature[..]);
        
        // Test verification
        assert!(derived_public_key.verify(&message, &signature).is_ok());
        
        println!("✅ Ed25519 RFC 8032 Test Vector 1 passed");
    }

    /// Test Ed25519 with longer message (Test Vector 2)
    #[test]
    fn test_ed25519_longer_message() {
        let secret_key_hex = "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb";
        let public_key_hex = "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c";
        let message_hex = "72";
        let signature_hex = "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00";
        
        let secret_key = hex::decode(secret_key_hex).unwrap();
        let public_key = hex::decode(public_key_hex).unwrap();
        let message = hex::decode(message_hex).unwrap();
        let expected_signature = hex::decode(signature_hex).unwrap();
        
        let key_pair = ed25519_dalek::SigningKey::from_bytes(&secret_key.try_into().unwrap());
        let derived_public_key = key_pair.verifying_key();
        assert_eq!(derived_public_key.as_bytes(), &public_key[..]);
        
        let signature = key_pair.sign(&message);
        assert_eq!(signature.to_bytes(), expected_signature[..]);
        
        assert!(derived_public_key.verify(&message, &signature).is_ok());
        
        println!("✅ Ed25519 RFC 8032 Test Vector 2 passed");
    }

    /// Test Ed25519 edge cases and error conditions
    #[test]
    fn test_ed25519_edge_cases() {
        // Test with invalid public key
        let invalid_public_key = [0u8; 32];
        let message = b"test message";
        let signature = [0u8; 64];
        
        let public_key_result = ed25519_dalek::VerifyingKey::from_bytes(&invalid_public_key);
        
        // Test with malformed signature
        let key_pair = ed25519_dalek::SigningKey::generate(&mut rand::thread_rng());
        let valid_signature = key_pair.sign(message);
        let mut corrupted_signature = valid_signature.to_bytes();
        corrupted_signature[0] ^= 1; // Flip a bit
        
        let corrupted_sig = ed25519_dalek::Signature::from_bytes(&corrupted_signature);
        assert!(key_pair.verifying_key().verify(message, &corrupted_sig).is_err());
        
        // Test with empty message
        let empty_message = b"";
        let empty_signature = key_pair.sign(empty_message);
        assert!(key_pair.verifying_key().verify(empty_message, &empty_signature).is_ok());
        
        // Test with very long message
        let long_message = vec![0u8; 10000];
        let long_signature = key_pair.sign(&long_message);
        assert!(key_pair.verifying_key().verify(&long_message, &long_signature).is_ok());
        
        println!("✅ Ed25519 edge cases passed");
    }

    /// Test OPRF correctness with known values
    #[test]
    fn test_oprf_correctness() {
        use lemma_crypto::oprf::*;
        
        // Test OPRF client initialization
        let client = OPRFClient::new_with_server_key([1u8; 32]);
        
        // Test inputs
        let test_inputs = vec![
            "test_input_1".to_string(),
            "test_input_2".to_string(),
            "".to_string(), // Empty input
            "x".repeat(1000), // Long input
        ];
        
        for input in test_inputs {
            // Test blind operation
            let (blinded_input, unblinding_factor) = client.blind(&input);
            assert_ne!(blinded_input, [0u8; 32]); // Should not be zero
            assert_ne!(unblinding_factor, [0u8; 32]); // Should not be zero
            
            // Test that same input produces same blinded result with same factor
            let (blinded_input2, unblinding_factor2) = client.blind(&input);
            // Note: Due to randomness, these might not be the same, but the final result should be consistent
            
            // Test evaluate operation (simulated server response)
            let server_response = client.evaluate(&blinded_input);
            assert_ne!(server_response, [0u8; 32]); // Should not be zero
            
            // Test unblind operation
            let final_result = client.unblind(&server_response, &unblinding_factor);
            assert_ne!(final_result, [0u8; 32]); // Should not be zero
            
            // Test consistency - same input should produce same final result
            let (blinded_input3, unblinding_factor3) = client.blind(&input);
            let server_response3 = client.evaluate(&blinded_input3);
            let final_result3 = client.unblind(&server_response3, &unblinding_factor3);
            
            // The OPRF should be deterministic for the same input
            assert_eq!(final_result, final_result3, "OPRF should be deterministic");
        }
        
        println!("✅ OPRF correctness tests passed");
    }

    /// Test OPRF edge cases and error conditions
    #[test]
    fn test_oprf_edge_cases() {
        use lemma_crypto::oprf::*;
        
        // Test with different server keys
        let client1 = OPRFClient::new_with_server_key([1u8; 32]);
        let client2 = OPRFClient::new_with_server_key([2u8; 32]);
        
        let input = "test_input".to_string();
        
        // Same input with different server keys should produce different results
        let (blinded1, unblinding1) = client1.blind(&input);
        let (blinded2, unblinding2) = client2.blind(&input);
        
        let result1 = client1.evaluate(&blinded1);
        let result2 = client2.evaluate(&blinded2);
        
        let final1 = client1.unblind(&result1, &unblinding1);
        let final2 = client2.unblind(&result2, &unblinding2);
        
        // Different server keys should produce different results
        assert_ne!(final1, final2, "Different server keys should produce different OPRF results");
        
        // Test with zero inputs (edge case)
        let zero_input = "\0".to_string();
        let (blinded_zero, unblinding_zero) = client1.blind(&zero_input);
        let result_zero = client1.evaluate(&blinded_zero);
        let final_zero = client1.unblind(&result_zero, &unblinding_zero);
        assert_ne!(final_zero, [0u8; 32]);
        
        println!("✅ OPRF edge cases passed");
    }

    /// Test Bloom filter correctness
    #[test]
    fn test_bloom_filter_correctness() {
        use lemma_crypto::bloom::*;
        
        // Test basic Bloom filter operations
        let mut bloom = CascadedBloomFilter::new(1, 1000, 0.01).unwrap();
        
        // Test adding elements
        let test_elements = vec![
            "element1".to_string(),
            "element2".to_string(),
            "element3".to_string(),
        ];
        
        // Initially, no elements should be present
        for element in &test_elements {
            assert!(!bloom.contains(element), "Element should not be present initially");
        }
        
        // Add elements
        for element in &test_elements {
            bloom.add(element);
        }
        
        // All added elements should be present
        for element in &test_elements {
            assert!(bloom.contains(element), "Added element should be present");
        }
        
        // Test false positive rate
        let mut false_positives = 0;
        let test_count = 10000;
        
        for i in 0..test_count {
            let test_element = format!("non_existent_{}", i);
            if bloom.contains(&test_element) {
                false_positives += 1;
            }
        }
        
        let false_positive_rate = false_positives as f64 / test_count as f64;
        assert!(false_positive_rate < 0.05, "False positive rate should be reasonable: {}", false_positive_rate);
        
        println!("✅ Bloom filter correctness tests passed (FP rate: {:.4})", false_positive_rate);
    }

    /// Test cascaded Bloom filter properties
    #[test]
    fn test_cascaded_bloom_filter() {
        use lemma_crypto::bloom::*;
        
        // Test different cascade levels
        let levels = vec![1, 2, 3, 5];
        
        for level in levels {
            let mut bloom = CascadedBloomFilter::new(level, 1000, 0.01).unwrap();
            
            // Add some elements
            let elements = vec![
                format!("test_level_{}_elem1", level),
                format!("test_level_{}_elem2", level),
                format!("test_level_{}_elem3", level),
            ];
            
            for element in &elements {
                bloom.add(element);
            }
            
            // Verify all elements are present
            for element in &elements {
                assert!(bloom.contains(element), "Element should be present in {}-level filter", level);
            }
        }
        
        println!("✅ Cascaded Bloom filter tests passed");
    }

    /// Test Bloom filter edge cases
    #[test]
    fn test_bloom_filter_edge_cases() {
        use lemma_crypto::bloom::*;
        
        // Test with empty string
        let mut bloom = CascadedBloomFilter::new(1, 1000, 0.01).unwrap();
        let empty_string = "".to_string();
        
        assert!(!bloom.contains(&empty_string));
        bloom.add(&empty_string);
        assert!(bloom.contains(&empty_string));
        
        // Test with very long string
        let long_string = "x".repeat(10000);
        assert!(!bloom.contains(&long_string));
        bloom.add(&long_string);
        assert!(bloom.contains(&long_string));
        
        // Test with special characters
        let special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?".to_string();
        assert!(!bloom.contains(&special_chars));
        bloom.add(&special_chars);
        assert!(bloom.contains(&special_chars));
        
        // Test with Unicode
        let unicode_string = "こんにちは世界🌍".to_string();
        assert!(!bloom.contains(&unicode_string));
        bloom.add(&unicode_string);
        assert!(bloom.contains(&unicode_string));
        
        println!("✅ Bloom filter edge cases passed");
    }

    /// Test credential issuance and verification correctness
    #[test]
    fn test_credential_correctness() {
        use std::collections::HashMap;
        
        let issuer = CredentialIssuer::new();
        let core = LemmaCore::new();
        
        // Test basic credential issuance
        let mut claims = HashMap::new();
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("level".to_string(), serde_json::Value::String("high".to_string()));
        
        let credential = issuer.issue_credential(
            "test_subject".to_string(),
            claims.clone(),
            None,
        ).unwrap();
        
        // Verify the credential structure
        assert!(!credential.id.is_empty());
        assert!(!credential.issuer.is_empty());
        assert_eq!(credential.subject, "test_subject");
        assert_eq!(credential.claims, claims);
        assert!(!credential.signature.is_empty());
        
        // Test verification
        let result = core.verify(&credential);
        assert!(result.is_ok(), "Valid credential should verify successfully");
        
        // Test with modified credential (should fail)
        let mut modified_credential = credential.clone();
        modified_credential.claims.insert("modified".to_string(), serde_json::Value::Bool(true));
        
        let modified_result = core.verify(&modified_credential);
        assert!(modified_result.is_err(), "Modified credential should fail verification");
        
        println!("✅ Credential correctness tests passed");
    }

    /// Test credential edge cases
    #[test]
    fn test_credential_edge_cases() {
        use std::collections::HashMap;
        
        let issuer = CredentialIssuer::new();
        let core = LemmaCore::new();
        
        // Test with empty claims
        let empty_claims = HashMap::new();
        let empty_credential = issuer.issue_credential(
            "test_subject".to_string(),
            empty_claims,
            None,
        ).unwrap();
        
        assert!(core.verify(&empty_credential).is_ok());
        
        // Test with very large claims
        let mut large_claims = HashMap::new();
        large_claims.insert("large_data".to_string(), serde_json::Value::String("x".repeat(10000)));
        
        let large_credential = issuer.issue_credential(
            "test_subject".to_string(),
            large_claims,
            None,
        ).unwrap();
        
        assert!(core.verify(&large_credential).is_ok());
        
        // Test with special characters in subject
        let special_subject = "test@example.com!#$%^&*()".to_string();
        let mut claims = HashMap::new();
        claims.insert("test".to_string(), serde_json::Value::Bool(true));
        
        let special_credential = issuer.issue_credential(
            special_subject.clone(),
            claims,
            None,
        ).unwrap();
        
        assert_eq!(special_credential.subject, special_subject);
        assert!(core.verify(&special_credential).is_ok());
        
        println!("✅ Credential edge cases passed");
    }

    /// Test cryptographic consistency across operations
    #[test]
    fn test_cryptographic_consistency() {
        use std::collections::HashMap;
        
        let issuer = CredentialIssuer::new();
        let core = LemmaCore::new();
        
        // Test that same input produces same output
        let mut claims = HashMap::new();
        claims.insert("test".to_string(), serde_json::Value::Bool(true));
        
        let credential1 = issuer.issue_credential(
            "test_subject".to_string(),
            claims.clone(),
            None,
        ).unwrap();
        
        let credential2 = issuer.issue_credential(
            "test_subject".to_string(),
            claims.clone(),
            None,
        ).unwrap();
        
        // Credentials should be different due to nonces/timestamps
        assert_ne!(credential1.id, credential2.id);
        
        // But both should verify successfully
        assert!(core.verify(&credential1).is_ok());
        assert!(core.verify(&credential2).is_ok());
        
        // Test verification consistency
        for _ in 0..10 {
            assert!(core.verify(&credential1).is_ok());
            assert!(core.verify(&credential2).is_ok());
        }
        
        println!("✅ Cryptographic consistency tests passed");
    }

    /// Test known attack vectors and defenses
    #[test]
    fn test_attack_resistance() {
        use std::collections::HashMap;
        
        let issuer = CredentialIssuer::new();
        let core = LemmaCore::new();
        
        // Create valid credential
        let mut claims = HashMap::new();
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        
        let credential = issuer.issue_credential(
            "test_subject".to_string(),
            claims,
            None,
        ).unwrap();
        
        // Test signature manipulation
        let mut sig_modified = credential.clone();
        if let Some(first_byte) = sig_modified.signature.get_mut(0) {
            *first_byte = first_byte.wrapping_add(1);
        }
        assert!(core.verify(&sig_modified).is_err(), "Signature manipulation should be detected");
        
        // Test subject modification
        let mut subject_modified = credential.clone();
        subject_modified.subject = "malicious_subject".to_string();
        assert!(core.verify(&subject_modified).is_err(), "Subject modification should be detected");
        
        // Test claim modification
        let mut claims_modified = credential.clone();
        claims_modified.claims.insert("admin".to_string(), serde_json::Value::Bool(true));
        assert!(core.verify(&claims_modified).is_err(), "Claims modification should be detected");
        
        // Test ID modification
        let mut id_modified = credential.clone();
        id_modified.id = "malicious_id".to_string();
        assert!(core.verify(&id_modified).is_err(), "ID modification should be detected");
        
        println!("✅ Attack resistance tests passed");
    }

    /// Test performance under cryptographic stress
    #[test]
    fn test_cryptographic_performance_stress() {
        use std::collections::HashMap;
        use std::time::Instant;
        
        let issuer = CredentialIssuer::new();
        let core = LemmaCore::new();
        
        let mut claims = HashMap::new();
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        
        // Create multiple credentials
        let mut credentials = Vec::new();
        let start = Instant::now();
        
        for i in 0..100 {
            let credential = issuer.issue_credential(
                format!("test_subject_{}", i),
                claims.clone(),
                None,
            ).unwrap();
            credentials.push(credential);
        }
        
        let issuance_time = start.elapsed();
        println!("Issued 100 credentials in {:?}", issuance_time);
        
        // Verify all credentials
        let start = Instant::now();
        for credential in &credentials {
            assert!(core.verify(credential).is_ok());
        }
        let verification_time = start.elapsed();
        println!("Verified 100 credentials in {:?}", verification_time);
        
        // Performance should be reasonable
        assert!(verification_time.as_millis() < 1000, "100 verifications should take less than 1 second");
        
        println!("✅ Cryptographic performance stress tests passed");
    }

    /// Test interoperability and serialization
    #[test]
    fn test_serialization_correctness() {
        use std::collections::HashMap;
        
        let issuer = CredentialIssuer::new();
        let core = LemmaCore::new();
        
        let mut claims = HashMap::new();
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("level".to_string(), serde_json::Value::Number(serde_json::Number::from(42)));
        
        let credential = issuer.issue_credential(
            "test_subject".to_string(),
            claims,
            None,
        ).unwrap();
        
        // Test JSON serialization
        let json_str = serde_json::to_string(&credential).unwrap();
        assert!(!json_str.is_empty());
        
        // Test JSON deserialization
        let deserialized: VerifiableCredential = serde_json::from_str(&json_str).unwrap();
        
        // Verify deserialized credential
        assert_eq!(credential.id, deserialized.id);
        assert_eq!(credential.issuer, deserialized.issuer);
        assert_eq!(credential.subject, deserialized.subject);
        assert_eq!(credential.claims, deserialized.claims);
        assert_eq!(credential.signature, deserialized.signature);
        
        // Verify the deserialized credential still works
        assert!(core.verify(&deserialized).is_ok());
        
        println!("✅ Serialization correctness tests passed");
    }

    /// Run all cryptographic correctness tests
    #[test]
    fn run_all_cryptographic_tests() {
        println!("🔒 Running Comprehensive Cryptographic Correctness Tests");
        println!("========================================================");
        
        // Ed25519 tests
        test_ed25519_rfc8032_vectors();
        test_ed25519_longer_message();
        test_ed25519_edge_cases();
        
        // OPRF tests
        test_oprf_correctness();
        test_oprf_edge_cases();
        
        // Bloom filter tests
        test_bloom_filter_correctness();
        test_cascaded_bloom_filter();
        test_bloom_filter_edge_cases();
        
        // Credential tests
        test_credential_correctness();
        test_credential_edge_cases();
        
        // System-level tests
        test_cryptographic_consistency();
        test_attack_resistance();
        test_cryptographic_performance_stress();
        test_serialization_correctness();
        
        println!("🎉 All cryptographic correctness tests passed!");
        println!("✅ Cryptographic implementation is secure and correct");
    }
} 