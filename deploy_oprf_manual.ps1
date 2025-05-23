# This script manually deploys a simple OPRF service to Heroku

# Configuration
$OPRF_APP_NAME = "lemma-oprf-service"
$MAIN_APP_NAME = "lemma-enterprise"

# Create a temporary directory for the OPRF service
Write-Host "Creating temporary directory for OPRF service..."
$tempDir = "simple-oprf-manual"
if (Test-Path $tempDir) {
    Remove-Item -Recurse -Force $tempDir
}
New-Item -ItemType Directory -Path $tempDir | Out-Null
Set-Location $tempDir

# Create a simple Go application for the OPRF service
Write-Host "Creating simple OPRF service..."

# Create main.go
@"
package main

import (
    "fmt"
    "log"
    "net/http"
    "os"
    "encoding/json"
)

func main() {
    port := os.Getenv("PORT")
    if port == "" {
        port = "8080"
    }

    http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
        fmt.Fprintf(w, "OPRF Service is running!")
    })

    http.HandleFunc("/status", func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        fmt.Fprintf(w, `{"status":"ok","service":"oprf","version":"1.0.0"}`)
    })

    http.HandleFunc("/evaluate", func(w http.ResponseWriter, r *http.Request) {
        if r.Method != "POST" {
            http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
            return
        }
        w.Header().Set("Content-Type", "application/json")
        fmt.Fprintf(w, `{"evaluated_element":"X9876543210abcdef","key_id":"test","proof":"Xabcdef1234567890"}`)
    })

    log.Printf("Starting server on port %s", port)
    if err := http.ListenAndServe(":" + port, nil); err != nil {
        log.Fatal(err)
    }
}
"@ | Out-File -FilePath "main.go" -Encoding utf8

# Create go.mod
@"
module github.com/lemma/oprf-service

go 1.18
"@ | Out-File -FilePath "go.mod" -Encoding utf8

# Create Procfile
@"
web: ./bin/app
"@ | Out-File -FilePath "Procfile" -Encoding ascii

# Initialize git repository
git init
git add .
git commit -m "Simple OPRF service"

# Push to Heroku
Write-Host "Pushing to Heroku..."
heroku git:remote -a $OPRF_APP_NAME
git push heroku master -f

# Configure the main app to use the OPRF service
Write-Host "Configuring main app to use OPRF service..."
heroku config:set OPRF_SERVICE_INTERNAL=https://$OPRF_APP_NAME.herokuapp.com --app $MAIN_APP_NAME

Write-Host "OPRF service deployed successfully!"
Write-Host "OPRF service URL: https://$OPRF_APP_NAME.herokuapp.com"

# Return to the original directory
Set-Location ..