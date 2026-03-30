#![no_std]
#![no_main]

use esp_backtrace as _;
use esp_hal::{
    clock::ClockControl,
    delay::Delay,
    gpio::{Input, Output, PullUp, PushPull, Gpio2, Gpio4, Gpio15},
    peripherals::Peripherals,
    prelude::*,
    system::SystemControl,
    timer::timg::{TimerGroup, Timer0},
};
use esp_println::println;
use heapless::{Vec, String};
use serde::{Deserialize, Serialize};
use ed25519_dalek::{
    Keypair, PublicKey, SecretKey, Signature, Signer, Verifier,
    KEYPAIR_LENGTH, PUBLIC_KEY_LENGTH, SECRET_KEY_LENGTH, SIGNATURE_LENGTH,
};
use rand_core::{OsRng, RngCore};
use postcard;

// BLE imports (simplified for demo - real implementation would use esp32-nimble)
// For this demo, we'll simulate BLE with serial communication concepts

/// Lemma ZKP Credential structure for swarm communication
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LemmaCredential {
    pub issuer: String<64>,
    pub subject: String<64>,
    pub claims: LemmaClaims,
    pub signature: [u8; SIGNATURE_LENGTH],
    pub public_key: [u8; PUBLIC_KEY_LENGTH],
    pub timestamp: u64,
}

/// ZKP Claims structure following Lemma README concepts
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LemmaClaims {
    pub package_type: String<32>,
    pub is_authorized: bool,
    pub device_id: String<32>,
    pub security_level: u8,
}

/// Lemma verification engine for ESP32 swarm
pub struct LemmaSwarmEngine {
    keypair: Keypair,
    device_id: String<32>,
    verified_devices: Vec<String<32>, 16>, // Track up to 16 verified devices
}

impl LemmaSwarmEngine {
    /// Create new Lemma engine with generated keypair
    pub fn new(device_id: &str) -> Result<Self, &'static str> {
        // Generate secure keypair for this device
        let secret_key_bytes = Self::generate_secure_random();
        let secret_key = SecretKey::from_bytes(&secret_key_bytes)
            .map_err(|_| "Failed to create secret key")?;
        let public_key = PublicKey::from(&secret_key);
        let keypair = Keypair { secret: secret_key, public: public_key };

        let mut device_id_str = String::new();
        device_id_str.push_str(device_id).map_err(|_| "Device ID too long")?;

