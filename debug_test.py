"""
Debug script for running tests with detailed error output.
"""
import sys
import pytest

if __name__ == "__main__":
    # Run the test with detailed error output
    sys.exit(pytest.main([
        "tests/test_routes.py::test_presentation_verification", 
        "-v", 
        "--no-header",
        "--showlocals",  # Show local variables in tracebacks
        "-s",  # Don't capture stdout/stderr
    ]))
