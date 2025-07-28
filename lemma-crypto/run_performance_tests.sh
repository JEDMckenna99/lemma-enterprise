#!/bin/bash

# Performance Test Suite Runner
echo "🚀 Lemma Performance Test Suite Runner"
echo "======================================"

# Check if we're in the correct directory
if [ ! -f "Cargo.toml" ]; then
    echo "❌ Error: Please run this script from the lemma-crypto directory"
    exit 1
fi

# Run the performance tests
echo "📊 Running performance tests..."
cargo test --release --test performance_test_suite test_performance_suite -- --nocapture

# Check if tests passed
if [ $? -eq 0 ]; then
    echo "✅ Performance tests completed successfully!"
else
    echo "❌ Performance tests failed!"
    exit 1
fi

# Run individual component tests
echo "🔍 Running individual component tests..."
cargo test --release --test performance_test_suite test_individual_components -- --nocapture

# Check if tests passed
if [ $? -eq 0 ]; then
    echo "✅ Individual component tests completed successfully!"
else
    echo "❌ Individual component tests failed!"
    exit 1
fi

echo "🎉 All performance tests completed!"
echo "📊 Performance suite is ready for continuous monitoring" 