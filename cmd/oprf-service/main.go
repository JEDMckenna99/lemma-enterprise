// Simple Mock OPRF Service
//
// This is a simplified mock version of the OPRF service for testing purposes.
// It doesn't implement the actual OPRF protocol but provides compatible API endpoints.

package main

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
)

// Configuration holds all service configuration
type Config struct {
	Port          int
	KeyDir        string
	Debug         bool
	RateLimitPerM int // Rate limit requests per minute
	EnableMetrics bool
	RotationDays  int // Days between key rotations (0 = disabled)
}

// KeyMetadata stores information about OPRF keys
type KeyMetadata struct {
	KeyID       string    `json:"key_id"`
	CreatedAt   time.Time `json:"created_at"`
	ExpiresAt   time.Time `json:"expires_at"`
	IsActive    bool      `json:"is_active"`
	Description string    `json:"description"`
	PublicKey   string    `json:"public_key"` // Hex-encoded public key
}

// OPRF request structure
type OPRFRequest struct {
	BlindedElements []string `json:"blinded_elements"` // Base64-encoded blinded elements
	KeyID           string   `json:"key_id"`           // Optional key ID to use
}

// OPRF response structure
type OPRFResponse struct {
	EvaluatedElements []string `json:"evaluated_elements"` // Base64-encoded evaluated elements
	Epoch             string   `json:"epoch"`              // Current epoch (e.g., "2023-06-15")
	PublicKey         string   `json:"public_key"`         // Hex-encoded public key
	KeyID             string   `json:"key_id"`             // ID of the key used
}

// Status response structure
type StatusResponse struct {
	Status    string `json:"status"`
	Service   string `json:"service"`
	Version   string `json:"version"`
	Timestamp int64  `json:"timestamp"`
	Epoch     string `json:"epoch"`
}

// Global variables
var (
	// Key management
	oprfKeys    = make(map[string][]byte) // keyID -> private key
	publicKeys  = make(map[string][]byte) // keyID -> public key
	activeKeyID string
	keyMutex    sync.RWMutex
	initialized bool

	// Simple metrics
	evaluationCount int64
	rotationCount   int64
	metricsLock     sync.RWMutex

	// Metrics
	oprfEvaluationsTotal = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "oprf_evaluations_total",
		Help: "Total number of OPRF evaluations performed",
	})

	keyRotations = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "oprf_key_rotations_total",
		Help: "Total number of key rotations performed",
	})

	httpRequestsTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "http_requests_total",
		Help: "Total number of HTTP requests",
	}, []string{"method", "endpoint", "status"})
)

// Initialize OPRF service
func initializeOPRF(cfg Config) error {
	log.Printf("Initializing OPRF service with key directory: %s", cfg.KeyDir)

	// Create key directory if it doesn't exist
	if err := os.MkdirAll(cfg.KeyDir, 0700); err != nil {
		return fmt.Errorf("failed to create key directory: %w", err)
	}

	// Load existing keys
	keys, err := loadExistingKeys(cfg.KeyDir)
	if err != nil {
		return fmt.Errorf("failed to load existing keys: %w", err)
	}

	// Generate initial key if none exist
	if len(keys) == 0 {
		log.Println("No existing keys found, generating initial key")
		keyID, err := generateNewKey(cfg.KeyDir, cfg.RotationDays)
		if err != nil {
			return fmt.Errorf("failed to generate initial key: %w", err)
		}

		// Load the newly generated key
		privateKey, publicKey, err := loadKeyPair(cfg.KeyDir, keyID)
		if err != nil {
			return fmt.Errorf("failed to load newly generated key: %w", err)
		}
		oprfKeys[keyID] = privateKey
		publicKeys[keyID] = publicKey
	} else {
		// Load all keys
		for keyID := range keys {
			privateKey, publicKey, err := loadKeyPair(cfg.KeyDir, keyID)
			if err != nil {
				log.Printf("Warning: failed to load key pair %s: %v", keyID, err)
				continue
			}
			oprfKeys[keyID] = privateKey
			publicKeys[keyID] = publicKey
			log.Printf("Loaded key: %s", keyID)
		}
	}

	// Determine the active key (newest)
	var newestTime time.Time
	for keyID := range oprfKeys {
		meta, err := loadKeyMetadata(cfg.KeyDir, keyID)
		if err != nil {
			log.Printf("Warning: could not load metadata for key %s: %v", keyID, err)
			continue
		}

		if meta.IsActive && meta.CreatedAt.After(newestTime) {
			newestTime = meta.CreatedAt
			activeKeyID = keyID
		}
	}

	// If no active key was found, use the first one
	if activeKeyID == "" && len(oprfKeys) > 0 {
		for keyID := range oprfKeys {
			activeKeyID = keyID
			break
		}
	}

	log.Printf("Active key ID: %s", activeKeyID)

	// Set up key rotation if enabled
	if cfg.RotationDays > 0 {
		go keyRotationTask(cfg)
	}

	initialized = true
	return nil
}

