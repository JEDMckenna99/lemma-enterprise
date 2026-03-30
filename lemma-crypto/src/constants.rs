// Constants used throughout the lemma-crypto library

// Cryptographic size constants
pub const SCALAR_SIZE: usize = 32;
pub const POINT_SIZE: usize = 32;
pub const PUBLIC_KEY_SIZE: usize = 32;
pub const PRIVATE_KEY_SIZE: usize = 32;
pub const SIGNATURE_SIZE: usize = 64;

// Bloom filter constants
pub const DEFAULT_CASCADE_LEVELS: usize = 3;
pub const DEFAULT_BASE_CAPACITY: usize = 1000;
pub const DEFAULT_BASE_ERROR_RATE: f64 = 0.001;

// OPRF constants
pub const MAX_OPRF_CACHE_SIZE: usize = 1000;

// DID method identifier
pub const DID_METHOD: &str = "lemma";

// Context strings
pub const CREDENTIAL_CONTEXT: &[u8] = b"LEMMA_CREDENTIAL_V1";

// Re-export useful constants from curve25519-dalek
pub use curve25519_dalek::constants::RISTRETTO_BASEPOINT_TABLE; 