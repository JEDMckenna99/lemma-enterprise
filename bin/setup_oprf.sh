#!/bin/bash
set -e

echo "Setting up OPRF service..."

# Create the keys directory if it doesn't exist
mkdir -p instance/data/keys

# Check if we already have keys
if [ ! -f instance/data/keys/oprf_key.json ]; then
    echo "Generating OPRF keys..."
    cd oprfservice
    go run keygen/keygen.go -keyfile ../instance/data/keys/oprf_key.json
    cd ..
else
    echo "OPRF keys already exist"
fi

# Build the OPRF service binary
echo "Building OPRF service binary..."
cd oprfservice
go build -o ../bin/oprfservice
cd ..

# Make the binary executable
chmod +x bin/oprfservice

echo "OPRF service setup complete!" 