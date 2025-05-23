#!/bin/bash
set -e

echo "=== Starting Heroku build process ==="

# Make scripts executable
chmod +x bin/*.sh

# Install Go for OPRF service
echo "=== Installing Go ==="
curl -L https://go.dev/dl/go1.18.linux-amd64.tar.gz -o go.tar.gz
tar -C /tmp -xzf go.tar.gz
export PATH=$PATH:/tmp/go/bin
go version

# Compile OPRF service
echo "=== Compiling OPRF service ==="
./bin/compile-oprf.sh

# Ensure directories exist
mkdir -p instance/data/keys
mkdir -p instance/data/revocation/cascades

echo "=== Build completed successfully ===" 