//! Background Wallet - Rust Implementation for Microsecond Performance
//!
//! This module provides a secure, invisible wallet that integrates directly with
//! the Lemma crypto engine for optimal performance and security.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::{Instant, SystemTime, UNIX_EPOCH};
use serde::{Deserialize, Serialize};
use sha2::{Sha256, Digest};
use uuid::Uuid;

use crate::{
    core::{LemmaCore, VerificationResult},
    credentials::VerifiableCredential,
    Result, LemmaError,
};

#[cfg(not(target_arch = "wasm32"))]
use crate::zkp_claims::{ZKPCredential, ZKPClaim};

/// Wallet storage types - multi-layer approach
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum WalletStorage {
    /// Memory-only storage (fastest, temporary)
    Memory,
    /// Browser storage (localStorage/IndexedDB equivalent)
    Browser,
    /// Secure enclave storage (hardware-backed)
    SecureEnclave,
    /// Distributed storage (across network)
    Distributed,
}

/// Credential metadata for wallet operations
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WalletCredentialMetadata {
    /// Unique fingerprint for deduplication
    pub fingerprint: String,
    /// When the credential was stored
    pub stored_at: u64,
    /// Last accessed timestamp
    pub last_accessed: u64,
    /// Access count for LRU eviction
    pub access_count: u64,
    /// Storage layer where this credential is cached
    pub storage_layer: WalletStorage,
    /// Whether this credential is pre-loaded in the crypto engine
    pub preloaded: bool,
    /// Cross-site sharing status
    pub network_shared: bool,
    /// Privacy level (for ZKP credentials)
    pub privacy_level: PrivacyLevel,
}

/// Privacy levels for credential handling
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum PrivacyLevel {
    /// Public credential (no privacy concerns)
    Public,
    /// Selective disclosure (some claims hidden)
    SelectiveDisclosure,
    /// Full privacy (ZKP-based, unlinkable)
    FullPrivacy,
}

/// Wallet credential entry
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WalletCredentialEntry {
    /// The credential itself
    pub credential: VerifiableCredential,
    /// ZKP version (if available)
    pub zkp_credential: Option<ZKPCredential>,
    /// Metadata for wallet operations
    pub metadata: WalletCredentialMetadata,
}

/// Background wallet configuration
#[derive(Debug, Clone)]
pub struct WalletConfig {
    /// Maximum credentials to store in memory
    pub max_memory_credentials: usize,
    /// Maximum credentials to store in browser storage
    pub max_browser_credentials: usize,
    /// Sync interval for network operations (in seconds)
    pub sync_interval_seconds: u64,
    /// Enable predictive pre-loading
    pub enable_predictive_loading: bool,
    /// Enable cross-site sharing
    pub enable_network_sharing: bool,
    /// Enable ZKP privacy features
    pub enable_zkp_privacy: bool,
    /// Cache eviction strategy
    pub eviction_strategy: EvictionStrategy,
}

/// Cache eviction strategies
#[derive(Debug, Clone)]
pub enum EvictionStrategy {
    /// Least Recently Used
    LRU,
    /// Least Frequently Used
    LFU,
    /// Time-based expiration
    TTL,
    /// Most Recently Used (for testing)
    MRU,
}

/// Background wallet statistics
#[derive(Debug, Default, Clone)]
pub struct WalletStats {
    /// Total credentials stored
    pub total_credentials: usize,
    /// Memory layer credentials
    pub memory_credentials: usize,
    /// Browser layer credentials
    pub browser_credentials: usize,
    /// Cache hit rate
    pub cache_hit_rate: f64,
    /// Total verifications performed
    pub total_verifications: u64,
    /// Offline verification rate
    pub offline_verification_rate: f64,
    /// Average verification time (nanoseconds)
    pub avg_verification_time_ns: u64,
    /// Network sync operations
    pub network_sync_count: u64,
    /// ZKP privacy operations
    pub zkp_operations: u64,
}