// Load existing keys from the key directory
func loadExistingKeys(keyDir string) (map[string]bool, error) {
	keys := make(map[string]bool)

	files, err := ioutil.ReadDir(keyDir)
	if err != nil {
		if os.IsNotExist(err) {
			return keys, nil
		}
		return nil, fmt.Errorf("failed to read key directory: %w", err)
	}

	for _, file := range files {
		if file.IsDir() || !strings.HasSuffix(file.Name(), ".key") {
			continue
		}

		keyID := strings.TrimSuffix(file.Name(), ".key")
		keys[keyID] = true
	}

	return keys, nil
}

// Generate a new OPRF key pair with metadata
func generateNewKey(keyDir string, rotationDays int) (string, error) {
	// Generate a new random key ID
	keyIDBytes := make([]byte, 16)
	if _, err := rand.Read(keyIDBytes); err != nil {
		return "", fmt.Errorf("failed to generate random key ID: %w", err)
	}
	keyID := hex.EncodeToString(keyIDBytes)

	// Generate the private key (32 bytes for HMAC-SHA256)
	privateKey := make([]byte, 32)
	if _, err := rand.Read(privateKey); err != nil {
		return "", fmt.Errorf("failed to generate private key: %w", err)
	}

	// Generate corresponding public key (hash of private key for this simple implementation)
	publicKeyHash := sha256.Sum256(privateKey)
	publicKey := publicKeyHash[:]

	// Calculate expiry date
	now := time.Now().UTC()
	var expiresAt time.Time
	if rotationDays > 0 {
		expiresAt = now.AddDate(0, 0, rotationDays)
	} else {
		// If rotation is disabled, set a far future date
		expiresAt = now.AddDate(10, 0, 0)
	}

	// Create metadata
	metadata := KeyMetadata{
		KeyID:       keyID,
		CreatedAt:   now,
		ExpiresAt:   expiresAt,
		IsActive:    true,
		Description: fmt.Sprintf("OPRF key generated on %s", now.Format(time.RFC3339)),
		PublicKey:   hex.EncodeToString(publicKey),
	}

	// Save the key and metadata
	keyPath := filepath.Join(keyDir, keyID+".key")
	metaPath := filepath.Join(keyDir, keyID+".json")
	pubPath := filepath.Join(keyDir, keyID+".pub")

	// Save the private key
	keyHex := hex.EncodeToString(privateKey)
	if err := ioutil.WriteFile(keyPath, []byte(keyHex), 0600); err != nil {
		return "", fmt.Errorf("failed to save key: %w", err)
	}

	// Save the metadata
	metaJSON, err := json.MarshalIndent(metadata, "", "  ")
	if err != nil {
		return "", fmt.Errorf("failed to marshal metadata: %w", err)
	}
	if err := ioutil.WriteFile(metaPath, metaJSON, 0600); err != nil {
		return "", fmt.Errorf("failed to save metadata: %w", err)
	}

	// Save the public key
	pubKeyHex := hex.EncodeToString(publicKey)
	if err := ioutil.WriteFile(pubPath, []byte(pubKeyHex), 0644); err != nil {
		return "", fmt.Errorf("failed to save public key: %w", err)
	}

	return keyID, nil
}

// Load key pair from files
func loadKeyPair(keyDir string, keyID string) ([]byte, []byte, error) {
	// Load private key
	privateKey, err := loadKey(filepath.Join(keyDir, keyID+".key"))
	if err != nil {
		return nil, nil, fmt.Errorf("failed to load private key: %w", err)
	}

	// Load public key
	publicKey, err := loadKey(filepath.Join(keyDir, keyID+".pub"))
	if err != nil {
		return nil, nil, fmt.Errorf("failed to load public key: %w", err)
	}

	return privateKey, publicKey, nil
}

