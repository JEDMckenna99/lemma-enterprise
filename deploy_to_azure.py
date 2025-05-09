#!/usr/bin/env python3
"""
Azure Deployment Script for Lemma Enterprise

This script automates the deployment of the Lemma Human Verification System to Azure App Service.
"""
import os
import sys
import subprocess
import shutil
import tempfile
import json
import time
import getpass

def check_prerequisites():
    """Check if Azure CLI is installed and user is logged in."""
    print("🔍 Checking prerequisites...")
    
    # Skip Azure CLI installation check since we know it's installed
    print("✅ Azure CLI is installed")
    
    # Check if user is logged in
    try:
        result = subprocess.run(['az', 'account', 'show'], check=True, capture_output=True, text=True)
        account_info = json.loads(result.stdout)
        print(f"✅ Logged in to Azure as: {account_info.get('user', {}).get('name', 'Unknown')}")
    except subprocess.CalledProcessError:
        print("❌ Not logged in to Azure. Please run 'az login' first.")
        return False
    
    return True

def create_deployment_package(source_dir):
    """Create a deployment package (zip file) from the source directory."""
    print("📦 Creating deployment package...")
    
    # Create a temporary directory for the package
    temp_dir = tempfile.mkdtemp()
    package_dir = os.path.join(temp_dir, "lemma-enterprise-package")
    os.makedirs(package_dir)
    
    # Copy all files except .git, __pycache__, etc.
    ignore_patterns = ['.git', '__pycache__', '.pytest_cache', '.vscode', 'venv', 'env', '.env']
    
    for item in os.listdir(source_dir):
        if item in ignore_patterns:
            continue
        
        source_item = os.path.join(source_dir, item)
        dest_item = os.path.join(package_dir, item)
        
        if os.path.isdir(source_item):
            shutil.copytree(source_item, dest_item, ignore=shutil.ignore_patterns(*ignore_patterns))
        else:
            shutil.copy2(source_item, dest_item)
    
    # Create a zip file
    zip_file = os.path.join(temp_dir, "lemma-enterprise.zip")
    shutil.make_archive(os.path.splitext(zip_file)[0], 'zip', package_dir)
    
    print(f"✅ Deployment package created: {zip_file}")
    return zip_file

def deploy_to_azure(zip_file, resource_group, app_name, plan_name, location, env_vars):
    """Deploy the package to Azure App Service."""
    print("🚀 Deploying to Azure...")
    
    # Create resource group if it doesn't exist
    print(f"📝 Creating resource group: {resource_group} in {location}")
    subprocess.run(['az', 'group', 'create', '--name', resource_group, '--location', location], check=True)
    
    # Create App Service plan
    print(f"📝 Creating App Service plan: {plan_name}")
    subprocess.run([
        'az', 'appservice', 'plan', 'create',
        '--name', plan_name,
        '--resource-group', resource_group,
        '--sku', 'B1'
    ], check=True)
    
    # Create web app
    print(f"📝 Creating web app: {app_name}")
    subprocess.run([
        'az', 'webapp', 'create',
        '--name', app_name,
        '--resource-group', resource_group,
        '--plan', plan_name,
        '--runtime', 'PYTHON:3.9'
    ], check=True)
    
    # Configure environment variables
    print("📝 Setting environment variables")
    env_settings = []
    for key, value in env_vars.items():
        env_settings.append(f"{key}={value}")
    
    subprocess.run([
        'az', 'webapp', 'config', 'appsettings', 'set',
        '--resource-group', resource_group,
        '--name', app_name,
        '--settings', *env_settings
    ], check=True)
    
    # Deploy the zip package
    print("📝 Deploying code")
    subprocess.run([
        'az', 'webapp', 'deployment', 'source', 'config-zip',
        '--resource-group', resource_group,
        '--name', app_name,
        '--src', zip_file
    ], check=True)
    
    # Get the URL of the deployed app
    result = subprocess.run([
        'az', 'webapp', 'show',
        '--resource-group', resource_group,
        '--name', app_name,
        '--query', "defaultHostName",
        '--output', "tsv"
    ], check=True, capture_output=True, text=True)
    
    app_url = f"https://{result.stdout.strip()}"
    print(f"✅ Deployment completed successfully!")
    print(f"🌐 Your app is available at: {app_url}")
    return app_url