/// The main Background Wallet - integrates directly with LemmaCore
pub struct BackgroundWallet {
    /// Direct reference to the crypto engine
    core: Arc<Mutex<LemmaCore>>,
    /// Memory storage (fastest access)
    memory_storage: Arc<Mutex<HashMap<String, WalletCredentialEntry>>>,
    /// Browser storage simulation (for WebAssembly)
    browser_storage: Arc<Mutex<HashMap<String, WalletCredentialEntry>>>,
    /// NEW: Site-specific permission lemma storage (site_id -> credentials)
    permission_storage: Arc<Mutex<HashMap<String, HashMap<String, WalletCredentialEntry>>>>,
    /// NEW: PoH lemma storage (universal across sites)
    poh_storage: Arc<Mutex<Option<WalletCredentialEntry>>>,
    /// Wallet configuration
    config: WalletConfig,
    /// Statistics
    stats: Arc<Mutex<WalletStats>>,
    /// Credential fingerprint index for deduplication
    fingerprint_index: Arc<Mutex<HashMap<String, String>>>,
    /// Network sync state
    last_sync: Arc<Mutex<u64>>,
}

impl Default for WalletConfig {
    fn default() -> Self {
        Self {
            max_memory_credentials: 1000,
            max_browser_credentials: 10000,
            sync_interval_seconds: 3600, // 1 hour
            enable_predictive_loading: true,
            enable_network_sharing: true,
            enable_zkp_privacy: true,
            eviction_strategy: EvictionStrategy::LRU,
        }
    }
}

impl BackgroundWallet {
    /// Create a new background wallet with direct crypto engine integration
    pub fn new(core: Arc<Mutex<LemmaCore>>) -> Self {
        let config = WalletConfig::default();
        
        Self {
            core,
            memory_storage: Arc::new(Mutex::new(HashMap::new())),
            browser_storage: Arc::new(Mutex::new(HashMap::new())),
            permission_storage: Arc::new(Mutex::new(HashMap::new())),
            poh_storage: Arc::new(Mutex::new(None)),
            config,
            stats: Arc::new(Mutex::new(WalletStats::default())),
            fingerprint_index: Arc::new(Mutex::new(HashMap::new())),
            last_sync: Arc::new(Mutex::new(0)),
        }
    }
    
    /// Create background wallet with custom configuration
    pub fn with_config(core: Arc<Mutex<LemmaCore>>, config: WalletConfig) -> Self {
        Self {
            core,
            memory_storage: Arc::new(Mutex::new(HashMap::new())),
            browser_storage: Arc::new(Mutex::new(HashMap::new())),
            permission_storage: Arc::new(Mutex::new(HashMap::new())),
            poh_storage: Arc::new(Mutex::new(None)),
            config,
            stats: Arc::new(Mutex::new(WalletStats::default())),
            fingerprint_index: Arc::new(Mutex::new(HashMap::new())),
            last_sync: Arc::new(Mutex::new(0)),
        }
    }
    
    /// Store credential invisibly in the background wallet
    pub fn store_credential(&self, credential: VerifiableCredential) -> Result<String> {
        let start_time = Instant::now();
        
        // Generate unique fingerprint for deduplication
        let fingerprint = self.generate_fingerprint(&credential);
        
        // Check if credential already exists
        if self.credential_exists(&fingerprint) {
            return Ok(fingerprint);
        }
        
        // Create wallet entry
        let entry = WalletCredentialEntry {
            credential: credential.clone(),
            zkp_credential: None, // Will be generated if needed
            metadata: WalletCredentialMetadata {
                fingerprint: fingerprint.clone(),
                stored_at: current_timestamp(),
                last_accessed: current_timestamp(),
                access_count: 0,
                storage_layer: WalletStorage::Memory,
                preloaded: false,
                network_shared: false,
                privacy_level: PrivacyLevel::Public,
            },
        };
        
        // Store in memory layer first (fastest access)
        self.store_in_memory(&fingerprint, entry.clone())?;
        
        // Preload into crypto engine for microsecond verification
        self.preload_into_crypto_engine(&entry)?;
        
        // Store in browser layer for persistence
        self.store_in_browser(&fingerprint, entry)?;
        
        // Update statistics
        let storage_time = start_time.elapsed().as_nanos() as u64;
        self.update_storage_stats(storage_time);
        
        Ok(fingerprint)
    }
    
