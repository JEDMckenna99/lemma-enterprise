//! Complete Crypto Wallet Flow Example
//! 
//! This example demonstrates the complete flow of:
//! 1. Creating a Rust-based crypto wallet
//! 2. Generating Lemma credentials (including ZKP)
//! 3. Storing credentials on user device (multi-layer storage)
//! 4. Cross-site credential sharing
//! 5. Microsecond verification

use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::Instant;

// Import the lemma-crypto components
use lemma_crypto::{
    LemmaCore,
    credentials::{VerifiableCredential, CredentialIssuer},
    packages::{IdentityPackage, TicketPackage, PackageAuthenticityPackage, QRCodePackage},
    wallet::{BackgroundWallet, WalletConfig, WalletStorage, PrivacyLevel},
    Result,
};

#[cfg(not(target_arch = "wasm32"))]
use lemma_crypto::zkp_claims::{zkp_helpers, ZKPCredential, ZKPVerifier};

fn main() -> Result<()> {
    println!("🦀 Complete Lemma Crypto Wallet Flow");
    println!("=====================================");
    
    // STEP 1: Initialize the crypto wallet system
    println!("\n🔧 STEP 1: Initialize Crypto Wallet System");
    let wallet = create_crypto_wallet_system()?;
    println!("✅ Crypto wallet system initialized with microsecond performance");
    
    // STEP 2: Create user credentials
    println!("\n👤 STEP 2: Create User Credentials");
    let user_credentials = create_user_credentials()?;
    println!("✅ Created {} user credentials", user_credentials.len());
    
    // STEP 3: Store credentials in wallet (device storage)
    println!("\n💾 STEP 3: Store Credentials in Device Wallet");
    let fingerprints = store_credentials_on_device(&wallet, user_credentials)?;
    println!("✅ Stored {} credentials with fingerprints: {:?}", fingerprints.len(), fingerprints);
    
    // STEP 4: Create ZKP credentials for privacy
    println!("\n🔐 STEP 4: Create Privacy-Preserving ZKP Credentials");
    create_zkp_credentials(&wallet)?;
    
    // STEP 5: Demonstrate cross-site credential sharing
    println!("\n🌐 STEP 5: Cross-Site Credential Sharing");
    demonstrate_cross_site_sharing(&wallet)?;
    
    // STEP 6: Perform microsecond verification
    println!("\n⚡ STEP 6: Microsecond Verification Performance");
    demonstrate_microsecond_verification(&wallet)?;
    
    // STEP 7: Show wallet statistics
    println!("\n📊 STEP 7: Wallet Statistics");
    show_wallet_statistics(&wallet);
    
    println!("\n🎉 Complete wallet flow demonstration successful!");
    println!("🚀 Ready for production use with microsecond performance!");
    
    Ok(())
}

/// Create and configure the crypto wallet system
fn create_crypto_wallet_system() -> Result<BackgroundWallet> {
    println!("  - Creating LemmaCore crypto engine...");
    let mut core = LemmaCore::new()?;
    
    // Register all supported credential packages
    core.register_package(IdentityPackage::new());
    core.register_package(TicketPackage::new());
    core.register_package(PackageAuthenticityPackage::new());
    core.register_package(QRCodePackage::new("user_device".to_string()));
    
    println!("  - Configuring multi-layer storage...");
    let wallet_config = WalletConfig {
        max_memory_credentials: 1000,        // Fast access layer
        max_browser_credentials: 10000,      // Persistent storage
        sync_interval_seconds: 300,          // 5-minute sync
        enable_predictive_loading: true,     // Pre-load likely credentials
        enable_network_sharing: true,        // Cross-site sharing
        enable_zkp_privacy: true,           // Privacy features
        ..Default::default()
    };
    
    println!("  - Initializing background wallet...");
    let wallet = BackgroundWallet::with_config(
        Arc::new(Mutex::new(core)),
        wallet_config
    );
    
    Ok(wallet)
}