// Load key metadata from a file
func loadKeyMetadata(keyDir string, keyID string) (KeyMetadata, error) {
	var metadata KeyMetadata

	metaPath := filepath.Join(keyDir, keyID+".json")
	metaData, err := ioutil.ReadFile(metaPath)
	if err != nil {
		return metadata, fmt.Errorf("failed to read metadata file: %w", err)
	}

	if err := json.Unmarshal(metaData, &metadata); err != nil {
		return metadata, fmt.Errorf("failed to unmarshal metadata: %w", err)
	}

	return metadata, nil
}

// Load a key from a file
func loadKey(keyFile string) ([]byte, error) {
	// Read the key file
	keyHex, err := ioutil.ReadFile(keyFile)
	if err != nil {
		return nil, err
	}

	// Decode from hex
	keyBytes, err := hex.DecodeString(strings.TrimSpace(string(keyHex)))
	if err != nil {
		return nil, err
	}

	return keyBytes, nil
}

// OPRF-like evaluation using HMAC-SHA256
func evaluateOPRF(privateKey []byte, blindedElement []byte) []byte {
	// Use HMAC-SHA256 as our OPRF function
	// In a real OPRF, this would be a proper oblivious PRF evaluation
	mac := hmac.New(sha256.New, privateKey)
	mac.Write(blindedElement)
	return mac.Sum(nil)
}

// Key rotation task
func keyRotationTask(cfg Config) {
	for {
		// Sleep for a day
		time.Sleep(24 * time.Hour)

		// Check if we need to rotate the key
		keyMutex.RLock()
		currentKeyID := activeKeyID
		keyMutex.RUnlock()

		if currentKeyID == "" {
			log.Println("No active key found, generating a new one")
			keyMutex.Lock()
			keyID, err := generateNewKey(cfg.KeyDir, cfg.RotationDays)
			if err != nil {
				log.Printf("Failed to generate new key: %v", err)
				keyMutex.Unlock()
				continue
			}

			// Load the new key
			privateKey, publicKey, err := loadKeyPair(cfg.KeyDir, keyID)
			if err != nil {
				log.Printf("Failed to load new key: %v", err)
				keyMutex.Unlock()
				continue
			}

			// Update the active key
			oprfKeys[keyID] = privateKey
			publicKeys[keyID] = publicKey
			activeKeyID = keyID
			keyMutex.Unlock()

			log.Printf("Generated new key with ID: %s", keyID)
			metricsLock.Lock()
			rotationCount++
			metricsLock.Unlock()
			continue
		}

		// Check if the current key needs rotation
		meta, err := loadKeyMetadata(cfg.KeyDir, currentKeyID)
		if err != nil {
			log.Printf("Failed to load metadata for key %s: %v", currentKeyID, err)
			continue
		}

		// If the key is expired, generate a new one
		if time.Now().UTC().After(meta.ExpiresAt) {
			log.Printf("Key %s has expired, generating a new one", currentKeyID)
			keyMutex.Lock()

			// Generate a new key
			keyID, err := generateNewKey(cfg.KeyDir, cfg.RotationDays)
			if err != nil {
				log.Printf("Failed to generate new key: %v", err)
				keyMutex.Unlock()
				continue
			}

			// Load the new key
			privateKey, publicKey, err := loadKeyPair(cfg.KeyDir, keyID)
			if err != nil {
				log.Printf("Failed to load new key: %v", err)
				keyMutex.Unlock()
				continue
			}

			// Update the active key
			oprfKeys[keyID] = privateKey
			publicKeys[keyID] = publicKey
			activeKeyID = keyID

			// Mark the old key as inactive
			meta.IsActive = false
			metaJSON, err := json.MarshalIndent(meta, "", "  ")
			if err != nil {
				log.Printf("Failed to marshal metadata: %v", err)
				keyMutex.Unlock()
				continue
			}

			metaPath := filepath.Join(cfg.KeyDir, currentKeyID+".json")
			if err := ioutil.WriteFile(metaPath, metaJSON, 0600); err != nil {
				log.Printf("Failed to save metadata: %v", err)
				keyMutex.Unlock()
				continue
			}

			keyMutex.Unlock()

			log.Printf("Rotated key from %s to %s", currentKeyID, keyID)
			metricsLock.Lock()
			rotationCount++
			metricsLock.Unlock()
		}
	}
}