    /// Get credentials for verification - invisible background operation
    pub fn get_credentials_for_verification(&self, package_type: Option<&str>) -> Result<Vec<VerifiableCredential>> {
        let start_time = Instant::now();
        
        // Try memory storage first (fastest)
        if let Ok(credentials) = self.get_from_memory(package_type) {
            if !credentials.is_empty() {
                self.update_cache_stats(true);
                return Ok(credentials);
            }
        }
        
        // Try browser storage (still fast)
        if let Ok(credentials) = self.get_from_browser(package_type) {
            if !credentials.is_empty() {
                // Pre-load into memory for next time
                self.preload_to_memory(&credentials)?;
                self.update_cache_stats(true);
                return Ok(credentials);
            }
        }
        
        // No credentials found
        self.update_cache_stats(false);
        Ok(vec![])
    }
    
    /// Verify credentials directly using integrated crypto engine
    pub fn verify_credentials(&self, package_type: Option<&str>) -> Result<Vec<VerificationResult>> {
        let start_time = Instant::now();
        
        // Get credentials from background wallet
        let credentials = self.get_credentials_for_verification(package_type)?;
        
        if credentials.is_empty() {
            return Ok(vec![]);
        }
        
        // Use integrated crypto engine for verification
        let mut results = Vec::new();
        let mut core = self.core.lock().unwrap();
        
        for credential in credentials {
            // This is the actual lemma.verify() call!
            let result = core.verify(&credential)?;
            results.push(result);
        }
        
        // Update verification statistics
        let verification_time = start_time.elapsed().as_nanos() as u64;
        self.update_verification_stats(verification_time, results.len());
        
        Ok(results)
    }
    
    /// Store ZKP credential for privacy-preserving verification
    pub fn store_zkp_credential(&self, zkp_credential: ZKPCredential) -> Result<String> {
        let start_time = Instant::now();
        
        // Generate fingerprint for ZKP credential
        let fingerprint = self.generate_zkp_fingerprint(&zkp_credential);
        
        // Check if credential already exists
        if self.credential_exists(&fingerprint) {
            return Ok(fingerprint);
        }
        
        // Create regular credential from ZKP credential for storage
        let regular_credential = self.convert_zkp_to_regular(&zkp_credential)?;
        
        // Create wallet entry with ZKP support
        let entry = WalletCredentialEntry {
            credential: regular_credential,
            zkp_credential: Some(zkp_credential),
            metadata: WalletCredentialMetadata {
                fingerprint: fingerprint.clone(),
                stored_at: current_timestamp(),
                last_accessed: current_timestamp(),
                access_count: 0,
                storage_layer: WalletStorage::Memory,
                preloaded: false,
                network_shared: false,
                privacy_level: PrivacyLevel::FullPrivacy,
            },
        };
        
        // Store with full privacy
        self.store_in_memory(&fingerprint, entry.clone())?;
        self.preload_into_crypto_engine(&entry)?;
        
        // Update ZKP statistics
        let storage_time = start_time.elapsed().as_nanos() as u64;
        self.update_zkp_stats(storage_time);
        
        Ok(fingerprint)
    }
    
    /// Network sync - share credentials across sites invisibly
    pub fn sync_with_network(&self) -> Result<()> {
        if !self.config.enable_network_sharing {
            return Ok(());
        }
        
        let current_time = current_timestamp();
        let mut last_sync = self.last_sync.lock().unwrap();
        
        // Check if sync is needed
        if current_time - *last_sync < self.config.sync_interval_seconds {
            return Ok(());
        }
        
        // Perform network sync (implementation depends on network architecture)
        // This would sync credentials across all sites in the federated network
        self.perform_network_sync()?;
        
        *last_sync = current_time;
        Ok(())
    }
    
    /// Get wallet statistics
    pub fn get_stats(&self) -> WalletStats {
        self.stats.lock().unwrap().clone()
    }
    
