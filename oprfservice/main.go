// OPRF Service for Lemma Human Verification System
//
// This microservice provides an endpoint for evaluating Oblivious Pseudorandom
// Functions (OPRFs) according to RFC 9497 using the ristretto255 elliptic curve.
//
// The service maintains its private key securely and evaluates blinded inputs
// without learning the original values, providing privacy-preserving revocation
// checks for the Lemma ecosystem.

package main

import (
	"crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/cloudflare/circl/oprf"
	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"golang.org/x/time/rate"
)

// Command line flags
var (
	portFlag         = flag.Int("port", 8080, "Port to run the OPRF service on")
	keyFileFlag      = flag.String("keyfile", "oprf_key.hex", "File storing the OPRF private key")
	keyDirFlag       = flag.String("keydir", "./keys", "Directory for key storage")
	generateFlag     = flag.Bool("generate", false, "Generate a new key and exit")
	debugFlag        = flag.Bool("debug", false, "Enable debug mode")
	rateLimitFlag    = flag.Int("ratelimit", 60, "Rate limit requests per minute (0 to disable)")
	metricsFlag      = flag.Bool("metrics", true, "Enable Prometheus metrics")
	rotationDaysFlag = flag.Int("rotationdays", 30, "Number of days before key rotation (0 to disable)")
)

// Global server variables
var (
	suite        = oprf.SuiteRistretto255
	oprfServers  = make(map[string]oprf.Server) // Map from key ID to OPRF server
	activeKeyID  string                         // Current active key ID
	previousKeys = make(map[string][]byte)      // Map of previous keys for verification
	initialized  = false
	keyMutex     sync.RWMutex                   // Mutex for key access
)

// Prometheus metrics
var (
	oprfRequestsTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "oprf_requests_total",
		Help: "The total number of OPRF evaluation requests",
	}, []string{"status"})

	oprfEvaluationsTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "oprf_evaluations_total",
		Help: "The total number of OPRF evaluations performed",
	})

	oprfLatency = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "oprf_request_duration_seconds",
		Help:    "Duration of OPRF requests in seconds",
		Buckets: prometheus.DefBuckets,
	}, []string{"endpoint"})

	rateLimitExceeded = promauto.NewCounter(prometheus.CounterOpts{
		Name: "oprf_rate_limit_exceeded_total",
		Help: "The total number of times the rate limit was exceeded",
	})

	keyRotations = promauto.NewCounter(prometheus.CounterOpts{
		Name: "oprf_key_rotations_total",
		Help: "The total number of key rotations performed",
	})
)

// Configuration
type Config struct {
	Port          int
	KeyFile       string
	KeyDir        string
	Debug         bool
	RateLimitPerM int    // Rate limit requests per minute
	EnableMetrics bool
	RotationDays  int    // Days between key rotations
}

// KeyMetadata stores information about a key
type KeyMetadata struct {
	KeyID       string    `json:"key_id"`
	CreatedAt   time.Time `json:"created_at"`
	ExpiresAt   time.Time `json:"expires_at"`
	IsActive    bool      `json:"is_active"`
	Description string    `json:"description"`
}

// Request and response structures
type OPRFRequest struct {
	Alpha  []string `json:"alpha"`  // Base64-encoded blinded elements
	KeyID  string   `json:"key_id"` // Optional key ID to use
}

type OPRFResponse struct {
	Beta      []string `json:"beta"`      // Base64-encoded evaluated elements
	Epoch     string   `json:"epoch"`     // Current epoch (e.g., "2023-06-15")
	PublicKey string   `json:"publicKey"` // Hex-encoded public key
	KeyID     string   `json:"key_id"`    // ID of the key used
}

type StatusResponse struct {
	Status    string `json:"status"`
	Service   string `json:"service"`
	Version   string `json:"version"`
	Timestamp int64  `json:"timestamp"`
	Epoch     string `json:"epoch"`
}

// RateLimiter provides a simple rate limiting implementation
type RateLimiter struct {
	limiters map[string]*rate.Limiter
	mu       sync.RWMutex
	r        rate.Limit
	b        int
}

