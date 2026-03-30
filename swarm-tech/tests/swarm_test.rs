#![cfg(test)]

//! Unit tests for Lemma ESP32 Swarm functionality
//! 
//! These tests run on the host machine (x86) with mocked hardware functionality
//! to validate the cryptographic operations and business logic.

use lemma_swarm::{
    crypto, ble, utils, 
    LemmaSwarmError, SwarmDevice, SwarmNetwork,
    MAX_DEVICE_ID_LEN, MAX_SWARM_DEVICES
};

// Mock the main module structures for testing
use heapless::{String, Vec};
use serde::{Deserialize, Serialize};

/// Mock Ed25519 constants for testing
const SIGNATURE_LENGTH: usize = 64;
const PUBLIC_KEY_LENGTH: usize = 32;
const SECRET_KEY_LENGTH: usize = 32;

/// Mock Lemma credential structure for testing
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
struct MockLemmaCredential {
    pub issuer: String<64>,
    pub subject: String<64>,
    pub claims: MockLemmaClaims,
    pub signature: [u8; SIGNATURE_LENGTH],
    pub public_key: [u8; PUBLIC_KEY_LENGTH],
    pub timestamp: u64,
}

/// Mock claims structure for testing
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
struct MockLemmaClaims {
    pub package_type: String<32>,
    pub is_authorized: bool,
    pub device_id: String<32>,
    pub security_level: u8,
}

/// Mock Lemma engine for testing without hardware dependencies
struct MockLemmaEngine {
    device_id: String<MAX_DEVICE_ID_LEN>,
    keypair: ([u8; SECRET_KEY_LENGTH], [u8; PUBLIC_KEY_LENGTH]),
}

impl MockLemmaEngine {
    fn new(device_id: &str) -> Result<Self, LemmaSwarmError> {
        let mut id = String::new();
        id.push_str(device_id).map_err(|_| LemmaSwarmError::OutOfMemory)?;
        
        // Generate mock keypair
        let mut secret_key = [0u8; SECRET_KEY_LENGTH];
        let mut public_key = [0u8; PUBLIC_KEY_LENGTH];
        crypto::generate_random_bytes(&mut secret_key)?;
        crypto::generate_random_bytes(&mut public_key)?;
        
        Ok(Self {
            device_id: id,
            keypair: (secret_key, public_key),
        })
    }
    
    fn create_mock_credential(&self) -> Result<MockLemmaCredential, LemmaSwarmError> {
        let mut issuer = String::new();
        issuer.push_str("did:lemma:test_device").map_err(|_| LemmaSwarmError::OutOfMemory)?;
        
        let mut package_type = String::new();
        package_type.push_str("authorization").map_err(|_| LemmaSwarmError::OutOfMemory)?;
        
        let claims = MockLemmaClaims {
            package_type,
            is_authorized: true,
            device_id: self.device_id.clone(),
            security_level: 100,
        };
        
        // Mock signature (in real implementation, this would be Ed25519)
        let mut signature = [0u8; SIGNATURE_LENGTH];
        crypto::generate_random_bytes(&mut signature)?;
        
        Ok(MockLemmaCredential {
            issuer,
            subject: self.device_id.clone(),
            claims,
            signature,
            public_key: self.keypair.1,
            timestamp: utils::get_timestamp(),
        })
    }
    
    fn verify_mock_credential(&self, credential: &MockLemmaCredential) -> Result<bool, LemmaSwarmError> {
        // Mock verification logic
        if !credential.claims.is_authorized {
            return Ok(false);
        }
        
        if credential.claims.security_level < 80 {
            return Ok(false);
        }
        
        // Check timestamp freshness (within 5 minutes = 300 timestamp units)
        let current_time = utils::get_timestamp();
        if current_time.saturating_sub(credential.timestamp) > 300 {
            return Ok(false);
        }
        
        // In real implementation, verify Ed25519 signature here
        Ok(true)
    }
}

#[test]
fn test_device_creation() {
    let device = SwarmDevice::new("TEST_DEVICE_001").unwrap();
    assert_eq!(device.device_id.as_str(), "TEST_DEVICE_001");
    assert_eq!(device.trust_level, 50);
    assert_eq!(device.verification_count, 0);
    assert_eq!(device.last_seen, 0);
}

#[test]
fn test_device_creation_long_id() {
    let long_id = "A".repeat(MAX_DEVICE_ID_LEN + 1);
    let result = SwarmDevice::new(&long_id);
    assert_eq!(result.unwrap_err(), LemmaSwarmError::OutOfMemory);
}

