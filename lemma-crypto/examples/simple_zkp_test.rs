//! Simple ZKP Test - Basic functionality test
//! 
//! This test focuses on the core ZKP functionality to ensure it works

use lemma_crypto::{
    LemmaCore, 
    zkp_claims::{zkp_helpers, ZKPCredential, ZKPVerifier},
    packages::IdentityPackage,
    Result,
};
use std::collections::HashMap;

fn main() -> Result<()> {
    println!("🔐 Simple ZKP Test");
    println!("==================");
    
    // Initialize the verification engine
    let mut lemma_core = LemmaCore::new()?;
    lemma_core.register_package(IdentityPackage::new());
    
    println!("✅ Initialized LemmaCore with ZKP support");
    
    // Create a simple ZKP claim
    let human_claim = zkp_helpers::create_human_claim(&[1, 2, 3, 4])?;
    println!("✅ Created human ZKP claim");
    
    // Create ZKP credential
    let mut zkp_claims = HashMap::new();
    zkp_claims.insert("isHuman".to_string(), human_claim);
    
    let zkp_credential = lemma_core.create_zkp_credential_from_claims(
        "did:lemma:issuer".to_string(),
        "did:lemma:subject".to_string(),
        zkp_claims,
    )?;
    
    println!("✅ Created ZKP credential with {} claims", zkp_credential.zkp_claims.len());
    
    // Verify the credential
    let result = lemma_core.verify_zkp_credential(&zkp_credential)?;
    println!("✅ Verified ZKP credential: {}", result.verified);
    
    println!("🎉 ZKP integration test successful!");
    
    Ok(())
} 