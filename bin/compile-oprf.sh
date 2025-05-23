#!/bin/bash
set -e

echo "Compiling Mock OPRF service..."
cd oprfservice

# Initialize Go modules if needed
if [ ! -f "go.mod" ]; then
    echo "Initializing Go modules..."
    go mod init github.com/lemma/oprf-service
fi

# Download dependencies
echo "Downloading Go dependencies..."
go get -v github.com/gin-contrib/cors
go get -v github.com/gin-gonic/gin

# Build the simple mock service
echo "Building Mock OPRF service..."
go build -o ../bin/oprfservice simple_mock.go

# Make executable
chmod +x ../bin/oprfservice
echo "Mock OPRF service compiled successfully"