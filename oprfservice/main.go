// Simple Mock OPRF Service
//
// This is a simplified mock version of the OPRF service for testing purposes.
// It doesn't implement the actual OPRF protocol but provides compatible API endpoints.

package main

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
)

// Command line flags
var (
	portFlag    = flag.Int("port", 8080, "Port to run the OPRF service on")
	keyDirFlag  = flag.String("keydir", "./keys", "Directory for key storage")
	debugFlag   = flag.Bool("debug", false, "Enable debug mode")
)

// Request and response structures
type OPRFRequest struct {
	Alpha []string `json:"alpha"` // Base64-encoded blinded elements
	KeyID string   `json:"key_id"` // Optional key ID to use
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

// Configuration
type Config struct {
	Port    int
	KeyDir  string
	Debug   bool
}

// Mock OPRF evaluation - simply applies SHA-256 to the input
func mockEvaluate(input string) string {
	hash := sha256.Sum256([]byte("oprf-mock-" + input))
	return base64.StdEncoding.EncodeToString(hash[:])
}

// Get current date as epoch string
func getCurrentEpoch() string {
	return time.Now().Format("2006-01-02")
}

// Create router with endpoints
func setupRouter(cfg Config) *gin.Engine {
	if cfg.Debug {
		gin.SetMode(gin.DebugMode)
	} else {
		gin.SetMode(gin.ReleaseMode)
	}

	r := gin.Default()

	// Configure CORS
	r.Use(cors.New(cors.Config{
		AllowOrigins:     []string{"*"},
		AllowMethods:     []string{"GET", "POST", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Accept", "Authorization"},
		ExposeHeaders:    []string{"Content-Length"},
		AllowCredentials: true,
		MaxAge:           12 * time.Hour,
	}))

	// Health check endpoint
	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, StatusResponse{
			Status:    "ok",
			Service:   "lemma-oprf-service-mock",
			Version:   "1.0.0",
			Timestamp: time.Now().Unix(),
			Epoch:     getCurrentEpoch(),
		})
	})

	// Public key endpoint - returns a mock key
	r.GET("/pubkey", func(c *gin.Context) {
		mockPubKey := sha256.Sum256([]byte("lemma-mock-key"))
		c.JSON(http.StatusOK, gin.H{
			"publicKey": hex.EncodeToString(mockPubKey[:]),
			"key_id":    "mock-key-1",
			"epoch":     getCurrentEpoch(),
		})
	})

	// OPRF evaluation endpoint
	r.POST("/oprfeval", func(c *gin.Context) {
		var req OPRFRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		// Process each input
		beta := make([]string, 0, len(req.Alpha))
		for _, alpha := range req.Alpha {
			evaluated := mockEvaluate(alpha)
			beta = append(beta, evaluated)
		}

		mockPubKey := sha256.Sum256([]byte("lemma-mock-key"))
		c.JSON(http.StatusOK, OPRFResponse{
			Beta:      beta,
			Epoch:     getCurrentEpoch(),
			PublicKey: hex.EncodeToString(mockPubKey[:]),
			KeyID:     "mock-key-1",
		})
	})

	return r
}

func main() {
	flag.Parse()

	// Create configuration
	cfg := Config{
		Port:    *portFlag,
		KeyDir:  *keyDirFlag,
		Debug:   *debugFlag,
	}

	// Override port from environment if available (for Heroku)
	if port := os.Getenv("PORT"); port != "" {
		fmt.Sscanf(port, "%d", &cfg.Port)
	}

	// Ensure key directory exists
	if err := os.MkdirAll(cfg.KeyDir, 0755); err != nil {
		log.Fatalf("Failed to create key directory: %v", err)
	}

	// Create a mock key file if needed
	mockKeyFile := filepath.Join(cfg.KeyDir, "mock_key.txt")
	if _, err := os.Stat(mockKeyFile); os.IsNotExist(err) {
		mockKey := sha256.Sum256([]byte("lemma-mock-key"))
		if err := os.WriteFile(mockKeyFile, []byte(hex.EncodeToString(mockKey[:])), 0600); err != nil {
			log.Printf("Warning: Failed to write mock key file: %v", err)
		}
	}

	// Set up router
	router := setupRouter(cfg)

	// Start server
	log.Printf("Starting mock OPRF service on port %d", cfg.Port)
	if err := router.Run(fmt.Sprintf(":%d", cfg.Port)); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
} 