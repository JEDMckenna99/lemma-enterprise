#!/usr/bin/env python3
"""
Comprehensive test runner for Lemma Human Verification System.
Provides detailed test reporting, coverage analysis, and security test validation.
"""
import sys
import os
import subprocess
import logging
from typing import List, Dict, Any, Optional


def setup_logging() -> logging.Logger:
    """Set up logging for the test runner."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('test_runner.log')
        ]
    )
    return logging.getLogger(__name__)


def run_command(command: List[str], logger: logging.Logger) -> tuple[int, str, str]:
    """
    Run a command and return the result.
    
    Args:
        command: Command to run as a list of strings
        logger: Logger instance
        
    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    logger.info(f"Running command: {' '.join(command)}")
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error("Command timed out after 5 minutes")
        return 1, "", "Command timed out"
    except Exception as e:
        logger.error(f"Error running command: {e}")
        return 1, "", str(e)


def check_test_dependencies(logger: logging.Logger) -> bool:
    """
    Check that all required test dependencies are available.
    
    Args:
        logger: Logger instance
        
    Returns:
        True if all dependencies are available
    """
    logger.info("Checking test dependencies...")
    
    required_packages = [
        'pytest',
        'pytest-cov',
        'flask',
        'cryptography',
        'flask-wtf'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        logger.error(f"Missing required test dependencies: {missing_packages}")
        logger.error("Install them with: pip install " + " ".join(missing_packages))
        return False
    
    logger.info("All test dependencies are available")
    return True


def run_security_tests(logger: logging.Logger) -> Dict[str, Any]:
    """
    Run security-specific tests.
    
    Args:
        logger: Logger instance
        
    Returns:
        Dict containing security test results
    """
    logger.info("Running security tests...")
    
    security_tests = [
        'tests/test_security.py::TestCSRFProtection',
        'tests/test_security.py::TestAuthentication',
        'tests/test_security.py::TestAPIKeyAuthorization',
        'tests/test_security.py::TestRateLimiting',
        'tests/test_security.py::TestInputSanitization',
        'tests/test_security.py::TestSessionSecurity'
    ]
    
    results = {
        'total_tests': 0,
        'passed': 0,
        'failed': 0,
        'failures': []
    }
    
    for test in security_tests:
        logger.info(f"Running {test}")
        returncode, stdout, stderr = run_command([
            'python', '-m', 'pytest', test, '-v', '--tb=short'
        ], logger)
        
        if returncode == 0:
            results['passed'] += 1
        else:
            results['failed'] += 1
            results['failures'].append({
                'test': test,
                'stdout': stdout,
                'stderr': stderr
            })
        
        results['total_tests'] += 1
    
    logger.info(f"Security tests completed: {results['passed']}/{results['total_tests']} passed")
    return results


def run_input_validation_tests(logger: logging.Logger) -> Dict[str, Any]:
    """
    Run input validation tests.
    
    Args:
        logger: Logger instance
        
    Returns:
        Dict containing input validation test results
    """
    logger.info("Running input validation tests...")
    
    returncode, stdout, stderr = run_command([
        'python', '-m', 'pytest', 'tests/test_input_validation.py', '-v', '--tb=short'
    ], logger)
    
    results = {
        'returncode': returncode,
        'stdout': stdout,
        'stderr': stderr,
        'passed': returncode == 0
    }
    
    logger.info(f"Input validation tests completed: {'PASSED' if results['passed'] else 'FAILED'}")
    return results


def run_dependency_tests(logger: logging.Logger) -> Dict[str, Any]:
    """
    Run dependency tests.
    
    Args:
        logger: Logger instance
        
    Returns:
        Dict containing dependency test results
    """
    logger.info("Running dependency tests...")
    
    returncode, stdout, stderr = run_command([
        'python', '-m', 'pytest', 'tests/test_dependencies.py', '-v', '--tb=short'
    ], logger)
    
    results = {
        'returncode': returncode,
        'stdout': stdout,
        'stderr': stderr,
        'passed': returncode == 0
    }
    
    logger.info(f"Dependency tests completed: {'PASSED' if results['passed'] else 'FAILED'}")
    return results


def run_all_tests_with_coverage(logger: logging.Logger) -> Dict[str, Any]:
    """
    Run all tests with coverage analysis.
    
    Args:
        logger: Logger instance
        
    Returns:
        Dict containing test results and coverage information
    """
    logger.info("Running all tests with coverage analysis...")
    
    returncode, stdout, stderr = run_command([
        'python', '-m', 'pytest', 
        'tests/',
        '--cov=lemma',
        '--cov-report=html:coverage_html',
        '--cov-report=term-missing',
        '--cov-fail-under=70',  # Require at least 70% coverage
        '-v'
    ], logger)
    
    results = {
        'returncode': returncode,
        'stdout': stdout,
        'stderr': stderr,
        'passed': returncode == 0,
        'coverage_html': 'coverage_html/index.html'
    }
    
    # Extract coverage percentage from output
    coverage_percentage = None
    for line in stdout.split('\n'):
        if 'TOTAL' in line and '%' in line:
            try:
                coverage_percentage = line.split()[-1].rstrip('%')
                results['coverage_percentage'] = float(coverage_percentage)
            except (ValueError, IndexError):
                pass
    
    logger.info(f"All tests completed: {'PASSED' if results['passed'] else 'FAILED'}")
    if coverage_percentage:
        logger.info(f"Code coverage: {coverage_percentage}%")
    
    return results


def run_linting_checks(logger: logging.Logger) -> Dict[str, Any]:
    """
    Run code linting checks.
    
    Args:
        logger: Logger instance
        
    Returns:
        Dict containing linting results
    """
    logger.info("Running linting checks...")
    
    # Try to run flake8 if available
    flake8_results = {'available': False}
    try:
        returncode, stdout, stderr = run_command([
            'python', '-m', 'flake8', 'lemma/', '--max-line-length=120', '--ignore=E501,W503'
        ], logger)
        flake8_results = {
            'available': True,
            'returncode': returncode,
            'stdout': stdout,
            'stderr': stderr,
            'passed': returncode == 0
        }
    except Exception:
        logger.warning("flake8 not available, skipping linting checks")
    
    # Try to run mypy if available for type checking
    mypy_results = {'available': False}
    try:
        returncode, stdout, stderr = run_command([
            'python', '-m', 'mypy', 'lemma/', '--ignore-missing-imports'
        ], logger)
        mypy_results = {
            'available': True,
            'returncode': returncode,
            'stdout': stdout,
            'stderr': stderr,
            'passed': returncode == 0
        }
    except Exception:
        logger.warning("mypy not available, skipping type checking")
    
    return {
        'flake8': flake8_results,
        'mypy': mypy_results
    }


def generate_test_report(results: Dict[str, Any], logger: logging.Logger) -> None:
    """
    Generate a comprehensive test report.
    
    Args:
        results: Test results from all test runs
        logger: Logger instance
    """
    logger.info("Generating test report...")
    
    report_content = []
    report_content.append("=" * 80)
    report_content.append("LEMMA HUMAN VERIFICATION SYSTEM - TEST REPORT")
    report_content.append("=" * 80)
    report_content.append("")
    
    # Overall summary
    all_passed = True
    
    # Security tests
    security = results.get('security', {})
    security_passed = security.get('failed', 1) == 0
    all_passed = all_passed and security_passed
    
    report_content.append(f"Security Tests: {'PASSED' if security_passed else 'FAILED'}")
    if security:
        report_content.append(f"  - {security.get('passed', 0)}/{security.get('total_tests', 0)} tests passed")
    
    # Input validation tests
    input_validation = results.get('input_validation', {})
    input_validation_passed = input_validation.get('passed', False)
    all_passed = all_passed and input_validation_passed
    
    report_content.append(f"Input Validation Tests: {'PASSED' if input_validation_passed else 'FAILED'}")
    
    # Dependency tests
    dependency = results.get('dependency', {})
    dependency_passed = dependency.get('passed', False)
    all_passed = all_passed and dependency_passed
    
    report_content.append(f"Dependency Tests: {'PASSED' if dependency_passed else 'FAILED'}")
    
    # Overall coverage
    all_tests = results.get('all_tests', {})
    all_tests_passed = all_tests.get('passed', False)
    all_passed = all_passed and all_tests_passed
    
    report_content.append(f"All Tests with Coverage: {'PASSED' if all_tests_passed else 'FAILED'}")
    if 'coverage_percentage' in all_tests:
        report_content.append(f"  - Code Coverage: {all_tests['coverage_percentage']}%")
    
    # Linting results
    linting = results.get('linting', {})
    flake8_passed = linting.get('flake8', {}).get('passed', True)  # Default to True if not available
    mypy_passed = linting.get('mypy', {}).get('passed', True)  # Default to True if not available
    
    if linting.get('flake8', {}).get('available', False):
        report_content.append(f"Flake8 Linting: {'PASSED' if flake8_passed else 'FAILED'}")
        all_passed = all_passed and flake8_passed
    
    if linting.get('mypy', {}).get('available', False):
        report_content.append(f"MyPy Type Checking: {'PASSED' if mypy_passed else 'FAILED'}")
        all_passed = all_passed and mypy_passed
    
    report_content.append("")
    report_content.append(f"OVERALL RESULT: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    report_content.append("=" * 80)
    
    # Write report to file
    with open('test_report.txt', 'w') as f:
        f.write('\n'.join(report_content))
    
    # Print to console
    for line in report_content:
        print(line)
    
    logger.info("Test report generated: test_report.txt")


def main() -> int:
    """
    Main test runner function.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    logger = setup_logging()
    logger.info("Starting Lemma Human Verification System test suite")
    
    # Check dependencies first
    if not check_test_dependencies(logger):
        return 1
    
    results = {}
    
    try:
        # Run security tests
        results['security'] = run_security_tests(logger)
        
        # Run input validation tests
        results['input_validation'] = run_input_validation_tests(logger)
        
        # Run dependency tests
        results['dependency'] = run_dependency_tests(logger)
        
        # Run all tests with coverage
        results['all_tests'] = run_all_tests_with_coverage(logger)
        
        # Run linting checks
        results['linting'] = run_linting_checks(logger)
        
        # Generate comprehensive report
        generate_test_report(results, logger)
        
        # Determine overall success
        overall_success = (
            results['security'].get('failed', 1) == 0 and
            results['input_validation'].get('passed', False) and
            results['dependency'].get('passed', False) and
            results['all_tests'].get('passed', False)
        )
        
        if overall_success:
            logger.info("All tests passed successfully!")
            return 0
        else:
            logger.error("Some tests failed. Check test_report.txt for details.")
            return 1
            
    except Exception as e:
        logger.error(f"Test runner encountered an error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main()) 