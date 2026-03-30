#!/bin/bash

echo "🔐 Lemma Crypto Test Runner"
echo "=========================="

# Function to run a specific test category
run_test_category() {
    local category=$1
    local description=$2
    
    echo ""
    echo "🧪 Running $description..."
    echo "----------------------------------------"
    
    if [ "$category" = "all" ]; then
        cargo test --release
    else
        cargo test --release "$category"
    fi
    
    if [ $? -eq 0 ]; then
        echo "✅ $description PASSED"
    else
        echo "❌ $description FAILED"
        return 1
    fi
}

# Function to run benchmarks
run_benchmarks() {
    echo ""
    echo "📊 Running Performance Benchmarks..."
    echo "----------------------------------------"
    
    cargo bench
    
    if [ $? -eq 0 ]; then
        echo "✅ Benchmarks completed successfully"
    else
        echo "❌ Benchmarks failed"
        return 1
    fi
}

# Main execution
echo ""
echo "Select test category:"
echo "1. Core Crypto Tests (comprehensive)"
echo "2. Stress Tests (performance & security)"
echo "3. Integration Tests (existing tests)"
echo "4. All Tests"
echo "5. Benchmarks"
echo "6. Quick Test (basic functionality)"
echo ""

read -p "Enter choice (1-6): " choice

case $choice in
    1)
        run_test_category "core_crypto_tests" "Core Crypto Tests"
        ;;
    2)
        run_test_category "stress_test" "Stress Tests"
        ;;
    3)
        run_test_category "integration" "Integration Tests"
        ;;
    4)
        run_test_category "all" "All Tests"
        ;;
    5)
        run_benchmarks
        ;;
    6)
        echo ""
        echo "🚀 Running Quick Test..."
        echo "----------------------------------------"
        cargo test --release test_lemma_verify_identity_success test_oprf_privacy_preserving_operations test_cascaded_bloom_filter_revocation
        ;;
    *)
        echo "Invalid choice. Running all tests..."
        run_test_category "all" "All Tests"
        ;;
esac

echo ""
echo "🎯 Test Results Summary:"
echo "========================"
echo "Check the output above for detailed results."
echo ""
echo "To run specific tests manually:"
echo "  cargo test test_lemma_verify_identity_success"
echo "  cargo test stress_test_oprf_operations"
echo "  cargo test test_cascaded_bloom_filter_revocation"
echo ""
echo "To run with verbose output:"
echo "  cargo test -- --nocapture"
echo ""
echo "To run benchmarks:"
echo "  cargo bench" 