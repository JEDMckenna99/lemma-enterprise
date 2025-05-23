package main

import (
    "fmt"
    "log"
    "net/http"
    "os"
    "encoding/json"
)

// Simple response structures
type StatusResponse struct {
    Status  string `json:"status"`
    Service string `json:"service"`
    Version string `json:"version"`
}

type EvaluateRequest struct {
    BlindedElement string `json:"blinded_element"`
    KeyID          string `json:"key_id"`
}

type EvaluateResponse struct {
    EvaluatedElement string `json:"evaluated_element"`
    KeyID            string `json:"key_id"`
    Proof            string `json:"proof"`
}

func main() {
    port := os.Getenv("PORT")
    if port == "" {
        port = "8080"
    }

    // Root endpoint
    http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
        fmt.Fprintf(w, "OPRF Service is running!")
    })

    // Status endpoint
    http.HandleFunc("/status", func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        response := StatusResponse{
            Status:  "ok",
            Service: "oprf",
            Version: "1.0.0",
        }
        json.NewEncoder(w).Encode(response)
    })

    // Evaluate endpoint
    http.HandleFunc("/evaluate", func(w http.ResponseWriter, r *http.Request) {
        if r.Method != "POST" {
            http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
            return
        }

        var request EvaluateRequest
        if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
            http.Error(w, "Invalid request", http.StatusBadRequest)
            return
        }

        // In a real implementation, this would perform the OPRF evaluation
        // For now, we just return a mock response
        response := EvaluateResponse{
            EvaluatedElement: "X9876543210abcdef",
            KeyID:            request.KeyID,
            Proof:            "Xabcdef1234567890",
        }

        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode(response)
    })

    log.Printf("Starting OPRF service on port %s", port)
    if err := http.ListenAndServe(":"+port, nil); err != nil {
        log.Fatal(err)
    }
}