#!/bin/bash
set -e

echo "Building OPRF service for Heroku deployment..."

# Change to the OPRF service directory
cd oprfservice

# Build the OPRF service binary
echo "Compiling OPRF service..."
go build -o ../bin/oprfservice main.go

# Make the binary executable
chmod +x ../bin/oprfservice

echo "OPRF service compiled successfully"

# Return to the root directory
cd ..

echo "Heroku build completed" 