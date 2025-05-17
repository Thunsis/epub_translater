#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script to download NLTK data required for the EPUB translator.
Run this script before using the translator to avoid download issues during processing.
"""

import os
import sys
import nltk
import ssl
import time

def download_nltk_data():
    """Download required NLTK data with robust error handling."""
    print("Downloading NLTK punkt tokenizer data...")
    
    # Disable SSL verification to avoid download issues
    try:
        _create_unverified_https_context = ssl._create_unverified_context
        ssl._create_default_https_context = _create_unverified_https_context
        print("SSL verification disabled for NLTK download")
    except AttributeError:
        print("Unable to disable SSL verification, continuing with default SSL context")

    try:
        # Check if data already exists
        try:
            nltk.data.find('tokenizers/punkt')
            print("NLTK punkt tokenizer already downloaded")
            return True
        except LookupError:
            pass
        
        # Set download directory to ensure permissions
        nltk_data_dir = os.path.expanduser('~/nltk_data')
        os.makedirs(nltk_data_dir, exist_ok=True)
        
        # Download with timeout
        start_time = time.time()
        result = nltk.download('punkt', download_dir=nltk_data_dir, quiet=False, timeout=30)
        
        if result:
            print(f"Successfully downloaded NLTK punkt tokenizer in {time.time() - start_time:.2f} seconds")
            print(f"Data saved to: {nltk_data_dir}")
            return True
        else:
            print("Failed to download NLTK data")
            return False
            
    except Exception as e:
        print(f"Error downloading NLTK data: {str(e)}")
        print("\nTroubleshooting tips:")
        print("1. Check your internet connection")
        print("2. Ensure you have write permissions to ~/nltk_data")
        print("3. Try running with administrator/root privileges")
        print("4. If behind a proxy, set the HTTP_PROXY and HTTPS_PROXY environment variables")
        return False

if __name__ == "__main__":
    print("NLTK Downloader for EPUB Translator")
    print("===================================")
    success = download_nltk_data()
    
    if success:
        print("\nNLTK data download complete. You can now run the EPUB translator.")
        sys.exit(0)
    else:
        print("\nNLTK data download failed. Please resolve the issues and try again.")
        sys.exit(1)