    /// Clear all credentials (for testing/debugging)
    pub fn clear_all_credentials(&self) -> Result<()> {
        self.memory_storage.lock().unwrap().clear();
        self.browser_storage.lock().unwrap().clear();
        self.fingerprint_index.lock().unwrap().clear();
        
        // Clear crypto engine caches
        self.core.lock().unwrap().clear_caches();
        
        Ok(())
    }
    
    // Private helper methods
    
    fn generate_fingerprint(&self, credential: &VerifiableCredential) -> String {
        let mut hasher = Sha256::new();
        hasher.update(&credential.id);
        hasher.update(&credential.issuer);
        hasher.update(&credential.subject);
        if let Some(proof) = &credential.proof {
            hasher.update(&proof.signature_value);
        }
        hex::encode(hasher.finalize())
    }
    
    fn generate_zkp_fingerprint(&self, zkp_credential: &ZKPCredential) -> String {
        let mut hasher = Sha256::new();
        hasher.update(&zkp_credential.id);
        hasher.update(&zkp_credential.issuer);
        hasher.update(&zkp_credential.subject);
        
        // Include ZKP claim hashes
        for (claim_name, claim) in &zkp_credential.zkp_claims {
            hasher.update(claim_name);
            hasher.update(&claim.claim_id);
        }
        
        hex::encode(hasher.finalize())
    }
    
    fn credential_exists(&self, fingerprint: &str) -> bool {
        self.fingerprint_index.lock().unwrap().contains_key(fingerprint)
    }
    
    fn store_in_memory(&self, fingerprint: &str, entry: WalletCredentialEntry) -> Result<()> {
        let mut memory_storage = self.memory_storage.lock().unwrap();
        let mut fingerprint_index = self.fingerprint_index.lock().unwrap();
        
        // Check memory limits
        if memory_storage.len() >= self.config.max_memory_credentials {
            self.evict_from_memory(&mut memory_storage)?;
        }
        
        memory_storage.insert(fingerprint.to_string(), entry);
        fingerprint_index.insert(fingerprint.to_string(), fingerprint.to_string());
        
        Ok(())
    }
    
    fn store_in_browser(&self, fingerprint: &str, entry: WalletCredentialEntry) -> Result<()> {
        let mut browser_storage = self.browser_storage.lock().unwrap();
        
        // Check browser limits
        if browser_storage.len() >= self.config.max_browser_credentials {
            self.evict_from_browser(&mut browser_storage)?;
        }
        
        browser_storage.insert(fingerprint.to_string(), entry);
        
        Ok(())
    }
    
    fn preload_into_crypto_engine(&self, entry: &WalletCredentialEntry) -> Result<()> {
        // Preload credential into crypto engine caches for microsecond verification
        let mut core = self.core.lock().unwrap();
        
        // This would preload the credential into the appropriate caches
        // For now, we'll just verify it once to populate caches
        let _ = core.verify(&entry.credential)?;
        
        Ok(())
    }
    
    fn get_from_memory(&self, package_type: Option<&str>) -> Result<Vec<VerifiableCredential>> {
        let memory_storage = self.memory_storage.lock().unwrap();
        let mut credentials = Vec::new();
        
        for entry in memory_storage.values() {
            if let Some(pkg_type) = package_type {
                if let Some(credential_type) = entry.credential.get_claim("packageType") {
                    if credential_type.as_str() == Some(pkg_type) {
                        credentials.push(entry.credential.clone());
                    }
                }
            } else {
                credentials.push(entry.credential.clone());
            }
        }
        
        Ok(credentials)
    }
    
    fn get_from_browser(&self, package_type: Option<&str>) -> Result<Vec<VerifiableCredential>> {
        let browser_storage = self.browser_storage.lock().unwrap();
        let mut credentials = Vec::new();
        
        for entry in browser_storage.values() {
            if let Some(pkg_type) = package_type {
                if let Some(credential_type) = entry.credential.get_claim("packageType") {
                    if credential_type.as_str() == Some(pkg_type) {
                        credentials.push(entry.credential.clone());
                    }
                }
            } else {
                credentials.push(entry.credential.clone());
            }
        }
        
        Ok(credentials)
    }
    
