#!/bin/bash
set -e

# Build the OPRF service from the oprfservice directory
cd oprfservice
go build -o ../bin/oprfservice

# Make the binary executable
chmod +x ../bin/oprfservice

echo "OPRF service compiled successfully" 