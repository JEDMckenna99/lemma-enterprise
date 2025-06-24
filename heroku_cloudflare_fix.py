#!/usr/bin/env python3
"""
Heroku CloudFlare Security Fix
==============================
This script runs from Heroku to fix CloudFlare 403 errors by adjusting security settings.
Uses environment variables from Heroku config.
"""

import os
import sys
import requests
import json
from datetime import datetime

def log(message, level="INFO"):
    """Log with timestamp and level"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    symbols = {
        "INFO": "🔧",
        "SUCCESS": "✅", 
        "ERROR": "❌",
        "WARNING": "⚠️"
    }
    symbol = symbols.get(level, "📝")
    print(f"[{timestamp}] {symbol} {message}")

def main():
    log("Lemma CloudFlare Security Fix", "INFO")
    log("=" * 50, "INFO")
    
    # Configuration
    ZONE_ID = "c4e8c3580c49fa6351a5d6c02bc79b4d"
    
    # Get environment variables - support both token and key methods
    cf_email = os.getenv('CLOUDFLARE_EMAIL')
    cf_api_token = os.getenv('CLOUDFLARE_API_TOKEN')
    cf_api_key = os.getenv('CLOUDFLARE_API_KEY')
    
    # Determine authentication method
    if cf_api_token:
        auth_method = "token"
        log("Using Custom API Token authentication", "INFO")
    elif cf_email and cf_api_key:
        auth_method = "key"
        log("Using Global API Key authentication", "INFO")
    else:
        log("No valid authentication found", "ERROR")
        if not cf_api_token:
            log("CLOUDFLARE_API_TOKEN not set", "ERROR")
            log("Run: heroku config:set CLOUDFLARE_API_TOKEN=your-custom-token --app lemma-enterprise", "INFO")
        if not cf_email or not cf_api_key:
            log("CLOUDFLARE_EMAIL or CLOUDFLARE_API_KEY not set", "ERROR")
            log("Alternative: heroku config:set CLOUDFLARE_API_KEY=your-global-key --app lemma-enterprise", "INFO")
        sys.exit(1)
    
    log(f"Zone ID: {ZONE_ID}", "INFO")
    if auth_method == "key":
        log(f"Email: {cf_email}", "INFO")
    log("", "INFO")
    
    # API endpoint
    api_url = f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/settings/security_level"
    
    # Headers based on authentication method
    if auth_method == "token":
        headers = {
            "Authorization": f"Bearer {cf_api_token}",
            "Content-Type": "application/json"
        }
    else:  # key method
        headers = {
            "X-Auth-Email": cf_email,
            "X-Auth-Key": cf_api_key,
            "Content-Type": "application/json"
        }
    
    # Request body
    data = {"value": "medium"}
    
    log("Making API call to update security level...", "INFO")
    
    try:
        # Make the API call
        response = requests.patch(api_url, headers=headers, json=data, timeout=30)
        
        log("API Response:", "INFO")
        try:
            response_data = response.json()
            print(json.dumps(response_data, indent=2))
        except json.JSONDecodeError:
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
        
        print()
        
        if response.status_code == 200:
            try:
                response_data = response.json()
                if response_data.get('success'):
                    log("CloudFlare security level updated to MEDIUM", "SUCCESS")
                    log("Your lemma.id site should now work properly!", "SUCCESS")
                    log("", "INFO")
                    log("Test your site:", "INFO")
                    log("  curl -I https://lemma.id/api/health", "INFO")
                    log("", "INFO")
                    
                    # Test the API immediately
                    log("Testing API health...", "INFO")
                    try:
                        test_response = requests.get("https://lemma.id/api/health", timeout=10)
                        if test_response.status_code == 200:
                            log(f"API is working! Status: {test_response.status_code}", "SUCCESS")
                            try:
                                health_data = test_response.json()
                                log(f"Service: {health_data.get('service', 'unknown')}", "SUCCESS")
                            except:
                                pass
                        else:
                            log(f"API returned status {test_response.status_code}", "WARNING")
                            log("May need a few minutes to propagate", "WARNING")
                    except requests.RequestException as e:
                        log(f"API test failed: {e}", "WARNING")
                        log("CloudFlare changes may need time to propagate", "WARNING")
                    
                else:
                    log("Could not update CloudFlare settings", "ERROR")
                    if 'errors' in response_data:
                        for error in response_data['errors']:
                            log(f"Error: {error.get('message', 'Unknown error')}", "ERROR")
                    sys.exit(1)
            except json.JSONDecodeError:
                log("Invalid JSON response from CloudFlare API", "ERROR")
                sys.exit(1)
        else:
            log(f"API call failed with status {response.status_code}", "ERROR")
            log(f"Response: {response.text}", "ERROR")
            if response.status_code == 403:
                log("This might be a token permissions issue", "WARNING")
                log("Make sure your token has 'Zone Settings:Edit' permission", "WARNING")
            sys.exit(1)
            
    except requests.RequestException as e:
        log(f"Request failed: {e}", "ERROR")
        sys.exit(1)
    
    log("CloudFlare security fix completed!", "SUCCESS")

if __name__ == "__main__":
    main() 