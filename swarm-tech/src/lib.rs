#![no_std]

//! # Lemma Swarm Library
//! 
//! Shared utilities and types for ESP32 Lemma verification swarm implementation.
//! This library provides core functionality for secure offline BLE communication
//! with ZKP-based authorization verification.

pub mod crypto;
pub mod ble;
pub mod utils;

use heapless::{String, Vec};
use serde::{Deserialize, Serialize};

/// Maximum number of devices that can be tracked in the swarm
pub const MAX_SWARM_DEVICES: usize = 16;

/// Maximum size for device ID strings
pub const MAX_DEVICE_ID_LEN: usize = 32;

/// Maximum size for claim strings
pub const MAX_CLAIM_LEN: usize = 64;

/// BLE characteristic UUID for Lemma credential exchange
pub const LEMMA_BLE_UUID: &str = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E";

/// Error types for Lemma swarm operations
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LemmaSwarmError {
    /// Cryptographic operation failed
    CryptoError,
    /// Serialization/deserialization failed
    SerializationError,
    /// BLE communication error
    BleError,
    /// Invalid credential format
    InvalidCredential,
    /// Device not authorized
    NotAuthorized,
    /// Memory allocation failed
    OutOfMemory,
    /// Timeout occurred
    Timeout,
}

impl LemmaSwarmError {
    pub fn as_str(&self) -> &'static str {
        match self {
            LemmaSwarmError::CryptoError => "Cryptographic operation failed",
            LemmaSwarmError::SerializationError => "Serialization/deserialization failed",
            LemmaSwarmError::BleError => "BLE communication error",
            LemmaSwarmError::InvalidCredential => "Invalid credential format",
            LemmaSwarmError::NotAuthorized => "Device not authorized",
            LemmaSwarmError::OutOfMemory => "Memory allocation failed",
            LemmaSwarmError::Timeout => "Timeout occurred",
        }
    }
}

/// Device information for swarm participants
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SwarmDevice {
    pub device_id: String<MAX_DEVICE_ID_LEN>,
    pub last_seen: u64,
    pub trust_level: u8,
    pub verification_count: u32,
}

impl SwarmDevice {
    pub fn new(device_id: &str) -> Result<Self, LemmaSwarmError> {
        let mut id = String::new();
        id.push_str(device_id).map_err(|_| LemmaSwarmError::OutOfMemory)?;
        
        Ok(Self {
            device_id: id,
            last_seen: 0,
            trust_level: 50, // Default trust level
            verification_count: 0,
        })
    }
    
    pub fn update_trust(&mut self, successful_verification: bool) {
        if successful_verification {
            self.trust_level = (self.trust_level + 10).min(100);
            self.verification_count += 1;
        } else {
            self.trust_level = self.trust_level.saturating_sub(20);
        }
    }
}

/// Swarm network state management
#[derive(Debug)]
pub struct SwarmNetwork {
    devices: Vec<SwarmDevice, MAX_SWARM_DEVICES>,
    own_device_id: String<MAX_DEVICE_ID_LEN>,
}

impl SwarmNetwork {
    pub fn new(device_id: &str) -> Result<Self, LemmaSwarmError> {
        let mut own_id = String::new();
        own_id.push_str(device_id).map_err(|_| LemmaSwarmError::OutOfMemory)?;
        
        Ok(Self {
            devices: Vec::new(),
            own_device_id: own_id,
        })
    }
    
    pub fn add_device(&mut self, device: SwarmDevice) -> Result<(), LemmaSwarmError> {
        // Check if device already exists
        for existing_device in &mut self.devices {
            if existing_device.device_id == device.device_id {
                existing_device.last_seen = device.last_seen;
                return Ok(());
            }
        }
        
        // Add new device
        self.devices.push(device).map_err(|_| LemmaSwarmError::OutOfMemory)
    }
    
    pub fn get_device(&self, device_id: &str) -> Option<&SwarmDevice> {
        self.devices.iter().find(|d| d.device_id.as_str() == device_id)
    }
    
    pub fn get_device_mut(&mut self, device_id: &str) -> Option<&mut SwarmDevice> {
        self.devices.iter_mut().find(|d| d.device_id.as_str() == device_id)
    }
    
    pub fn device_count(&self) -> usize {
        self.devices.len()
    }
    