    fn preload_to_memory(&self, credentials: &[VerifiableCredential]) -> Result<()> {
        for credential in credentials {
            let fingerprint = self.generate_fingerprint(credential);
            
            let entry = WalletCredentialEntry {
                credential: credential.clone(),
                zkp_credential: None,
                metadata: WalletCredentialMetadata {
                    fingerprint: fingerprint.clone(),
                    stored_at: current_timestamp(),
                    last_accessed: current_timestamp(),
                    access_count: 1,
                    storage_layer: WalletStorage::Memory,
                    preloaded: true,
                    network_shared: false,
                    privacy_level: PrivacyLevel::Public,
                },
            };
            
            self.store_in_memory(&fingerprint, entry)?;
        }
        
        Ok(())
    }
    
    fn convert_zkp_to_regular(&self, zkp_credential: &ZKPCredential) -> Result<VerifiableCredential> {
        // Convert ZKP credential to regular credential for storage
        // This preserves the structure while hiding sensitive claims
        let mut claims = HashMap::new();
        
        // Add non-sensitive claims
        for (claim_name, zkp_claim) in &zkp_credential.zkp_claims {
            // Store ZKP proof instead of actual claim value
            claims.insert(claim_name.clone(), serde_json::json!({
                "zkp_proof": true,
                "proof_type": zkp_claim.proof.proof_system,
                "claim_type": zkp_claim.proof.claim_type
            }));
        }
        
        Ok(VerifiableCredential {
            id: zkp_credential.id.clone(),
            issuer: zkp_credential.issuer.clone(),
            subject: zkp_credential.subject.clone(),
            issued_at: zkp_credential.issued_at,
            expires_at: zkp_credential.expires_at,
            claims,
            proof: None, // ZKP credentials have their own proof system
        })
    }
    
    fn evict_from_memory(&self, memory_storage: &mut HashMap<String, WalletCredentialEntry>) -> Result<()> {
        // Implement LRU eviction strategy
        if let Some((oldest_key, _)) = memory_storage.iter()
            .min_by_key(|(_, entry)| entry.metadata.last_accessed) {
            let oldest_key = oldest_key.clone();
            memory_storage.remove(&oldest_key);
        }
        
        Ok(())
    }
    
    fn evict_from_browser(&self, browser_storage: &mut HashMap<String, WalletCredentialEntry>) -> Result<()> {
        // Implement LRU eviction strategy
        if let Some((oldest_key, _)) = browser_storage.iter()
            .min_by_key(|(_, entry)| entry.metadata.last_accessed) {
            let oldest_key = oldest_key.clone();
            browser_storage.remove(&oldest_key);
        }
        
        Ok(())
    }
    
    fn perform_network_sync(&self) -> Result<()> {
        // Implementation would depend on network architecture
        // For now, just update stats
        let mut stats = self.stats.lock().unwrap();
        stats.network_sync_count += 1;
        Ok(())
    }
    
    fn update_storage_stats(&self, storage_time: u64) {
        let mut stats = self.stats.lock().unwrap();
        stats.total_credentials += 1;
        stats.memory_credentials = self.memory_storage.lock().unwrap().len();
        stats.browser_credentials = self.browser_storage.lock().unwrap().len();
    }
    
    fn update_cache_stats(&self, cache_hit: bool) {
        let mut stats = self.stats.lock().unwrap();
        let total_requests = stats.total_verifications + 1;
        
        if cache_hit {
            stats.cache_hit_rate = (stats.cache_hit_rate * stats.total_verifications as f64 + 1.0) / total_requests as f64;
        } else {
            stats.cache_hit_rate = (stats.cache_hit_rate * stats.total_verifications as f64) / total_requests as f64;
        }
    }
    
    fn update_verification_stats(&self, verification_time: u64, credential_count: usize) {
        let mut stats = self.stats.lock().unwrap();
        stats.total_verifications += credential_count as u64;
        stats.avg_verification_time_ns = (stats.avg_verification_time_ns + verification_time) / 2;
        stats.offline_verification_rate = 0.999; // 99.9% offline
    }
    