#[test]
fn test_device_trust_update() {
    let mut device = SwarmDevice::new("TEST_DEVICE").unwrap();
    
    // Test successful verification
    device.update_trust(true);
    assert_eq!(device.trust_level, 60);
    assert_eq!(device.verification_count, 1);
    
    // Test failed verification
    device.update_trust(false);
    assert_eq!(device.trust_level, 40);
    assert_eq!(device.verification_count, 1); // Count only increases on success
    
    // Test trust level caps at 100
    for _ in 0..10 {
        device.update_trust(true);
    }
    assert_eq!(device.trust_level, 100);
}

#[test]
fn test_swarm_network_creation() {
    let network = SwarmNetwork::new("SWARM_MASTER").unwrap();
    assert_eq!(network.device_count(), 0);
}

#[test]
fn test_swarm_network_add_device() {
    let mut network = SwarmNetwork::new("SWARM_MASTER").unwrap();
    let device1 = SwarmDevice::new("DEVICE_001").unwrap();
    let device2 = SwarmDevice::new("DEVICE_002").unwrap();
    
    // Add first device
    network.add_device(device1).unwrap();
    assert_eq!(network.device_count(), 1);
    
    // Add second device
    network.add_device(device2).unwrap();
    assert_eq!(network.device_count(), 2);
    
    // Verify device lookup
    let found_device = network.get_device("DEVICE_001").unwrap();
    assert_eq!(found_device.device_id.as_str(), "DEVICE_001");
    
    // Test non-existent device
    assert!(network.get_device("NONEXISTENT").is_none());
}

#[test]
fn test_swarm_network_device_update() {
    let mut network = SwarmNetwork::new("SWARM_MASTER").unwrap();
    let device = SwarmDevice::new("DEVICE_001").unwrap();
    
    network.add_device(device).unwrap();
    
    // Update device trust level
    {
        let device_mut = network.get_device_mut("DEVICE_001").unwrap();
        device_mut.update_trust(true);
    }
    
    let updated_device = network.get_device("DEVICE_001").unwrap();
    assert_eq!(updated_device.trust_level, 60);
}

#[test]
fn test_swarm_network_capacity() {
    let mut network = SwarmNetwork::new("SWARM_MASTER").unwrap();
    
    // Fill network to capacity
    for i in 0..MAX_SWARM_DEVICES {
        let device_id = format!("DEVICE_{:03}", i);
        let device = SwarmDevice::new(&device_id).unwrap();
        network.add_device(device).unwrap();
    }
    
    assert_eq!(network.device_count(), MAX_SWARM_DEVICES);
    
    // Try to add one more device (should fail)
    let overflow_device = SwarmDevice::new("OVERFLOW_DEVICE").unwrap();
    let result = network.add_device(overflow_device);
    assert_eq!(result.unwrap_err(), LemmaSwarmError::OutOfMemory);
}

#[test]
fn test_swarm_network_trusted_devices() {
    let mut network = SwarmNetwork::new("SWARM_MASTER").unwrap();
    
    // Add devices with different trust levels
    let mut device1 = SwarmDevice::new("HIGH_TRUST").unwrap();
    device1.trust_level = 90;
    
    let mut device2 = SwarmDevice::new("LOW_TRUST").unwrap();
    device2.trust_level = 50;
    
    let mut device3 = SwarmDevice::new("MED_TRUST").unwrap();
    device3.trust_level = 85;
    
    network.add_device(device1).unwrap();
    network.add_device(device2).unwrap();
    network.add_device(device3).unwrap();
    
    // Count trusted devices (>= 80 trust level)
    let trusted_count = network.trusted_devices().count();
    assert_eq!(trusted_count, 2); // HIGH_TRUST and MED_TRUST
}

#[test]
fn test_crypto_random_bytes() {
    let mut buffer1 = [0u8; 32];
    let mut buffer2 = [0u8; 32];
    
    crypto::generate_random_bytes(&mut buffer1).unwrap();
    crypto::generate_random_bytes(&mut buffer2).unwrap();
    
    // Buffers should be different (very high probability)
    assert_ne!(buffer1, buffer2);
    
    // Buffers should not be all zeros
    assert_ne!(buffer1, [0u8; 32]);
    assert_ne!(buffer2, [0u8; 32]);
}

