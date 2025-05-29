#!/bin/bash
# Heroku pre-build hook to compile OPRF service

set -e

echo "🚀 === Heroku Pre-Build: Compiling OPRF Service (Mock Version) ==="
echo "📝 Note: Using mock implementation while main.go compatibility is fixed"

# Check if we're in a Heroku build environment
if [[ -n "$SOURCE_VERSION" && -n "$BUILD_DIR" ]]; then
    echo "✅ Detected Heroku build environment"
    echo "Build dir: $BUILD_DIR"
    echo "Source version: $SOURCE_VERSION"
else
    echo "⚠️  Running outside Heroku build environment"
fi

# Ensure we're in the right directory
if [[ ! -d "oprfservice" ]]; then
    echo "❌ oprfservice directory not found. Are we in the right location?"
    pwd
    ls -la
    exit 1
fi

# Check Go installation
echo "🔍 Checking Go installation:"
which go || echo "Go not found in PATH"
go version || echo "Go version check failed"

# Ensure bin directory exists
mkdir -p bin

# Navigate to OPRF service directory
cd oprfservice

echo "📂 Current directory: $(pwd)"
echo "📝 Files in oprfservice:"
ls -la

# Check Go module status
echo "🔍 Checking Go modules:"
if [[ -f "go.mod" ]]; then
    echo "✅ go.mod found"
    head -10 go.mod
else
    echo "❌ go.mod not found"
    exit 1
fi

# Download dependencies
echo "📦 Downloading Go dependencies..."
go mod download || {
    echo "❌ Failed to download dependencies"
    exit 1
}

# Verify simple_mock.go exists
if [[ ! -f "simple_mock.go" ]]; then
    echo "❌ simple_mock.go not found in oprfservice directory"
    exit 1
fi

echo "🔨 Building OPRF service (Mock Version)..."
# Build with verbose output and proper binary name
go build -v -ldflags="-s -w" -o ../bin/oprf-service simple_mock.go || {
    echo "❌ Go build failed"
    exit 1
}

# Return to root directory
cd ..

# Verify binary was created
if [[ -f "bin/oprf-service" ]]; then
    echo "✅ OPRF service binary created successfully!"
    ls -la bin/oprf-service
    
    # Make sure it's executable
    chmod +x bin/oprf-service
    
    # Show binary info
    file bin/oprf-service || echo "file command not available"
    
    echo "🎉 OPRF service (Mock) ready for deployment!"
    echo "📝 Note: This uses mock implementation for compatibility"
else
    echo "❌ Binary was not created at bin/oprf-service"
    echo "Contents of bin directory:"
    ls -la bin/ || echo "bin directory doesn't exist"
    exit 1
fi

echo "✅ === Heroku Pre-Build Complete ===" 