// Get the current epoch (YYYY-MM-DD)
func getCurrentEpoch() string {
	return time.Now().UTC().Format("2006-01-02")
}

// Simple rate limiter
type RateLimiter struct {
	requests map[string][]time.Time
	mu       sync.Mutex
	limit    int
	window   time.Duration
}

func NewRateLimiter(requestsPerMinute int) *RateLimiter {
	return &RateLimiter{
		requests: make(map[string][]time.Time),
		limit:    requestsPerMinute,
		window:   time.Minute,
	}
}

func (rl *RateLimiter) Allow(ip string) bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()

	// Clean up old requests
	requests := rl.requests[ip]
	var validRequests []time.Time
	for _, reqTime := range requests {
		if now.Sub(reqTime) <= rl.window {
			validRequests = append(validRequests, reqTime)
		}
	}

	// Check if we're under the limit
	if len(validRequests) >= rl.limit {
		return false
	}

	// Add this request
	validRequests = append(validRequests, now)
	rl.requests[ip] = validRequests

	return true
}

// Set up the Gin router with routes and middleware
func setupRouter(cfg Config) *gin.Engine {
	// Set Gin mode
	if cfg.Debug {
		gin.SetMode(gin.DebugMode)
	} else {
		gin.SetMode(gin.ReleaseMode)
	}

	r := gin.Default()

	// Configure CORS
	r.Use(cors.New(cors.Config{
		AllowOrigins:     []string{"*"},
		AllowMethods:     []string{"GET", "POST"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Accept"},
		ExposeHeaders:    []string{"Content-Length"},
		AllowCredentials: true,
		MaxAge:           12 * time.Hour,
	}))

	// Add rate limiting middleware if enabled
	var limiter *RateLimiter
	if cfg.RateLimitPerM > 0 {
		log.Printf("Rate limiting enabled: %d requests per minute", cfg.RateLimitPerM)
		limiter = NewRateLimiter(cfg.RateLimitPerM)

		r.Use(func(c *gin.Context) {
			if !limiter.Allow(c.ClientIP()) {
				c.JSON(http.StatusTooManyRequests, gin.H{
					"error": "Rate limit exceeded",
				})
				c.Abort()
				return
			}
			c.Next()
		})
	}

	// Health check endpoint
	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, StatusResponse{
			Status:    "ok",
			Service:   "lemma-oprf-service",
			Version:   "1.0.0",
			Timestamp: time.Now().Unix(),
			Epoch:     getCurrentEpoch(),
		})
	})

	// OPRF evaluation endpoint
	r.POST("/evaluate", func(c *gin.Context) {
		// Check if OPRF server is initialized
		if !initialized {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "OPRF server not initialized"})
			return
		}

		// Parse request
		var req OPRFRequest
		if err := c.BindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request format"})
			return
		}

		// Validate request
		if len(req.BlindedElements) == 0 {
			c.JSON(http.StatusBadRequest, gin.H{"error": "No blinded elements provided"})
			return
		}

		if len(req.BlindedElements) > 100 {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Too many elements (max 100)"})
			return
		}

		// Determine which key to use
		keyMutex.RLock()
		var privateKey []byte
		var publicKey []byte
		var keyID string

		// If a key ID was specified and exists
		if req.KeyID != "" && oprfKeys[req.KeyID] != nil {
			privateKey = oprfKeys[req.KeyID]
			publicKey = publicKeys[req.KeyID]
			keyID = req.KeyID
		} else {
			// Otherwise use the active key
			privateKey = oprfKeys[activeKeyID]
			publicKey = publicKeys[activeKeyID]
			keyID = activeKeyID
		}
		keyMutex.RUnlock()

		if privateKey == nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid key ID or no active key"})
			return
		}

		// Process each element
		evaluatedElements := make([]string, len(req.BlindedElements))
		for i, blindedStr := range req.BlindedElements {
			// Decode base64 string to bytes
			blindedBytes, err := base64.StdEncoding.DecodeString(blindedStr)
			if err != nil {
				c.JSON(http.StatusBadRequest, gin.H{
					"error": fmt.Sprintf("Invalid base64 encoding for element %d", i),
				})
				return
			}

			// Evaluate the OPRF function
			evaluation := evaluateOPRF(privateKey, blindedBytes)
			evaluatedElements[i] = base64.StdEncoding.EncodeToString(evaluation)
		}

		// Update metrics
		metricsLock.Lock()
		evaluationCount += int64(len(evaluatedElements))
		metricsLock.Unlock()

		// Return response
		c.JSON(http.StatusOK, OPRFResponse{
			EvaluatedElements: evaluatedElements,
			Epoch:             getCurrentEpoch(),
			PublicKey:         hex.EncodeToString(publicKey),
			KeyID:             keyID,
		})
	})

	// Get public key endpoint
	r.GET("/pubkey", func(c *gin.Context) {
		if !initialized {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "OPRF server not initialized"})
			return
		}

		// Get the key ID from the query parameter
		keyID := c.Query("key_id")

		// Determine which key to use
		keyMutex.RLock()
		var publicKey []byte
		var keyIDToUse string

		// If a key ID was specified and exists
		if keyID != "" && publicKeys[keyID] != nil {
			publicKey = publicKeys[keyID]
			keyIDToUse = keyID
		} else {
			// Otherwise use the active key
			publicKey = publicKeys[activeKeyID]
			keyIDToUse = activeKeyID
		}
		keyMutex.RUnlock()

		if publicKey == nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid key ID or no active key"})
			return
		}

		c.JSON(http.StatusOK, gin.H{
			"public_key": hex.EncodeToString(publicKey),
			"key_id":     keyIDToUse,
			"epoch":      getCurrentEpoch(),
		})
	})

	// Metrics endpoint (if enabled)
	if cfg.EnableMetrics {
		r.GET("/metrics", func(c *gin.Context) {
			metricsLock.RLock()
			evaluations := evaluationCount
			rotations := rotationCount
			metricsLock.RUnlock()

			c.JSON(http.StatusOK, gin.H{
				"oprf_evaluations_total":   evaluations,
				"oprf_key_rotations_total": rotations,
				"active_key_id":            activeKeyID,
				"total_keys":               len(oprfKeys),
			})
		})
	}

	return r
}