    pub fn trusted_devices(&self) -> impl Iterator<Item = &SwarmDevice> {
        self.devices.iter().filter(|d| d.trust_level >= 80)
    }
}

/// Crypto module for cryptographic operations
pub mod crypto {
    use super::LemmaSwarmError;
    
    /// Generate secure random bytes for key generation
    pub fn generate_random_bytes(buffer: &mut [u8]) -> Result<(), LemmaSwarmError> {
        // In real implementation, use hardware RNG from ESP32
        // For demo, use a deterministic but varied approach
        for (i, byte) in buffer.iter_mut().enumerate() {
            *byte = (i as u8).wrapping_mul(73).wrapping_add(157).wrapping_mul(211);
        }
        Ok(())
    }
    
    /// Timing-safe comparison for preventing timing attacks
    pub fn constant_time_compare(a: &[u8], b: &[u8]) -> bool {
        if a.len() != b.len() {
            return false;
        }
        
        let mut result = 0u8;
        for (a_byte, b_byte) in a.iter().zip(b.iter()) {
            result |= a_byte ^ b_byte;
        }
        result == 0
    }
}

/// BLE module for Bluetooth Low Energy communication
pub mod ble {
    use super::LemmaSwarmError;
    use heapless::Vec;
    
    /// Maximum BLE packet size for credential transmission
    pub const MAX_BLE_PACKET_SIZE: usize = 512;
    
    /// BLE packet structure for Lemma credentials
    #[derive(Debug, Clone)]
    pub struct BlePacket {
        pub data: Vec<u8, MAX_BLE_PACKET_SIZE>,
        pub sequence: u8,
        pub total_packets: u8,
    }
    
    impl BlePacket {
        pub fn new(data: &[u8], sequence: u8, total_packets: u8) -> Result<Self, LemmaSwarmError> {
            let mut packet_data = Vec::new();
            packet_data.extend_from_slice(data).map_err(|_| LemmaSwarmError::OutOfMemory)?;
            
            Ok(Self {
                data: packet_data,
                sequence,
                total_packets,
            })
        }
    }
    
    /// Fragment large credentials into BLE-sized packets
    pub fn fragment_credential(data: &[u8]) -> Result<Vec<BlePacket, 8>, LemmaSwarmError> {
        const PACKET_DATA_SIZE: usize = MAX_BLE_PACKET_SIZE - 2; // Reserve 2 bytes for headers
        let total_packets = ((data.len() + PACKET_DATA_SIZE - 1) / PACKET_DATA_SIZE) as u8;
        let mut packets = Vec::new();
        
        for (i, chunk) in data.chunks(PACKET_DATA_SIZE).enumerate() {
            let packet = BlePacket::new(chunk, i as u8, total_packets)?;
            packets.push(packet).map_err(|_| LemmaSwarmError::OutOfMemory)?;
        }
        
        Ok(packets)
    }
    
    /// Reassemble fragmented packets into complete credential
    pub fn reassemble_credential(packets: &[BlePacket]) -> Result<Vec<u8, 1024>, LemmaSwarmError> {
        if packets.is_empty() {
            return Err(LemmaSwarmError::InvalidCredential);
        }
        
        let mut data = Vec::new();
        for packet in packets {
            data.extend_from_slice(&packet.data).map_err(|_| LemmaSwarmError::OutOfMemory)?;
        }
        
        Ok(data)
    }
}

/// Utility functions
pub mod utils {
    /// Get current timestamp (simplified for embedded)
    pub fn get_timestamp() -> u64 {
        // In real implementation, use RTC or system timer
        static mut COUNTER: u64 = 0;
        unsafe {
            COUNTER += 1;
            COUNTER
        }
    }
    
    /// Calculate simple checksum for data integrity
    pub fn calculate_checksum(data: &[u8]) -> u16 {
        data.iter().fold(0u16, |acc, &byte| acc.wrapping_add(byte as u16))
    }
    
    /// Validate device ID format
    pub fn is_valid_device_id(device_id: &str) -> bool {
        !device_id.is_empty() 
            && device_id.len() <= super::MAX_DEVICE_ID_LEN 
            && device_id.chars().all(|c| c.is_alphanumeric() || c == '_' || c == '-')
    }
} 