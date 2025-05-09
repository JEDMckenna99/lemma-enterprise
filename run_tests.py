#!/usr/bin/env python3
"""
Test runner script for Lemma Enterprise.
Runs all tests and generates a coverage report.
"""
import os
import sys
import pytest

def main():
    """Run all tests and generate coverage report."""
    print("Running Lemma Enterprise tests...")
    
    # Add the current directory to the path
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    
    # Run pytest with coverage
    args = [
        "-v",
        "--cov=lemma",
        "--cov-report=term-missing",
        "--cov-report=html:coverage_html",
        "tests/"
    ]
    
    # Run the tests
    result = pytest.main(args)
    
    # Print summary
    if result == 0:
        print("\n✅ All tests passed!")
        print("Coverage report generated in coverage_html/")
    else:
        print("\n❌ Some tests failed!")
    
    return result

if __name__ == "__main__":
    sys.exit(main())