// NewRateLimiter creates a new rate limiter
func NewRateLimiter(r rate.Limit, b int) *RateLimiter {
	return &RateLimiter{
		limiters: make(map[string]*rate.Limiter),
		r:        r,
		b:        b,
	}
}

// GetLimiter gets a limiter for a particular key
func (l *RateLimiter) GetLimiter(key string) *rate.Limiter {
	l.mu.RLock()
	limiter, exists := l.limiters[key]
	l.mu.RUnlock()

	if !exists {
		l.mu.Lock()
		limiter, exists = l.limiters[key]
		if !exists {
			limiter = rate.NewLimiter(l.r, l.b)
			l.limiters[key] = limiter
		}
		l.mu.Unlock()
	}

	return limiter
}

// CleanupTask removes old limiters to avoid memory leaks
func (l *RateLimiter) CleanupTask(interval time.Duration) {
	ticker := time.NewTicker(interval)
	for range ticker.C {
		l.mu.Lock()
		// Could implement more sophisticated cleanup - for now, just ensure map doesn't grow too large
		if len(l.limiters) > 10000 {
			l.limiters = make(map[string]*rate.Limiter)
			log.Println("Rate limiter map was too large, cleared it")
		}
		l.mu.Unlock()
	}
}

// LimiterMiddleware creates a middleware for rate limiting by IP
func LimiterMiddleware(limiter *RateLimiter, enableMetrics bool) gin.HandlerFunc {
	return func(c *gin.Context) {
		key := c.ClientIP()
		if !limiter.GetLimiter(key).Allow() {
			if enableMetrics {
				rateLimitExceeded.Inc()
			}
			c.JSON(http.StatusTooManyRequests, gin.H{
				"error": "Rate limit exceeded",
			})
			c.Abort()
			return
		}
		c.Next()
	}
}

// MetricsMiddleware creates a middleware for recording request durations
func MetricsMiddleware(enableMetrics bool) gin.HandlerFunc {
	return func(c *gin.Context) {
		if !enableMetrics {
			c.Next()
			return
		}

		start := time.Now()
		path := c.FullPath()
		
		c.Next()
		
		status := fmt.Sprintf("%d", c.Writer.Status())
		duration := time.Since(start).Seconds()
		
		// Record metrics
		oprfLatency.WithLabelValues(path).Observe(duration)
		
		// Only count OPRF-related requests
		if path == "/oprfeval" || path == "/pubkey" {
			oprfRequestsTotal.WithLabelValues(status).Inc()
		}
	}
}