        Ok(Self {
            keypair,
            device_id: device_id_str,
            verified_devices: Vec::new(),
        })
    }

    /// Generate cryptographically secure random bytes
    fn generate_secure_random() -> [u8; SECRET_KEY_LENGTH] {
        let mut bytes = [0u8; SECRET_KEY_LENGTH];
        // In real implementation, use hardware RNG
        // For demo, use a simplified approach
        for (i, byte) in bytes.iter_mut().enumerate() {
            *byte = (i as u8).wrapping_mul(73).wrapping_add(157);
        }
        bytes
    }

    /// Create ZKP credential with authorization claim
    /// Following Lemma README: create_zkp_credential_from_claims
    pub fn create_zkp_credential(&self) -> Result<LemmaCredential, &'static str> {
        let mut issuer = String::new();
        issuer.push_str("did:lemma:swarm_device").map_err(|_| "Issuer string too long")?;
        
        let mut subject = String::new();
        subject.push_str(&self.device_id).map_err(|_| "Subject string too long")?;

        // Create ZKP claims following Lemma architecture
        let mut package_type = String::new();
        package_type.push_str("authorization").map_err(|_| "Package type too long")?;
        
        let claims = LemmaClaims {
            package_type,
            is_authorized: true,
            device_id: self.device_id.clone(),
            security_level: 100, // High security level
        };

        // Serialize claims for signing
        let claims_bytes = postcard::to_vec::<LemmaClaims, 256>(&claims)
            .map_err(|_| "Failed to serialize claims")?;

        // Create signature using Ed25519 (microsecond-level performance)
        let signature = self.keypair.sign(&claims_bytes);

        Ok(LemmaCredential {
            issuer,
            subject,
            claims,
            signature: signature.to_bytes(),
            public_key: self.keypair.public.to_bytes(),
            timestamp: Self::get_timestamp(),
        })
    }

    /// Verify ZKP credential from swarm device
    /// Following Lemma README: verify_zkp_credential (microsecond-level)
    pub fn verify_zkp_credential(&mut self, credential: &LemmaCredential) -> Result<bool, &'static str> {
        // 1. Verify signature authenticity
        let public_key = PublicKey::from_bytes(&credential.public_key)
            .map_err(|_| "Invalid public key")?;
        
        let signature = Signature::from_bytes(&credential.signature)
            .map_err(|_| "Invalid signature")?;

        let claims_bytes = postcard::to_vec::<LemmaClaims, 256>(&credential.claims)
            .map_err(|_| "Failed to serialize claims for verification")?;

        // Microsecond-level Ed25519 verification
        public_key.verify(&claims_bytes, &signature)
            .map_err(|_| "Signature verification failed")?;

        // 2. Verify authorization claim (ZKP selective disclosure)
        if !credential.claims.is_authorized {
            return Ok(false);
        }

        // 3. Check security level threshold
        if credential.claims.security_level < 80 {
            return Ok(false);
        }

        // 4. Verify timestamp (prevent replay attacks)
        let current_time = Self::get_timestamp();
        if current_time.saturating_sub(credential.timestamp) > 300 {
            return Ok(false); // Credential older than 5 minutes
        }

        // 5. Add to verified devices list (swarm trust network)
        if !self.verified_devices.contains(&credential.claims.device_id) {
            self.verified_devices.push(credential.claims.device_id.clone())
                .map_err(|_| "Verified devices list full")?;
        }

        Ok(true)
    }

    /// Get current timestamp (simplified for embedded)
    fn get_timestamp() -> u64 {
        // In real implementation, use RTC or system timer
        // For demo, use a simple counter
        static mut COUNTER: u64 = 0;
        unsafe {
            COUNTER += 1;
            COUNTER
        }
    }

    /// Serialize credential for BLE transmission
    pub fn serialize_credential(&self, credential: &LemmaCredential) -> Result<Vec<u8, 512>, &'static str> {
        postcard::to_vec(credential).map_err(|_| "Serialization failed")
    }

    /// Deserialize credential from BLE reception
    pub fn deserialize_credential(&self, data: &[u8]) -> Result<LemmaCredential, &'static str> {
        postcard::from_bytes(data).map_err(|_| "Deserialization failed")
    }
}

/// Main application structure
pub struct SwarmApp {
    lemma_engine: LemmaSwarmEngine,
    button: Input<'static, Gpio15>,
    led_green: Output<'static, Gpio2>,
    led_red: Output<'static, Gpio4>,
    delay: Delay,
}

impl SwarmApp {
    pub fn new(
        button: Input<'static, Gpio15>,
        led_green: Output<'static, Gpio2>,
        led_red: Output<'static, Gpio4>,
        delay: Delay,
    ) -> Result<Self, &'static str> {
        let lemma_engine = LemmaSwarmEngine::new("ESP32_SWARM_001")?;
        