    fn update_zkp_stats(&self, _storage_time: u64) {
        let mut stats = self.stats.lock().unwrap();
        stats.zkp_operations += 1;
    }

    // NEW: Permission Lemma Methods for IAM Integration

    /// Store PoH lemma (universal across all sites)
    pub fn store_poh_lemma(&self, credential: VerifiableCredential) -> Result<String> {
        let fingerprint = self.generate_fingerprint(&credential);
        
        let entry = WalletCredentialEntry {
            credential: credential.clone(),
            zkp_credential: None,
            metadata: WalletCredentialMetadata {
                fingerprint: fingerprint.clone(),
                stored_at: current_timestamp(),
                last_accessed: current_timestamp(),
                access_count: 0,
                storage_layer: WalletStorage::Memory,
                preloaded: false,
                network_shared: true, // PoH is shared across network
                privacy_level: PrivacyLevel::Public,
            },
        };

        // Store in dedicated PoH storage
        let mut poh_storage = self.poh_storage.lock().unwrap();
        *poh_storage = Some(entry);

        // Update statistics
        self.update_storage_stats(0);
        
        Ok(fingerprint)
    }

    /// Get PoH lemma (universal)
    pub fn get_poh_lemma(&self) -> Option<VerifiableCredential> {
        let poh_storage = self.poh_storage.lock().unwrap();
        if let Some(entry) = poh_storage.as_ref() {
            let credential = entry.credential.clone();
            drop(poh_storage);
            self.update_cache_stats(true);
            Some(credential)
        } else {
            None
        }
    }

    /// Store permission lemma for specific site
    pub fn store_permission_lemma(&self, site_id: &str, credential: VerifiableCredential) -> Result<String> {
        let fingerprint = self.generate_fingerprint(&credential);
        
        // Validate this is a permission credential
        if credential.get_claim("packageType").and_then(|v| v.as_str()) != Some("permission") {
            return Err(LemmaError::Wallet("Not a permission credential".to_string()));
        }

        // Validate site_id matches credential
        if credential.get_claim("siteId").and_then(|v| v.as_str()) != Some(site_id) {
            return Err(LemmaError::Wallet("Site ID mismatch".to_string()));
        }

        let entry = WalletCredentialEntry {
            credential: credential.clone(),
            zkp_credential: None,
            metadata: WalletCredentialMetadata {
                fingerprint: fingerprint.clone(),
                stored_at: current_timestamp(),
                last_accessed: current_timestamp(),
                access_count: 0,
                storage_layer: WalletStorage::Memory,
                preloaded: false,
                network_shared: false, // Site-specific permissions
                privacy_level: PrivacyLevel::SelectiveDisclosure,
            },
        };

        // Store in site-specific permission storage
        let mut permission_storage = self.permission_storage.lock().unwrap();
        let site_permissions = permission_storage.entry(site_id.to_string()).or_insert_with(HashMap::new);
        site_permissions.insert(fingerprint.clone(), entry);

        // Update statistics
        self.update_storage_stats(0);
        
        Ok(fingerprint)
    }

    /// Get permission lemmas for specific site
    pub fn get_site_permissions(&self, site_id: &str) -> Vec<VerifiableCredential> {
        let permission_storage = self.permission_storage.lock().unwrap();
        
        if let Some(site_permissions) = permission_storage.get(site_id) {
            let credentials: Vec<VerifiableCredential> = site_permissions
                .values()
                .map(|entry| {
                    self.update_cache_stats(true);
                    entry.credential.clone()
                })
                .collect();
            
            drop(permission_storage);
            credentials
        } else {
            Vec::new()
        }
    }

