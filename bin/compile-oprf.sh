#!/bin/bash
set -e

echo "Compiling OPRF service..."
cd oprfservice

# Initialize Go modules if needed
if [ ! -f "go.mod" ]; then
    echo "Initializing Go modules..."
    go mod init github.com/lemma/oprf-service
fi

# Download dependencies
echo "Downloading Go dependencies..."
go mod tidy
go get -v ./...

# Build the service
echo "Building OPRF service..."
go build -o ../bin/oprfservice

# Make executable
chmod +x ../bin/oprfservice
echo "OPRF service compiled successfully"