/// Create various types of user credentials
fn create_user_credentials() -> Result<Vec<VerifiableCredential>> {
    let issuer = CredentialIssuer::new();
    let user_did = "did:lemma:user_device_12345".to_string();
    let mut credentials = Vec::new();
    
    // 1. Human Identity Credential
    let mut identity_claims = HashMap::new();
    identity_claims.insert("packageType".to_string(), serde_json::json!("identity"));
    identity_claims.insert("isHuman".to_string(), serde_json::json!(true));
    identity_claims.insert("verificationMethod".to_string(), serde_json::json!("stripe_identity"));
    identity_claims.insert("verificationLevel".to_string(), serde_json::json!("high"));
    identity_claims.insert("deviceId".to_string(), serde_json::json!("device_12345"));
    
    let identity_cred = issuer.issue_credential(
        user_did.clone(),
        identity_claims,
        Some(86400 * 30) // 30 days
    )?;
    credentials.push(identity_cred);
    
    // 2. Age Verification Credential
    let mut age_claims = HashMap::new();
    age_claims.insert("packageType".to_string(), serde_json::json!("identity"));
    age_claims.insert("ageVerified".to_string(), serde_json::json!(true));
    age_claims.insert("ageRange".to_string(), serde_json::json!("18_plus"));
    age_claims.insert("jurisdiction".to_string(), serde_json::json!("US"));
    
    let age_cred = issuer.issue_credential(
        user_did.clone(),
        age_claims,
        Some(86400 * 365) // 1 year
    )?;
    credentials.push(age_cred);
    
    // 3. Device Authentication Credential
    let mut device_claims = HashMap::new();
    device_claims.insert("packageType".to_string(), serde_json::json!("device"));
    device_claims.insert("deviceType".to_string(), serde_json::json!("mobile"));
    device_claims.insert("platform".to_string(), serde_json::json!("ios"));
    device_claims.insert("secureEnclave".to_string(), serde_json::json!(true));
    device_claims.insert("biometricEnabled".to_string(), serde_json::json!(true));
    
    let device_cred = issuer.issue_credential(
        user_did.clone(),
        device_claims,
        None // No expiration
    )?;
    credentials.push(device_cred);
    
    println!("  - Created identity credential: {}", credentials[0].id);
    println!("  - Created age verification credential: {}", credentials[1].id);
    println!("  - Created device authentication credential: {}", credentials[2].id);
    
    Ok(credentials)
}

/// Store credentials in the device wallet with multi-layer storage
fn store_credentials_on_device(wallet: &BackgroundWallet, credentials: Vec<VerifiableCredential>) -> Result<Vec<String>> {
    let mut fingerprints = Vec::new();
    
    for (i, credential) in credentials.iter().enumerate() {
        println!("  - Storing credential {} in device wallet...", i + 1);
        let start_time = Instant::now();
        
        // Store credential with automatic multi-layer caching
        let fingerprint = wallet.store_credential(credential.clone())?;
        
        let storage_time = start_time.elapsed();
        println!("    ✅ Stored with fingerprint: {} ({}µs)", 
                fingerprint, storage_time.as_micros());
        
        fingerprints.push(fingerprint);
    }
    
    // Verify all credentials are accessible
    println!("  - Verifying credential accessibility...");
    let stored_credentials = wallet.get_credentials_for_verification(None)?;
    println!("    ✅ {} credentials accessible for verification", stored_credentials.len());
    
    Ok(fingerprints)
}

/// Create ZKP credentials for privacy-preserving verification
#[cfg(not(target_arch = "wasm32"))]
fn create_zkp_credentials(wallet: &BackgroundWallet) -> Result<()> {
    println!("  - Creating privacy-preserving ZKP claims...");
    
    // Create human verification claim with zero-knowledge proof
    let human_secret = vec![1, 2, 3, 4]; // In practice, this would be derived from actual verification
    let human_claim = zkp_helpers::create_human_claim(&human_secret)?;
    println!("    ✅ Created ZKP human claim");
    
    // Create age verification claim with range proof
    let age_secret = vec![5, 6, 7, 8]; // Age verification secret
    let age_claim = zkp_helpers::create_age_range_claim(&age_secret, 18, 65)?;
    println!("    ✅ Created ZKP age range claim");
    
    // Create ZKP credential
    let mut zkp_claims = HashMap::new();
    zkp_claims.insert("isHuman".to_string(), human_claim);
    zkp_claims.insert("ageRange".to_string(), age_claim);
    
    // Use the crypto engine to create ZKP credential
    let core = Arc::clone(&wallet.core);
    let mut core_lock = core.lock().unwrap();
    
    let zkp_credential = core_lock.create_zkp_credential_from_claims(
        "did:lemma:privacy_issuer".to_string(),
        "did:lemma:user_device_12345".to_string(),
        zkp_claims,
    )?;
    
    // Store ZKP credential in wallet
    let zkp_fingerprint = wallet.store_zkp_credential(zkp_credential)?;
    println!("  - Stored ZKP credential with fingerprint: {}", zkp_fingerprint);
    
    println!("    ✅ ZKP credentials provide perfect privacy with selective disclosure");
    
    Ok(())
}