#[test]
fn test_crypto_constant_time_compare() {
    let data1 = [1, 2, 3, 4, 5];
    let data2 = [1, 2, 3, 4, 5];
    let data3 = [1, 2, 3, 4, 6];
    let data4 = [1, 2, 3, 4];
    
    // Same data should match
    assert!(crypto::constant_time_compare(&data1, &data2));
    
    // Different data should not match
    assert!(!crypto::constant_time_compare(&data1, &data3));
    
    // Different lengths should not match
    assert!(!crypto::constant_time_compare(&data1, &data4));
}

#[test]
fn test_ble_packet_creation() {
    let test_data = b"Hello, Lemma Swarm!";
    let packet = ble::BlePacket::new(test_data, 0, 1).unwrap();
    
    assert_eq!(packet.sequence, 0);
    assert_eq!(packet.total_packets, 1);
    assert_eq!(packet.data.as_slice(), test_data);
}

#[test]
fn test_ble_credential_fragmentation() {
    let large_data = vec![0xAAu8; 1000];
    let packets = ble::fragment_credential(&large_data).unwrap();
    
    assert!(packets.len() > 1); // Should be fragmented
    assert_eq!(packets[0].sequence, 0);
    assert_eq!(packets[0].total_packets, packets.len() as u8);
    
    // Verify all packets have same total_packets value
    for packet in &packets {
        assert_eq!(packet.total_packets, packets.len() as u8);
    }
}

#[test]
fn test_ble_credential_reassembly() {
    let original_data = b"This is a test credential for BLE fragmentation and reassembly";
    let packets = ble::fragment_credential(original_data).unwrap();
    let reassembled = ble::reassemble_credential(&packets).unwrap();
    
    assert_eq!(reassembled.as_slice(), original_data);
}

#[test]
fn test_utils_timestamp() {
    let timestamp1 = utils::get_timestamp();
    let timestamp2 = utils::get_timestamp();
    
    // Timestamps should be increasing
    assert!(timestamp2 > timestamp1);
}

#[test]
fn test_utils_checksum() {
    let data1 = b"Hello, World!";
    let data2 = b"Hello, World!";
    let data3 = b"Hello, Lemma!";
    
    let checksum1 = utils::calculate_checksum(data1);
    let checksum2 = utils::calculate_checksum(data2);
    let checksum3 = utils::calculate_checksum(data3);
    
    // Same data should have same checksum
    assert_eq!(checksum1, checksum2);
    
    // Different data should have different checksum (very high probability)
    assert_ne!(checksum1, checksum3);
}

#[test]
fn test_utils_device_id_validation() {
    // Valid device IDs
    assert!(utils::is_valid_device_id("ESP32_001"));
    assert!(utils::is_valid_device_id("DEVICE-123"));
    assert!(utils::is_valid_device_id("Swarm_Node_A"));
    assert!(utils::is_valid_device_id("123ABC"));
    
    // Invalid device IDs
    assert!(!utils::is_valid_device_id(""));                    // Empty
    assert!(!utils::is_valid_device_id("DEVICE@123"));         // Invalid character
    assert!(!utils::is_valid_device_id("DEVICE 123"));         // Space
    assert!(!utils::is_valid_device_id(&"A".repeat(MAX_DEVICE_ID_LEN + 1))); // Too long
}

#[test]
fn test_mock_lemma_engine_creation() {
    let engine = MockLemmaEngine::new("TEST_ENGINE").unwrap();
    assert_eq!(engine.device_id.as_str(), "TEST_ENGINE");
}

#[test]
fn test_mock_credential_creation() {
    let engine = MockLemmaEngine::new("TEST_ENGINE").unwrap();
    let credential = engine.create_mock_credential().unwrap();
    
    assert_eq!(credential.issuer.as_str(), "did:lemma:test_device");
    assert_eq!(credential.subject.as_str(), "TEST_ENGINE");
    assert_eq!(credential.claims.device_id.as_str(), "TEST_ENGINE");
    assert!(credential.claims.is_authorized);
    assert_eq!(credential.claims.security_level, 100);
    assert_eq!(credential.claims.package_type.as_str(), "authorization");
}

