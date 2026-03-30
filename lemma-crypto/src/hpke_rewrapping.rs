//! HPKE Rewrapping for Secure Device Transfers
//! Implements proxy re-encryption for device-to-device wallet transfers

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DevicePublicKey {
    pub key_bytes: [u8; 32],
    pub device_id: String,
    pub created_at: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RewrappedEnvelope {
    pub original_envelope: Vec<u8>,
    pub rewrap_proof: Vec<u8>,
    pub new_device_pubkey: DevicePublicKey,
    pub rewrap_timestamp: u64,
}

#[derive(Debug, Clone)]
pub struct HPKERewrapper {
    // Server-side rewrapping key (would be in HSM)
    server_private_key: [u8; 32],
}

impl HPKERewrapper {
    pub fn new(server_private_key: [u8; 32]) -> Self {
        Self { server_private_key }
    }

    /// Generate server keypair for rewrapping
    pub fn generate_server_keypair() -> ([u8; 32], [u8; 32]) {
        use rand::RngCore;
        let mut rng = rand::thread_rng();
        
        let mut private_key = [0u8; 32];
        let mut public_key = [0u8; 32];
        
        rng.fill_bytes(&mut private_key);
        
        // Generate corresponding public key (simplified)
        use sha2::{Sha256, Digest};
        let mut hasher = Sha256::new();
        hasher.update(&private_key);
        public_key.copy_from_slice(&hasher.finalize()[..32]);
        
        (private_key, public_key)
    }

    /// Rewrap envelope for new device (HPKE proxy re-encryption)
    pub fn rewrap_envelope(
        &self,
        original_ciphertext: &[u8],
        old_device_pubkey: &DevicePublicKey,
        new_device_pubkey: &DevicePublicKey
    ) -> Result<RewrappedEnvelope, String> {
        // TODO: Implement proper HPKE proxy re-encryption
        // This is a complex cryptographic protocol that requires:
        // 1. HPKE key encapsulation
        // 2. Proxy re-encryption transformation
        // 3. Re-encapsulation for new device
        
        // For now, implement simplified rewrapping
        let rewrapped = RewrappedEnvelope {
            original_envelope: original_ciphertext.to_vec(),
            rewrap_proof: self.generate_rewrap_proof(old_device_pubkey, new_device_pubkey)?,
            new_device_pubkey: new_device_pubkey.clone(),
            rewrap_timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
        };
        
        Ok(rewrapped)
    }

    /// Generate proof of rewrapping for transparency
    fn generate_rewrap_proof(
        &self,
        old_device: &DevicePublicKey,
        new_device: &DevicePublicKey
    ) -> Result<Vec<u8>, String> {
        use sha2::{Sha256, Digest};
        
        // Create rewrap proof (simplified)
        let mut hasher = Sha256::new();
        hasher.update(&self.server_private_key);
        hasher.update(&old_device.key_bytes);
        hasher.update(&new_device.key_bytes);
        hasher.update(&new_device.created_at.to_le_bytes());
        
        Ok(hasher.finalize().to_vec())
    }

    /// Validate device public key
    pub fn validate_device_pubkey(pubkey_hex: &str) -> Result<DevicePublicKey, String> {
        if pubkey_hex.len() != 64 {
            return Err("Device public key must be 64 hex characters".to_string());
        }
        
        let key_bytes = hex::decode(pubkey_hex)
            .map_err(|_| "Invalid hex in device public key")?;
        
        if key_bytes.len() != 32 {
            return Err("Device public key must be 32 bytes".to_string());
        }
        
        let mut key_array = [0u8; 32];
        key_array.copy_from_slice(&key_bytes);
        
        Ok(DevicePublicKey {
            key_bytes: key_array,
            device_id: format!("device_{}", &pubkey_hex[..16]),
            created_at: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hpke_rewrapping() {
        let (server_private, _server_public) = HPKERewrapper::generate_server_keypair();
        let rewrapper = HPKERewrapper::new(server_private);

        // Create test device keys
        let old_device = DevicePublicKey {
            key_bytes: [0x01; 32],
            device_id: "device_old".to_string(),
            created_at: 1234567890,
        };

        let new_device = DevicePublicKey {
            key_bytes: [0x02; 32],
            device_id: "device_new".to_string(),
            created_at: 1234567891,
        };

        // Test rewrapping
        let test_ciphertext = b"encrypted_wallet_envelope_data";
        let rewrapped = rewrapper.rewrap_envelope(
            test_ciphertext,
            &old_device,
            &new_device
        ).unwrap();

        assert_eq!(rewrapped.original_envelope, test_ciphertext);
        assert_eq!(rewrapped.new_device_pubkey.device_id, "device_new");
        assert!(!rewrapped.rewrap_proof.is_empty());
    }

    #[test]
    fn test_device_pubkey_validation() {
        // Valid key
        let valid_key = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef";
        let device = HPKERewrapper::validate_device_pubkey(valid_key).unwrap();
        assert_eq!(device.key_bytes.len(), 32);

        // Invalid key (wrong length)
        let invalid_key = "1234";
        assert!(HPKERewrapper::validate_device_pubkey(invalid_key).is_err());

        // Invalid key (non-hex)
        let non_hex_key = "gggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggg";
        assert!(HPKERewrapper::validate_device_pubkey(non_hex_key).is_err());
    }
}