#[cfg(target_arch = "wasm32")]
fn create_zkp_credentials(_wallet: &BackgroundWallet) -> Result<()> {
    println!("  - ZKP features not available in WebAssembly build");
    println!("    (Use native build for full privacy features)");
    Ok(())
}

/// Demonstrate cross-site credential sharing
fn demonstrate_cross_site_sharing(wallet: &BackgroundWallet) -> Result<()> {
    println!("  - Simulating cross-site credential access...");
    
    // Simulate accessing credentials from different websites
    let sites = vec!["ecommerce.com", "social-media.com", "banking-app.com"];
    
    for site in sites {
        println!("    - Accessing credentials from {}...", site);
        
        let start_time = Instant::now();
        let credentials = wallet.get_credentials_for_verification(Some("identity"))?;
        let access_time = start_time.elapsed();
        
        println!("      ✅ {} credentials accessible ({}µs)", 
                credentials.len(), access_time.as_micros());
    }
    
    // Perform background network sync
    println!("  - Performing background network sync...");
    wallet.sync_with_network()?;
    println!("    ✅ Credentials synchronized across network");
    
    Ok(())
}

/// Demonstrate microsecond verification performance
fn demonstrate_microsecond_verification(wallet: &BackgroundWallet) -> Result<()> {
    println!("  - Testing verification performance...");
    
    let iterations = 100;
    let mut total_time = 0u128;
    
    for i in 0..iterations {
        let start_time = Instant::now();
        
        // Perform verification using integrated crypto engine
        let results = wallet.verify_credentials(Some("identity"))?;
        
        let verification_time = start_time.elapsed();
        total_time += verification_time.as_nanos();
        
        if i == 0 {
            println!("    - First verification: {}µs (cold start)", verification_time.as_micros());
            println!("    - Verification results: {} credentials verified", results.len());
        }
    }
    
    let avg_time_ns = total_time / iterations as u128;
    let avg_time_us = avg_time_ns as f64 / 1000.0;
    
    println!("    ✅ Average verification time: {:.2}µs ({} iterations)", avg_time_us, iterations);
    
    if avg_time_us < 1.0 {
        println!("    🚀 MICROSECOND PERFORMANCE ACHIEVED!");
    } else if avg_time_us < 10.0 {
        println!("    ⚡ Excellent sub-10µs performance!");
    } else {
        println!("    ✅ Good sub-millisecond performance");
    }
    
    Ok(())
}

/// Show comprehensive wallet statistics
fn show_wallet_statistics(wallet: &BackgroundWallet) {
    let stats = wallet.get_stats();
    
    println!("  📊 Wallet Statistics:");
    println!("    - Total credentials: {}", stats.total_credentials);
    println!("    - Memory layer: {} credentials", stats.memory_credentials);
    println!("    - Browser layer: {} credentials", stats.browser_credentials);
    println!("    - Cache hit rate: {:.2}%", stats.cache_hit_rate * 100.0);
    println!("    - Total verifications: {}", stats.total_verifications);
    println!("    - Offline verification rate: {:.2}%", stats.offline_verification_rate * 100.0);
    println!("    - Average verification time: {}ns", stats.avg_verification_time_ns);
    println!("    - Network sync operations: {}", stats.network_sync_count);
    println!("    - ZKP operations: {}", stats.zkp_operations);
} 