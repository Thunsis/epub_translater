#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Utility script to diagnose and fix DeepSeek API connection issues.
This script:
1. Tests connectivity to the DeepSeek API
2. Tries with different timeout settings
3. Tries with SSL verification disabled
"""

import os
import sys
import json
import time
import argparse
import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

def test_deepseek_connection(api_key, timeout=30, verify_ssl=True, max_retries=3):
    """Test connection to DeepSeek API with various settings."""
    
    endpoint = "https://api.deepseek.com/v1/chat/completions"
    
    # Create a session with retry capability
    session = requests.Session()
    
    # Configure retries with backoff
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Simple test message - much smaller than a full book structure
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, are you working?"}
        ],
        "temperature": 0.3,
        "max_tokens": 100  # Very small response requested
    }
    
    print(f"\nTesting DeepSeek API connection:")
    print(f"  - Timeout: {timeout} seconds")
    print(f"  - SSL Verification: {'Enabled' if verify_ssl else 'Disabled'}")
    print(f"  - Max Retries: {max_retries}")
    
    start_time = time.time()
    try:
        response = session.post(
            endpoint,
            headers=headers,
            data=json.dumps(data),
            timeout=timeout,
            verify=verify_ssl
        )
        response.raise_for_status()
        
        # Get response
        result = response.json()
        elapsed = time.time() - start_time
        
        print(f"✅ SUCCESS: API responded in {elapsed:.2f} seconds")
        print(f"Response content: {result['choices'][0]['message']['content']}")
        return True
        
    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        print(f"❌ ERROR: Request timed out after {elapsed:.2f} seconds")
        return False
        
    except requests.exceptions.SSLError as e:
        print(f"❌ ERROR: SSL Certificate verification failed: {str(e)}")
        print("   Try running with --no-verify-ssl option")
        return False
        
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: Request failed: {str(e)}")
        return False

def get_api_key():
    """Get API key from config.ini or environment variable."""
    # First try environment variable
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if api_key:
        return api_key
    
    # Then try config.ini
    try:
        import configparser
        config = configparser.ConfigParser()
        if os.path.exists('config.ini'):
            config.read('config.ini')
            if 'deepseek' in config and 'api_key' in config['deepseek']:
                api_key = config['deepseek']['api_key']
                if api_key and api_key != 'YOUR_DEEPSEEK_API_KEY_HERE':
                    return api_key
    except Exception:
        pass
    
    return None

def update_config(timeout=None, max_retries=None, verify_ssl=None):
    """Update config.ini with new settings."""
    import configparser
    config = configparser.ConfigParser()
    
    if os.path.exists('config.ini'):
        config.read('config.ini')
    
    if 'deepseek' not in config:
        config.add_section('deepseek')
    
    # Only update the specified settings
    if timeout is not None:
        config.set('deepseek', 'timeout', str(timeout))
    
    if max_retries is not None:
        config.set('deepseek', 'max_retries', str(max_retries))
        
    # Other settings remain unchanged
    
    with open('config.ini', 'w') as f:
        config.write(f)
    
    print(f"Updated config.ini with new settings")

def main():
    parser = argparse.ArgumentParser(description="Test and fix DeepSeek API connection issues")
    
    parser.add_argument(
        "-k", "--api-key",
        help="DeepSeek API key (overrides config file and environment variable)",
        default=None
    )
    
    parser.add_argument(
        "--timeout",
        help="Connection timeout in seconds (default: 60)",
        type=int,
        default=60
    )
    
    parser.add_argument(
        "--no-verify-ssl",
        help="Disable SSL certificate verification",
        action="store_true"
    )
    
    parser.add_argument(
        "--max-retries",
        help="Maximum number of retries (default: 3)",
        type=int,
        default=3
    )
    
    parser.add_argument(
        "--update-config",
        help="Update config.ini with new settings if test is successful",
        action="store_true"
    )
    
    args = parser.parse_args()
    
    # Get API key from args, env var, or config
    api_key = args.api_key or get_api_key()
    
    if not api_key:
        print("❌ ERROR: No DeepSeek API key provided")
        print("Please provide your API key using one of these methods:")
        print("  1. Pass it with -k or --api-key")
        print("  2. Set it in the DEEPSEEK_API_KEY environment variable")
        print("  3. Update it in your config.ini file")
        sys.exit(1)
    
    # Test the connection
    success = test_deepseek_connection(
        api_key=api_key,
        timeout=args.timeout,
        verify_ssl=not args.no_verify_ssl,
        max_retries=args.max_retries
    )
    
    if success and args.update_config:
        update_config(
            timeout=args.timeout,
            max_retries=args.max_retries
        )
        
        print("\n✅ Connection test passed. You can now try running your translation with:")
        if args.no_verify_ssl:
            print(f"python main.py input.epub --phase terminology --no-verify-ssl")
        else:
            print(f"python main.py input.epub --phase terminology")
    
    if not success:
        print("\n❌ Connection test failed. Try these solutions:")
        print("1. Check your internet connection and try again")
        print("2. Try with a longer timeout: --timeout 120")
        print("3. Try disabling SSL verification: --no-verify-ssl")
        print("4. Ensure your DeepSeek API key is valid and has sufficient credits")
        sys.exit(1)

if __name__ == "__main__":
    main()