// Initialize the OPRF servers with keys
func initializeOPRF(cfg Config) error {
	// Create key directory if it doesn't exist
	if err := os.MkdirAll(cfg.KeyDir, 0700); err != nil {
		return fmt.Errorf("failed to create key directory: %w", err)
	}

	// Check if we have any keys already
	keys, err := loadExistingKeys(cfg.KeyDir)
	if err != nil {
		return err
	}

	// If no keys, generate a new one
	if len(keys) == 0 {
		keyID, err := generateNewKey(cfg.KeyDir, cfg.RotationDays)
		if err != nil {
			return err
		}
		log.Printf("Generated new key with ID: %s", keyID)
		
		// Load the keys again
		keys, err = loadExistingKeys(cfg.KeyDir)
		if err != nil {
			return err
		}
	}

	// Create OPRF servers for each key
	for keyID, privateKey := range keys {
		server, err := oprf.NewServer(suite, privateKey)
		if err != nil {
			return fmt.Errorf("failed to create OPRF server for key %s: %w", keyID, err)
		}
		oprfServers[keyID] = server
		log.Printf("Loaded key: %s", keyID)
	}

	// Determine the active key (newest)
	var newestTime time.Time
	for keyID := range keys {
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
	if activeKeyID == "" && len(keys) > 0 {
		for keyID := range keys {
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
func loadExistingKeys(keyDir string) (map[string][]byte, error) {
	keys := make(map[string][]byte)
	
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
		keyPath := filepath.Join(keyDir, file.Name())
		
		privateKey, err := loadKey(keyPath)
		if err != nil {
			log.Printf("Warning: failed to load key %s: %v", keyPath, err)
			continue
		}

		keys[keyID] = privateKey
	}

	return keys, nil
}

// Generate a new key with an expiration date
func generateNewKey(keyDir string, rotationDays int) (string, error) {
	// Generate a new random key ID
	keyIDBytes := make([]byte, 16)
	if _, err := rand.Read(keyIDBytes); err != nil {
		return "", fmt.Errorf("failed to generate random key ID: %w", err)
	}
	keyID := hex.EncodeToString(keyIDBytes)

	// Generate the private key
	privateKey, err := suite.GenerateKey()
	if err != nil {
		return "", fmt.Errorf("failed to generate key: %w", err)
	}

	// Get the public key
	oprfServer, err := oprf.NewServer(suite, privateKey)
	if err != nil {
		return "", fmt.Errorf("failed to create OPRF server: %w", err)
	}
	publicKey := oprfServer.GetPublicKey().Serialize()

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
			keyPath := filepath.Join(cfg.KeyDir, keyID+".key")
			privateKey, err := loadKey(keyPath)
			if err != nil {
				log.Printf("Failed to load new key: %v", err)
				keyMutex.Unlock()
				continue
			}
			
			// Create a new OPRF server
			server, err := oprf.NewServer(suite, privateKey)
			if err != nil {
				log.Printf("Failed to create OPRF server: %v", err)
				keyMutex.Unlock()
				continue
			}
			
			// Update the active key
			oprfServers[keyID] = server
			activeKeyID = keyID
			keyMutex.Unlock()
			
			log.Printf("Generated new key with ID: %s", keyID)
			if cfg.EnableMetrics {
				keyRotations.Inc()
			}
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
			keyPath := filepath.Join(cfg.KeyDir, keyID+".key")
			privateKey, err := loadKey(keyPath)
			if err != nil {
				log.Printf("Failed to load new key: %v", err)
				keyMutex.Unlock()
				continue
			}
			
			// Create a new OPRF server
			server, err := oprf.NewServer(suite, privateKey)
			if err != nil {
				log.Printf("Failed to create OPRF server: %v", err)
				keyMutex.Unlock()
				continue
			}
			
			// Update the active key
			oprfServers[keyID] = server
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
			if cfg.EnableMetrics {
				keyRotations.Inc()
			}
		}
	}
}

// Generate a new OPRF private key and save it to a file
func generateKey(keyFile string) ([]byte, error) {
	// Generate a new private key
	privateKey, err := suite.GenerateKey()
	if err != nil {
		return nil, err
	}

	// Encode the key as hex
	keyHex := hex.EncodeToString(privateKey)

	// Save to file
	err = ioutil.WriteFile(keyFile, []byte(keyHex), 0600)
	if err != nil {
		return nil, err
	}

	log.Printf("Generated new OPRF key and saved to %s\n", keyFile)
	return privateKey, nil
}

// Load an OPRF private key from a file
func loadKey(keyFile string) ([]byte, error) {
	// Read the key file
	keyHex, err := ioutil.ReadFile(keyFile)
	if err != nil {
		return nil, err
	}

	// Decode from hex
	privateKey, err := hex.DecodeString(strings.TrimSpace(string(keyHex)))
	if err != nil {
		return nil, err
	}

	return privateKey, nil
}

// Get the current epoch (YYYY-MM-DD)
func getCurrentEpoch() string {
	return time.Now().UTC().Format("2006-01-02")
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

	// Add metrics middleware
	if cfg.EnableMetrics {
		r.Use(MetricsMiddleware(true))
	}

	// Add rate limiting middleware if enabled
	if cfg.RateLimitPerM > 0 {
		log.Printf("Rate limiting enabled: %d requests per minute\n", cfg.RateLimitPerM)
		// Convert requests per minute to requests per second
		rps := rate.Limit(cfg.RateLimitPerM) / 60
		
		// Create a new rate limiter with a burst of 5 and requests per second limit
		limiter := NewRateLimiter(rps, 5)
		
		// Start the cleanup task to prevent memory leaks
		go limiter.CleanupTask(10 * time.Minute)
		
		// Apply the rate limiter middleware to all routes
		r.Use(LimiterMiddleware(limiter, cfg.EnableMetrics))
	}

	// Health check endpoint
	r.GET("/health", func(c *gin.Context) {
		keyMutex.RLock()
		currentKeyID := activeKeyID
		keyMutex.RUnlock()
		
		c.JSON(http.StatusOK, StatusResponse{
			Status:    "ok",
			Service:   "lemma-oprf-service",
			Version:   "1.0.0",
			Timestamp: time.Now().Unix(),
			Epoch:     getCurrentEpoch(),
		})
	})

	// OPRF evaluation endpoint
	r.POST("/oprfeval", func(c *gin.Context) {
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
		if len(req.Alpha) == 0 {
			c.JSON(http.StatusBadRequest, gin.H{"error": "No blinded elements provided"})
			return
		}

		if len(req.Alpha) > 100 {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Too many elements (max 100)"})
			return
		}

		// Determine which key to use
		keyMutex.RLock()
		var server oprf.Server
		var keyID string
		
		// If a key ID was specified and exists
		if req.KeyID != "" && oprfServers[req.KeyID] != nil {
			server = oprfServers[req.KeyID]
			keyID = req.KeyID
		} else {
			// Otherwise use the active key
			server = oprfServers[activeKeyID]
			keyID = activeKeyID
		}
		keyMutex.RUnlock()
		
		if server == nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid key ID or no active key"})
			return
		}

		// Process each element
		elements := make([]oprf.Element, len(req.Alpha))
		for i, alphaStr := range req.Alpha {
			// Decode base64 string to bytes
			alphaBytes, err := base64.StdEncoding.DecodeString(alphaStr)
			if err != nil {
				c.JSON(http.StatusBadRequest, gin.H{
					"error": fmt.Sprintf("Invalid base64 encoding for element %d", i),
				})
				return
			}

			// Deserialize to OPRF element
			elements[i] = suite.NewElement()
			err = elements[i].Deserialize(alphaBytes)
			if err != nil {
				c.JSON(http.StatusBadRequest, gin.H{
					"error": fmt.Sprintf("Invalid element format for element %d", i),
				})
				return
			}
		}

		// Evaluate the OPRF function
		evaluations, err := server.Evaluate(elements)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "OPRF evaluation failed"})
			return
		}

		// Convert evaluations to response format
		betaValues := make([]string, len(evaluations))
		for i, eval := range evaluations {
			betaBytes := eval.Serialize()
			betaValues[i] = base64.StdEncoding.EncodeToString(betaBytes)
		}

		// Get public key
		publicKey := server.GetPublicKey().Serialize()
		publicKeyHex := hex.EncodeToString(publicKey)

		// Update metrics
		if cfg.EnableMetrics {
			oprfEvaluationsTotal.Add(float64(len(evaluations)))
		}

		// Return response
		c.JSON(http.StatusOK, OPRFResponse{
			Beta:      betaValues,
			Epoch:     getCurrentEpoch(),
			PublicKey: publicKeyHex,
			KeyID:     keyID,
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
		var server oprf.Server
		var keyIDToUse string
		
		// If a key ID was specified and exists
		if keyID != "" && oprfServers[keyID] != nil {
			server = oprfServers[keyID]
			keyIDToUse = keyID
		} else {
			// Otherwise use the active key
			server = oprfServers[activeKeyID]
			keyIDToUse = activeKeyID
		}
		keyMutex.RUnlock()
		
		if server == nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid key ID or no active key"})
			return
		}

		publicKey := server.GetPublicKey().Serialize()
		publicKeyHex := hex.EncodeToString(publicKey)

		c.JSON(http.StatusOK, gin.H{
			"publicKey": publicKeyHex,
			"epoch":     getCurrentEpoch(),
			"algorithm": "ristretto255",
			"key_id":    keyIDToUse,
		})
	})

	// List keys endpoint
	r.GET("/keys", func(c *gin.Context) {
		if !initialized {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "OPRF server not initialized"})
			return
		}

		// Get all key metadata
		keyMutex.RLock()
		keyIDs := make([]string, 0, len(oprfServers))
		for keyID := range oprfServers {
			keyIDs = append(keyIDs, keyID)
		}
		currentActiveKey := activeKeyID
		keyMutex.RUnlock()

		// Build response
		keyList := make([]map[string]interface{}, 0, len(keyIDs))
		for _, keyID := range keyIDs {
			// Try to load metadata
			meta, err := loadKeyMetadata(cfg.KeyDir, keyID)
			if err != nil {
				log.Printf("Warning: could not load metadata for key %s: %v", keyID, err)
				// Include basic info even without metadata
				keyList = append(keyList, map[string]interface{}{
					"key_id":    keyID,
					"is_active": keyID == currentActiveKey,
				})
				continue
			}

			// Include full metadata
			keyInfo := map[string]interface{}{
				"key_id":     meta.KeyID,
				"created_at": meta.CreatedAt,
				"expires_at": meta.ExpiresAt,
				"is_active":  meta.IsActive && keyID == currentActiveKey,
				"description": meta.Description,
			}
			keyList = append(keyList, keyInfo)
		}

		c.JSON(http.StatusOK, gin.H{
			"keys":        keyList,
			"active_key":  currentActiveKey,
			"total_keys":  len(keyIDs),
			"epoch":       getCurrentEpoch(),
		})
	})

	// Metrics endpoint for Prometheus
	if cfg.EnableMetrics {
		log.Println("Enabling Prometheus metrics endpoint at /metrics")
		r.GET("/metrics", gin.WrapH(promhttp.Handler()))
	}

	// Simple status metrics for non-Prometheus consumers
	r.GET("/status", func(c *gin.Context) {
		keyMutex.RLock()
		keyCount := len(oprfServers)
		currentActiveKey := activeKeyID
		keyMutex.RUnlock()
		
		c.JSON(http.StatusOK, gin.H{
			"uptime":        time.Now().Unix(),
			"epochs_served": 1,  // Would track actual epochs
			"evaluations":   0,  // Would track evaluations
			"epoch":         getCurrentEpoch(),
			"rateLimit":     cfg.RateLimitPerM,
			"metrics":       cfg.EnableMetrics,
			"keys":          keyCount,
			"active_key":    currentActiveKey,
		})
	})

	return r
}

func main() {
	// Parse command line flags
	flag.Parse()

	// Create configuration
	cfg := Config{
		Port:          *portFlag,
		KeyFile:       *keyFileFlag,
		KeyDir:        *keyDirFlag,
		Debug:         *debugFlag,
		RateLimitPerM: *rateLimitFlag,
		EnableMetrics: *metricsFlag,
		RotationDays:  *rotationDaysFlag,
	}

	// Handle generate flag
	if *generateFlag {
		_, err := generateKey(cfg.KeyFile)
		if err != nil {
			log.Fatalf("Failed to generate key: %v", err)
		}
		os.Exit(0)
	}

	// Initialize OPRF servers
	err := initializeOPRF(cfg)
	if err != nil {
		log.Fatalf("Failed to initialize OPRF servers: %v", err)
	}

	// Set up router
	r := setupRouter(cfg)

	// Start the server
	addr := fmt.Sprintf(":%d", cfg.Port)
	log.Printf("Starting OPRF service on %s", addr)
	log.Printf("Rate limiting: %d requests per minute", cfg.RateLimitPerM)
	log.Printf("Prometheus metrics: %v", cfg.EnableMetrics)
	log.Printf("Key rotation: %d days", cfg.RotationDays)
	if err := r.Run(addr); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
} 