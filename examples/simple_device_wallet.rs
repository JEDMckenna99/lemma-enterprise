//! Simple Device Wallet Example
//! 
//! This example shows how to create a basic crypto wallet
//! that runs on a user device with local storage.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use lemma_crypto::{
    LemmaCore,
    credentials::{VerifiableCredential, CredentialIssuer, generate_keypair},
    wallet::BackgroundWallet,
    packages::IdentityPackage,
    Result,
};

fn main() -> Result<()> {
    println!("📱 Simple Device Wallet Example");
    println!("===============================");
    
    // Step 1: Create user's crypto wallet
    let wallet = create_user_wallet()?;
    println!("✅ Created user wallet");
    
    // Step 2: Generate user identity credential
    let credential = create_user_identity()?;
    println!("✅ Generated user identity credential");
    
    // Step 3: Store in device wallet
    let fingerprint = wallet.store_credential(credential)?;
    println!("✅ Stored credential in device: {}", fingerprint);
    
    // Step 4: Test verification
    test_verification(&wallet)?;
    
    println!("🎉 Device wallet working perfectly!");
    Ok(())
}

/// Create a user's crypto wallet for device storage
fn create_user_wallet() -> Result<BackgroundWallet> {
    // Initialize crypto engine
    let mut core = LemmaCore::new()?;
    core.register_package(IdentityPackage::new());
    
    // Create background wallet
    let wallet = BackgroundWallet::new(Arc::new(Mutex::new(core)));
    
    Ok(wallet)
}

/// Create a user identity credential
fn create_user_identity() -> Result<VerifiableCredential> {
    // Generate keys for user
    let (private_key, public_key) = generate_keypair();
    let issuer = CredentialIssuer::from_keys(private_key, public_key);
    
    // Create identity claims
    let mut claims = HashMap::new();
    claims.insert("packageType".to_string(), serde_json::json!("identity"));
    claims.insert("isHuman".to_string(), serde_json::json!(true));
    claims.insert("deviceStored".to_string(), serde_json::json!(true));
    
    // Issue credential
    let credential = issuer.issue_credential(
        "did:lemma:user".to_string(),
        claims,
        Some(86400 * 30) // 30 days
    )?;
    
    Ok(credential)
}

/// Test verification on device
fn test_verification(wallet: &BackgroundWallet) -> Result<()> {
    println!("  - Testing device verification...");
    
    let results = wallet.verify_credentials(None)?;
    println!("  - Verified {} credentials", results.len());
    
    for result in results {
        println!("    ✅ Credential verified: {}", result.verified);
    }
    
    Ok(())
} 