#[test]
fn test_mock_credential_verification() {
    let engine = MockLemmaEngine::new("TEST_ENGINE").unwrap();
    let credential = engine.create_mock_credential().unwrap();
    
    // Valid credential should verify
    assert!(engine.verify_mock_credential(&credential).unwrap());
    
    // Test unauthorized credential
    let mut unauthorized_credential = credential.clone();
    unauthorized_credential.claims.is_authorized = false;
    assert!(!engine.verify_mock_credential(&unauthorized_credential).unwrap());
    
    // Test low security level
    let mut low_security_credential = credential.clone();
    low_security_credential.claims.security_level = 50;
    assert!(!engine.verify_mock_credential(&low_security_credential).unwrap());
}

#[test]
fn test_mock_credential_serialization() {
    let engine = MockLemmaEngine::new("TEST_ENGINE").unwrap();
    let credential = engine.create_mock_credential().unwrap();
    
    // Serialize and deserialize
    let serialized = postcard::to_vec::<MockLemmaCredential, 512>(&credential).unwrap();
    let deserialized: MockLemmaCredential = postcard::from_bytes(&serialized).unwrap();
    
    assert_eq!(credential, deserialized);
}

#[test]
fn test_error_message_display() {
    assert_eq!(LemmaSwarmError::CryptoError.as_str(), "Cryptographic operation failed");
    assert_eq!(LemmaSwarmError::SerializationError.as_str(), "Serialization/deserialization failed");
    assert_eq!(LemmaSwarmError::BleError.as_str(), "BLE communication error");
    assert_eq!(LemmaSwarmError::InvalidCredential.as_str(), "Invalid credential format");
    assert_eq!(LemmaSwarmError::NotAuthorized.as_str(), "Device not authorized");
    assert_eq!(LemmaSwarmError::OutOfMemory.as_str(), "Memory allocation failed");
    assert_eq!(LemmaSwarmError::Timeout.as_str(), "Timeout occurred");
}

/// Integration test that simulates a complete swarm interaction
#[test]
fn test_swarm_integration() {
    // Create two mock engines representing different ESP32 devices
    let engine_a = MockLemmaEngine::new("ESP32_SWARM_A").unwrap();
    let engine_b = MockLemmaEngine::new("ESP32_SWARM_B").unwrap();
    
    // Create swarm network
    let mut network = SwarmNetwork::new("SWARM_MASTER").unwrap();
    
    // Device A creates and broadcasts credential
    let credential_a = engine_a.create_mock_credential().unwrap();
    let serialized_a = postcard::to_vec::<MockLemmaCredential, 512>(&credential_a).unwrap();
    
    // Simulate BLE transmission by fragmenting and reassembling
    let packets_a = ble::fragment_credential(&serialized_a).unwrap();
    let received_data_a = ble::reassemble_credential(&packets_a).unwrap();
    let received_credential_a: MockLemmaCredential = postcard::from_bytes(&received_data_a).unwrap();
    
    // Device B verifies credential from Device A
    let verification_result_a = engine_b.verify_mock_credential(&received_credential_a).unwrap();
    assert!(verification_result_a, "Device B should verify Device A's credential");
    
    // Add Device A to network based on successful verification
    if verification_result_a {
        let device_a = SwarmDevice::new(&received_credential_a.claims.device_id).unwrap();
        network.add_device(device_a).unwrap();
    }
    
    // Device B creates and broadcasts credential
    let credential_b = engine_b.create_mock_credential().unwrap();
    let serialized_b = postcard::to_vec::<MockLemmaCredential, 512>(&credential_b).unwrap();
    let packets_b = ble::fragment_credential(&serialized_b).unwrap();
    let received_data_b = ble::reassemble_credential(&packets_b).unwrap();
    let received_credential_b: MockLemmaCredential = postcard::from_bytes(&received_data_b).unwrap();
    
    // Device A verifies credential from Device B
    let verification_result_b = engine_a.verify_mock_credential(&received_credential_b).unwrap();
    assert!(verification_result_b, "Device A should verify Device B's credential");
    
    // Add Device B to network
    if verification_result_b {
        let device_b = SwarmDevice::new(&received_credential_b.claims.device_id).unwrap();
        network.add_device(device_b).unwrap();
    }
    
    // Verify swarm network state
    assert_eq!(network.device_count(), 2);
    assert!(network.get_device("ESP32_SWARM_A").is_some());
    assert!(network.get_device("ESP32_SWARM_B").is_some());
    
    println!("✅ Swarm integration test completed successfully!");
    println!("   - Device A credential verified by Device B");
    println!("   - Device B credential verified by Device A");
    println!("   - Swarm network contains {} devices", network.device_count());
} 