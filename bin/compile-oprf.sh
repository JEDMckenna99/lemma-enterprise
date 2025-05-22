#!/bin/bash
set -e

echo "Compiling OPRF service..."
cd oprfservice
go build -o ../bin/oprfservice
chmod +x ../bin/oprfservice
echo "OPRF service compiled successfully"