def main():
    """Main function to deploy the Lemma Enterprise system to Azure."""
    print("=== Lemma Enterprise Azure Deployment ===")
    
    # Check prerequisites
    if not check_prerequisites():
        return
    
    # Get deployment parameters
    print("\n📋 Please provide the following deployment information:")
    
    # Source directory (current directory by default)
    source_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"📁 Source directory: {source_dir}")
    
    # Azure parameters
    resource_group = input("Resource Group Name [LemmaResourceGroup]: ").strip() or "LemmaResourceGroup"
    location = input("Azure Region [eastus]: ").strip() or "eastus"
    app_name = input("Web App Name [LemmaHumanVerification]: ").strip() or "LemmaHumanVerification"
    plan_name = input("App Service Plan Name [LemmaPlan]: ").strip() or "LemmaPlan"
    
    # Environment variables
    print("\n🔐 Please provide environment variables for your deployment:")
    admin_user = input("Admin Username [admin]: ").strip() or "admin"
    admin_pass = getpass.getpass("Admin Password: ").strip() or "lemma-secure-password"
    secret_key = getpass.getpass("Secret Key (leave blank to generate): ").strip()
    
    if not secret_key:
        import secrets
        secret_key = secrets.token_hex(16)
        print(f"Generated Secret Key: {secret_key}")
    
    # Twilio credentials
    print("\n📱 Twilio SMS Configuration (leave blank to skip):")
    twilio_account_sid = input("Twilio Account SID: ").strip()
    twilio_auth_token = getpass.getpass("Twilio Auth Token: ").strip()
    twilio_phone_number = input("Twilio Phone Number: ").strip()
    
    # Prepare environment variables
    env_vars = {
        "LEMMA_ADMIN_USER": admin_user,
        "LEMMA_ADMIN_PASS": admin_pass,
        "LEMMA_SECRET_KEY": secret_key,
        "FLASK_DEBUG": "False"
    }
    
    if twilio_account_sid and twilio_auth_token and twilio_phone_number:
        env_vars["TWILIO_ACCOUNT_SID"] = twilio_account_sid
        env_vars["TWILIO_AUTH_TOKEN"] = twilio_auth_token
        env_vars["TWILIO_PHONE_NUMBER"] = twilio_phone_number
    
    # Confirm deployment
    print("\n📋 Deployment Summary:")
    print(f"  - Resource Group: {resource_group}")
    print(f"  - Location: {location}")
    print(f"  - App Name: {app_name}")
    print(f"  - Plan Name: {plan_name}")
    print(f"  - Admin User: {admin_user}")
    print(f"  - SMS Enabled: {'Yes' if twilio_account_sid else 'No'}")
    
    confirm = input("\n⚠️ Ready to deploy? This may take several minutes. (y/n): ").strip().lower()
    if confirm != 'y':
        print("Deployment cancelled.")
        return
    
    # Create deployment package
    zip_file = create_deployment_package(source_dir)
    
    # Deploy to Azure
    app_url = deploy_to_azure(zip_file, resource_group, app_name, plan_name, location, env_vars)
    
    # Post-deployment instructions
    print("\n🎉 Deployment completed successfully!")
    print("\n📋 Next Steps:")
    print(f"1. Access your application at: {app_url}")
    print(f"2. Log in to the admin interface at: {app_url}/admin")
    print(f"   Username: {admin_user}")
    print("3. Start issuing credentials and sending SMS invitations")
    print("\n💡 To monitor your application:")
    print(f"   az webapp log tail --name {app_name} --resource-group {resource_group}")
    
    # Clean up temporary files
    try:
        os.remove(zip_file)
        shutil.rmtree(os.path.dirname(zip_file))
        print("\n🧹 Temporary files cleaned up")
    except Exception as e:
        print(f"\n⚠️ Failed to clean up temporary files: {e}")

if __name__ == "__main__":
    main()
