#!/usr/bin/env python3
"""
Production readiness test runner for Lemma Enterprise.

This script runs all the production readiness tests and generates a report
on whether the system is ready for production deployment.

Usage:
    python run_prod_tests.py [--report-file REPORT_FILE]
"""

import os
import sys
import json
import time
import argparse
import pytest
from datetime import datetime
from typing import Dict, Any, List

# Ensure proper path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run production readiness tests for Lemma Enterprise"
    )
    parser.add_argument(
        "--report-file",
        default="prod_test_report.json",
        help="File to write the test report to",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--flow",
        help="Run only a specific flow test (1-13)",
    )
    return parser.parse_args()


def run_tests(args) -> Dict[str, Any]:
    """Run all production readiness tests."""
    start_time = time.time()
    
    # Prepare pytest arguments
    pytest_args = ['-xvs', 'prod_tests/flows']
    
    # Run only a specific flow if requested
    if args.flow:
        flow_num = args.flow
        pytest_args = ['-xvs', f'prod_tests/flows/test_flow_{flow_num}.py']
    
    # Run the tests
    result = pytest.main(pytest_args)
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    # Determine overall status
    status = "PASS" if result == 0 else "FAIL"
    
    # Create the report
    report = {
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "total_time_seconds": elapsed_time,
        "command": " ".join(pytest_args),
    }
    
    return report


def write_report(report: Dict[str, Any], report_file: str):
    """Write the test report to a file."""
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\nProduction readiness test report written to {report_file}")
    print(f"Overall status: {report['status']}")
    print(f"Total time: {report['total_time_seconds']:.2f} seconds")


def main():
    """Run the production readiness tests."""
    args = parse_args()
    
    print("=====================================================")
    print("Lemma Enterprise Production Readiness Test Runner")
    print("=====================================================")
    print(f"Starting tests at {datetime.now().isoformat()}")
    
    # Set up environment
    os.environ["LEMMA_TESTING"] = "1"
    
    # Run the tests
    report = run_tests(args)
    
    # Write the report
    write_report(report, args.report_file)
    
    # Exit with the appropriate code
    sys.exit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main() 