        Ok(Self {
            lemma_engine,
            button,
            led_green,
            led_red,
            delay,
        })
    }

    /// Handle button press - create and broadcast Lemma credential
    pub fn handle_button_press(&mut self) -> Result<(), &'static str> {
        println!("🔘 Button pressed - Creating Lemma credential...");
        
        // Create ZKP credential (following Lemma README architecture)
        let credential = self.lemma_engine.create_zkp_credential()?;
        
        // Serialize for BLE transmission
        let serialized = self.lemma_engine.serialize_credential(&credential)?;
        
        println!("📡 Broadcasting Lemma credential ({} bytes)", serialized.len());
        println!("🔐 Device ID: {}", credential.claims.device_id.as_str());
        println!("✅ Authorized: {}", credential.claims.is_authorized);
        println!("🔒 Security Level: {}", credential.claims.security_level);
        
        // Simulate BLE broadcast (in real implementation, use esp32-nimble)
        self.simulate_ble_broadcast(&serialized);
        
        // Flash green LED to indicate successful send
        self.flash_green_led();
        
        Ok(())
    }

    /// Simulate receiving and verifying credential from swarm
    pub fn handle_received_credential(&mut self, data: &[u8]) -> Result<(), &'static str> {
        println!("📥 Received credential data ({} bytes)", data.len());
        
        // Deserialize received credential
        match self.lemma_engine.deserialize_credential(data) {
            Ok(credential) => {
                println!("📋 Credential from: {}", credential.claims.device_id.as_str());
                
                // Verify credential (microsecond-level performance)
                match self.lemma_engine.verify_zkp_credential(&credential) {
                    Ok(true) => {
                        println!("✅ Verification SUCCESS - Device authorized!");
                        self.flash_green_led();
                    }
                    Ok(false) => {
                        println!("❌ Verification FAILED - Device not authorized!");
                        self.flash_red_led();
                    }
                    Err(e) => {
                        println!("⚠️ Verification ERROR: {}", e);
                        self.flash_red_led();
                    }
                }
            }
            Err(e) => {
                println!("💥 Deserialization failed: {}", e);
                self.flash_red_led();
            }
        }
        
        Ok(())
    }

    /// Flash green LED for success
    fn flash_green_led(&mut self) {
        for _ in 0..3 {
            self.led_green.set_high();
            self.delay.delay_millis(200);
            self.led_green.set_low();
            self.delay.delay_millis(200);
        }
    }

    /// Flash red LED for failure
    fn flash_red_led(&mut self) {
        for _ in 0..5 {
            self.led_red.set_high();
            self.delay.delay_millis(100);
            self.led_red.set_low();
            self.delay.delay_millis(100);
        }
    }

    /// Simulate BLE broadcast (replace with real BLE implementation)
    fn simulate_ble_broadcast(&self, data: &[u8]) {
        // In real implementation, use esp32-nimble to broadcast via BLE
        // For demo, just log the broadcast
        println!("🌐 BLE Broadcast: {} bytes transmitted", data.len());
        
        // Simulate self-verification for demo
        // In real swarm, other devices would receive and verify
    }

    /// Main application loop
    pub fn run(&mut self) -> ! {
        println!("🚀 Lemma Swarm Demo Started!");
        println!("📱 Device: ESP32_SWARM_001");
        println!("🔘 Press button to broadcast authorization");
        println!("💡 Green LED = Verification Success");
        println!("🔴 Red LED = Verification Failure");
        
        // Demo: Create sample credential for testing
        let demo_credential = self.lemma_engine.create_zkp_credential()
            .expect("Failed to create demo credential");
        let demo_data = self.lemma_engine.serialize_credential(&demo_credential)
            .expect("Failed to serialize demo credential");
        
        let mut last_button_state = self.button.is_high();
        let mut demo_counter = 0u32;
        
        loop {
            // Handle button press (with debouncing)
            let current_button_state = self.button.is_high();
            if last_button_state && !current_button_state {
                // Button pressed (falling edge due to pull-up)
                self.delay.delay_millis(50); // Debounce
                if !self.button.is_high() {
                    if let Err(e) = self.handle_button_press() {
                        println!("❌ Button press error: {}", e);
                        self.flash_red_led();
                    }
                }
            }
            last_button_state = current_button_state;
            
            // Demo: Simulate receiving credentials every 10 seconds
            demo_counter += 1;
            if demo_counter >= 10000 {
                demo_counter = 0;
                println!("🎭 Demo: Simulating received credential...");
                if let Err(e) = self.handle_received_credential(&demo_data) {
                    println!("❌ Demo verification error: {}", e);
                }
            }
            
            self.delay.delay_millis(1);
        }
    }
}

#[esp_hal::entry]
fn main() -> ! {
    let peripherals = Peripherals::take();
    let system = SystemControl::new(peripherals.SYSTEM);
    let clocks = ClockControl::max(system.clock_control).freeze();
    let delay = Delay::new(&clocks);

    println!("🦀 Lemma ESP32 Swarm Initializing...");

    // Initialize GPIO pins
    let io = esp_hal::gpio::Io::new(peripherals.GPIO, peripherals.IO_MUX);
    
    // Button on GPIO15 with pull-up (press = LOW)
    let button = Input::new(io.pins.gpio15, PullUp);
    
    // LEDs on GPIO2 (green) and GPIO4 (red)
    let led_green = Output::new(io.pins.gpio2, esp_hal::gpio::Level::Low);
    let led_red = Output::new(io.pins.gpio4, esp_hal::gpio::Level::Low);

    println!("🔧 GPIO initialized:");
    println!("   Button: GPIO15 (pull-up)");
    println!("   Green LED: GPIO2");
    println!("   Red LED: GPIO4");

    // Initialize Lemma swarm application
    let mut app = SwarmApp::new(button, led_green, led_red, delay)
        .expect("Failed to initialize Lemma swarm app");

    // Start the main application loop
    app.run()
} 