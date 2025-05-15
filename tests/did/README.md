# DID Testing for Lemma

This directory contains test scripts for verifying the DID (Decentralized Identifier) functionality in the Lemma human verification system.

## Test Scripts

- **test_heroku_deployment.py**: Tests the basic API functionality of your Heroku deployment
- **heroku_did_resolution_test.py**: Tests DID resolution capabilities
- **test_did_functionality.py**: Comprehensive tests for all DID-related functionality
- **browser_storage_test.py**: Tests credential storage in the browser using Selenium
- **run_did_tests.py**: Main runner script that can execute all tests

## Running Tests

The easiest way to run all tests is to use the runner script with your Heroku URL:

```bash
python run_did_tests.py --url https://your-lemma-app.herokuapp.com
```

### Options

- `--url`: (Required) The URL of your Heroku deployment
- `--did`: (Optional) A specific DID to test with
- `--user`: (Optional) A specific user ID to test with
- `--visible`: (Optional) Run browser tests in visible mode
- `--skip-browser`: (Optional) Skip browser storage tests
- `--tests`: (Optional) Specific tests to run, choices are "deployment", "resolution", "functionality", "browser"

### Examples

Run only deployment and resolution tests:
```bash
python run_did_tests.py --url https://your-lemma-app.herokuapp.com --tests deployment resolution
```

Test with a specific DID:
```bash
python run_did_tests.py --url https://your-lemma-app.herokuapp.com --did did:lemma:test123
```

Run browser tests in visible mode with a specific user:
```bash
python run_did_tests.py --url https://your-lemma-app.herokuapp.com --visible --user test-user-123
```

## Requirements

- Python 3.9+
- requests
- selenium (for browser tests)
- webdriver-manager (for browser tests)

## Output

The tests will output detailed information about each step of the process, with clear indicators for successes (✅) and failures (❌). At the end, you'll get a summary of all test results. 