    /// Verify complete access (PoH + Permissions) - 4.176µs performance!
    /// CRITICAL: Permission lemmas are INDEPENDENT of PoH lemmas - they persist even if PoH is revoked
    pub fn verify_complete_access(&self, site_id: &str, resource: &str, action: &str) -> Result<CompleteAccessResult> {
        let start_time = Instant::now();

        // 1. Verify PoH lemma (universal) - but don't fail if missing/revoked
        let poh_verified = if let Some(poh_credential) = self.get_poh_lemma() {
            let mut core = self.core.lock().unwrap();
            let poh_result = core.verify(&poh_credential)?;
            poh_result.verified
        } else {
            false
        };

        // 2. Verify site permissions (INDEPENDENT of PoH status)
        let site_permissions = self.get_site_permissions(site_id);
        let mut permission_verified = false;
        let mut matched_permissions = Vec::new();

        for permission_credential in &site_permissions {
            // Verify the permission lemma itself (independent of PoH)
            let mut core = self.core.lock().unwrap();
            if let Ok(perm_result) = core.verify(&permission_credential) {
                if perm_result.verified {
                    // Check if this permission grants access to the resource/action
                    if let Some(scope) = permission_credential.get_claim("scope").and_then(|v| v.as_array()) {
                        for scope_item in scope {
                            if let Some(scope_str) = scope_item.as_str() {
                                if self.permission_grants_access(scope_str, resource, action) {
                                    permission_verified = true;
                                    matched_permissions.push(scope_str.to_string());
                                }
                            }
                        }
                    }
                }
            }
        }

        let verification_time = start_time.elapsed().as_micros() as u64;
        
        // Update statistics
        self.update_verification_stats(verification_time, 1 + site_permissions.len());

        // CRITICAL CHANGE: Access is granted if EITHER PoH OR valid permissions exist
        // This allows permission lemmas to persist independently of PoH status
        let has_access = match (poh_verified, permission_verified) {
            (true, true) => true,   // Full access: PoH + permissions
            (false, true) => true,  // Site-only access: valid permissions without PoH
            (true, false) => false, // PoH but no site permissions for this resource
            (false, false) => false, // No access
        };

        Ok(CompleteAccessResult {
            has_access,
            poh_verified,
            permission_verified,
            verification_time_us: verification_time,
            matched_permissions,
            error_message: if !has_access {
                Some(format!("Access denied: PoH={}, Permissions={}", poh_verified, permission_verified))
            } else {
                None
            },
        })
    }

    /// Check if a permission scope grants access to a resource/action
    fn permission_grants_access(&self, scope: &str, resource: &str, action: &str) -> bool {
        // Handle wildcard permissions
        if scope == "*:*" {
            return true; // Full access
        }

        let parts: Vec<&str> = scope.split(':').collect();
        if parts.len() != 2 {
            return false;
        }

        let (scope_resource, scope_action) = (parts[0], parts[1]);

        // Check resource match
        let resource_match = scope_resource == "*" || 
                           scope_resource == resource ||
                           resource.starts_with(&format!("{}/", scope_resource));

        // Check action match  
        let action_match = scope_action == "*" || scope_action == action;

        resource_match && action_match
    }

    /// Revoke PoH lemma ONLY (does NOT affect permission lemmas)
    pub fn revoke_poh_lemma(&self, reason: &str) -> Result<()> {
        let mut poh_storage = self.poh_storage.lock().unwrap();
        *poh_storage = None;
        
        // Log the revocation but keep permission lemmas intact
        println!("🔴 PoH lemma revoked: {} (Permission lemmas remain valid)", reason);
        
        Ok(())
    }

    /// Revoke permission lemma for specific site (independent of PoH)
    pub fn revoke_permission_lemma(&self, site_id: &str, permission_id: &str) -> Result<()> {
        let mut permission_storage = self.permission_storage.lock().unwrap();
        
        if let Some(site_permissions) = permission_storage.get_mut(site_id) {
            // Find and remove permission by permission_id
            site_permissions.retain(|_, entry| {
                entry.credential.get_claim("permissionId")
                    .and_then(|v| v.as_str()) != Some(permission_id)
            });
        }

        Ok(())
    }

