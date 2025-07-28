@echo off

REM Performance Test Suite Runner
echo 🚀 Lemma Performance Test Suite Runner
echo ======================================

REM Check if we're in the correct directory
if not exist "Cargo.toml" (
    echo ❌ Error: Please run this script from the lemma-crypto directory
    exit /b 1
)

REM Run the performance tests
echo 📊 Running performance tests...
cargo test --release --test performance_test_suite test_performance_suite -- --nocapture

REM Check if tests passed
if %errorlevel% neq 0 (
    echo ❌ Performance tests failed!
    exit /b 1
) else (
    echo ✅ Performance tests completed successfully!
)

REM Run individual component tests
echo 🔍 Running individual component tests...
cargo test --release --test performance_test_suite test_individual_components -- --nocapture

REM Check if tests passed
if %errorlevel% neq 0 (
    echo ❌ Individual component tests failed!
    exit /b 1
) else (
    echo ✅ Individual component tests completed successfully!
)

echo 🎉 All performance tests completed!
echo 📊 Performance suite is ready for continuous monitoring
pause 