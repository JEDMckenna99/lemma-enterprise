#!/usr/bin/env python3
"""
Deployment Preparation Script for Lemma Enterprise

This script prepares the application for deployment by checking
dependencies, environment variables, and other configuration settings.
"""
import os
import sys
import json
import shutil
from pathlib import Path
import secrets
import string

# Required environment variables
REQUIRED_ENV_VARS = {
    "LEMMA_ADMIN_USER": os.environ.get("LEMMA_ADMIN_USER", "admin"),
    "LEMMA_ADMIN_PASS": os.environ.get("LEMMA_ADMIN_PASS", ""),
    "LEMMA_SECRET_KEY": os.environ.get("LEMMA_SECRET_KEY", ""),
    "LEMMA_API_KEY": os.environ.get("LEMMA_API_KEY", "")
}

# Optional environment variables with defaults
OPTIONAL_ENV_VARS = {
    "LEMMA_SESSION_TIMEOUT": os.environ.get("LEMMA_SESSION_TIMEOUT", "3600"),
    "LEMMA_RATE_LIMIT": os.environ.get("LEMMA_RATE_LIMIT", "100/hour")
}

def check_environment_variables():
    """Check if required environment variables are set."""
    print("Checking environment variables...")
    
    missing_vars = []
    for var_name, var_value in REQUIRED_ENV_VARS.items():
        if not var_value:
            missing_vars.append(var_name)
    
    if missing_vars:
        print("\n❌ Missing required environment variables:")
        for var_name in missing_vars:
            print(f"  - {var_name}")
        
        # Generate secure defaults
        secure_defaults = {}
        if "LEMMA_SECRET_KEY" in missing_vars:
            secure_defaults["LEMMA_SECRET_KEY"] = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
        
        if "LEMMA_API_KEY" in missing_vars:
            secure_defaults["LEMMA_API_KEY"] = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
        
        # Write to .env.production.template
        with open(".env.production.template", "w") as f:
            for var_name, var_value in REQUIRED_ENV_VARS.items():
                if var_name in secure_defaults:
                    f.write(f"{var_name}={secure_defaults[var_name]}\n")
                elif var_value:
                    f.write(f"{var_name}={var_value}\n")
                else:
                    f.write(f"{var_name}=CHANGE_ME\n")
            
            for var_name, var_value in OPTIONAL_ENV_VARS.items():
                f.write(f"{var_name}={var_value}\n")
        
        print("\n⚠️ Created .env.production.template with secure defaults.")
        print("Please update this file with your values before deployment.")
        return False
    
    print("✅ All required environment variables are set.")
    
    # Write deployment config
    deployment_config = {
        "required_vars": REQUIRED_ENV_VARS,
        "optional_vars": OPTIONAL_ENV_VARS
    }
    
    with open("deployment_config.json", "w") as f:
        json.dump(deployment_config, f, indent=2)
    
    print("✅ Deployment configuration written to deployment_config.json")
    return True

def check_dependencies():
    """Check if required dependencies are installed."""
    print("\nChecking dependencies...")
    
    try:
        with open("requirements.txt", "r") as f:
            requirements = f.read().splitlines()
        
        import pkg_resources
        
        missing_deps = []
        for req in requirements:
            if req and not req.startswith('#'):
                try:
                    pkg_resources.require(req)
                except (pkg_resources.DistributionNotFound, pkg_resources.VersionConflict):
                    missing_deps.append(req)
        
        if missing_deps:
            print(f"❌ Missing {len(missing_deps)} dependencies:")
            for dep in missing_deps[:5]:
                print(f"  - {dep}")
            
            if len(missing_deps) > 5:
                print(f"  - and {len(missing_deps) - 5} more...")
            
            print("\nRun: pip install -r requirements.txt")
            return False
        
        print("✅ All dependencies are installed.")
        return True
    except Exception as e:
        print(f"❌ Error checking dependencies: {e}")
        return False

def prepare_deployment_package():
    """Prepare the deployment package."""
    print("\nPreparing deployment package...")
    
    # List of files to exclude
    exclude_patterns = [
        "__pycache__",
        "*.pyc",
        ".git",
        ".env",
        ".vscode",
        ".DS_Store",
        "*.zip",
        "venv",
        "env",
        ".pytest_cache",
        "*.sqlite",
        "*.db",
        ".coverage",
        "htmlcov",
        "temp",
        "tmp"
    ]
    
    # List of test files to exclude
    test_files = [
        "test_*.py",
        "*_test.py"
    ]
    
    try:
        # Create output directory
        os.makedirs("deployment", exist_ok=True)
        
        # Create a list of all files
        all_files = []
        for root, dirs, files in os.walk("."):
            # Check if directory should be excluded
            if any(exclude in root for exclude in exclude_patterns):
                continue
            
            # Add non-excluded files
            for file in files:
                # Skip excluded patterns
                if any(file.endswith(exc.replace("*", "")) for exc in exclude_patterns if "*" in exc):
                    continue
                
                # Skip test files
                if any(file.startswith(test.replace("*", "")) or file.endswith(test.replace("*", "")) for test in test_files if "*" in test):
                    continue
                
                file_path = os.path.join(root, file)
                if file_path.startswith("./") or file_path.startswith(".\\"):
                    file_path = file_path[2:]
                
                all_files.append(file_path)
        
        print(f"✅ Found {len(all_files)} files to include in the package.")
        
        # Copy files to deployment directory
        for file_path in all_files:
            dest_path = os.path.join("deployment", file_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy2(file_path, dest_path)
        
        print("✅ Files copied to deployment directory.")
        
        # Create deployment zip
        shutil.make_archive("lemma-enterprise", "zip", "deployment")
        
        print("✅ Deployment package created: lemma-enterprise.zip")
        return True
    except Exception as e:
        print(f"❌ Error preparing deployment package: {e}")
        return False

def main():
    """Main function to prepare deployment."""
    print("=== LEMMA ENTERPRISE DEPLOYMENT PREPARATION ===\n")
    
    env_check = check_environment_variables()
    dep_check = check_dependencies()
    
    if not env_check or not dep_check:
        print("\n⚠️ Please fix the issues above before proceeding with deployment.")
        return False
    
    package_result = prepare_deployment_package()
    
    if not package_result:
        print("\n⚠️ Failed to create deployment package.")
        return False
    
    print("\n🎉 Deployment preparation complete!")
    print("\nNext steps:")
    print("1. Deploy the application using the generated lemma-enterprise.zip package")
    print("2. Set the environment variables on your hosting platform")
    print("3. Verify that the application is running correctly")
    
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