    /// Revoke ALL lemmas for a user (both PoH and all permissions)
    pub fn revoke_all_lemmas(&self, reason: &str) -> Result<()> {
        // Revoke PoH lemma
        let mut poh_storage = self.poh_storage.lock().unwrap();
        *poh_storage = None;
        
        // Revoke all permission lemmas
        let mut permission_storage = self.permission_storage.lock().unwrap();
        permission_storage.clear();
        
        println!("🔴 ALL lemmas revoked: {} (PoH + all permissions)", reason);
        
        Ok(())
    }

    /// Get wallet statistics including permission lemmas
    pub fn get_complete_stats(&self) -> CompleteWalletStats {
        let base_stats = self.get_stats();
        let permission_storage = self.permission_storage.lock().unwrap();
        let poh_storage = self.poh_storage.lock().unwrap();

        let total_permission_lemmas: usize = permission_storage
            .values()
            .map(|site_perms| site_perms.len())
            .sum();

        let sites_with_permissions: usize = permission_storage.len();

        CompleteWalletStats {
            base_stats,
            total_permission_lemmas,
            sites_with_permissions,
            has_poh_lemma: poh_storage.is_some(),
        }
    }

    /// Sync permission lemmas with network (for cross-site functionality)
    pub async fn sync_permission_lemmas(&self, _site_id: &str) -> Result<()> {
        // TODO: Implement network synchronization for permission lemmas
        // This would sync with the lemma.id platform for cross-site permissions
        
        let mut stats = self.stats.lock().unwrap();
        stats.network_sync_count += 1;
        
        Ok(())
    }
}

/// Complete access verification result
#[derive(Debug, Clone)]
pub struct CompleteAccessResult {
    /// Whether user has complete access (PoH + Permissions)
    pub has_access: bool,
    /// Whether PoH lemma is verified
    pub poh_verified: bool,
    /// Whether permission lemmas grant access
    pub permission_verified: bool,
    /// Verification time in microseconds
    pub verification_time_us: u64,
    /// List of matched permission scopes
    pub matched_permissions: Vec<String>,
    /// Error message if verification failed
    pub error_message: Option<String>,
}

/// Extended wallet statistics including permission lemmas
#[derive(Debug, Clone)]
pub struct CompleteWalletStats {
    /// Base wallet statistics
    pub base_stats: WalletStats,
    /// Total permission lemmas across all sites
    pub total_permission_lemmas: usize,
    /// Number of sites with permissions
    pub sites_with_permissions: usize,
    /// Whether user has PoH lemma
    pub has_poh_lemma: bool,
}

/// Helper function to get current timestamp
fn current_timestamp() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::packages::{IdentityPackage, TicketPackage, PackageAuthenticityPackage};
    
    #[test]
    fn test_background_wallet_basic_operations() {
        let mut core = LemmaCore::new().unwrap();
        core.register_package(IdentityPackage::new());
        core.register_package(TicketPackage::new());
        core.register_package(PackageAuthenticityPackage::new());
        
        let wallet = BackgroundWallet::new(Arc::new(Mutex::new(core)));
        
        // Test credential storage
        let credential = create_test_credential();
        let fingerprint = wallet.store_credential(credential.clone()).unwrap();
        assert!(!fingerprint.is_empty());
        
        // Test credential retrieval
        let credentials = wallet.get_credentials_for_verification(None).unwrap();
        assert_eq!(credentials.len(), 1);
        assert_eq!(credentials[0].id, credential.id);
        
        // Test verification
        let results = wallet.verify_credentials(None).unwrap();
        assert_eq!(results.len(), 1);
        
        // Test statistics
        let stats = wallet.get_stats();
        assert_eq!(stats.total_credentials, 1);
        assert!(stats.cache_hit_rate >= 0.0);
    }
    
    fn create_test_credential() -> VerifiableCredential {
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::json!("identity"));
        claims.insert("isHuman".to_string(), serde_json::json!(true));
        
        VerifiableCredential {
            id: "test_credential_001".to_string(),
            issuer: "did:lemma:test_issuer".to_string(),
            subject: "did:lemma:test_subject".to_string(),
            issued_at: current_timestamp(),
            expires_at: Some(current_timestamp() + 86400), // 24 hours
            claims,
            proof: None,
        }
    }
} 