func main() {
	// Configuration with defaults
	cfg := Config{
		Port:          8080,
		KeyDir:        "./keys",
		Debug:         false,
		RateLimitPerM: 60, // 60 requests per minute default
		EnableMetrics: true,
		RotationDays:  30, // Rotate keys every 30 days
	}

	// Parse environment variables
	if port := os.Getenv("PORT"); port != "" {
		if p, err := strconv.Atoi(port); err == nil {
			cfg.Port = p
		}
	}

	if keyDir := os.Getenv("KEYDIR"); keyDir != "" {
		cfg.KeyDir = keyDir
	}

	if debug := os.Getenv("DEBUG"); debug == "true" {
		cfg.Debug = true
	}

	if rateLimit := os.Getenv("RATE_LIMIT"); rateLimit != "" {
		if r, err := strconv.Atoi(rateLimit); err == nil {
			cfg.RateLimitPerM = r
		}
	}

	if metrics := os.Getenv("ENABLE_METRICS"); metrics == "false" {
		cfg.EnableMetrics = false
	}

	if rotationDays := os.Getenv("ROTATION_DAYS"); rotationDays != "" {
		if r, err := strconv.Atoi(rotationDays); err == nil {
			cfg.RotationDays = r
		}
	}

	// Initialize OPRF service
	if err := initializeOPRF(cfg); err != nil {
		log.Fatalf("Failed to initialize OPRF service: %v", err)
	}

	// Set up router
	r := setupRouter(cfg)

	// Start server
	addr := fmt.Sprintf(":%d", cfg.Port)
	log.Printf("Starting OPRF service on %s", addr)
	log.Printf("Key directory: %s", cfg.KeyDir)
	log.Printf("Debug mode: %v", cfg.Debug)
	log.Printf("Rate limiting: %d requests/minute", cfg.RateLimitPerM)
	log.Printf("Metrics enabled: %v", cfg.EnableMetrics)
	log.Printf("Key rotation: %d days", cfg.RotationDays)

	if err := r.Run(addr); err != nil {
		log.Fatalf("Server failed to start: %v", err)
	}
}
