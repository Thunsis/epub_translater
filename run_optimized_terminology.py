#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Optimized runner for DeepSeek terminology extraction.
This script:
1. Uses the optimized terminology extractor that processes content in smaller chunks
2. Increases timeout values for API calls
3. Provides an option to disable SSL verification for problematic environments 
"""

import os
import sys
import argparse
import logging
import time
from pathlib import Path

# Import our modules
from epub_translator.config import Config
from epub_translator.translator import DeepseekTranslator
from epub_translator.term_extractor_optimized import OptimizedTerminologyExtractor

def setup_logging(log_level):
    """Set up logging configuration"""
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {log_level}")
    
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("epub_translator.log"),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("epub_translator")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Optimized DeepSeek terminology extraction")
    
    parser.add_argument(
        "input_file", 
        help="Path to the input EPUB file or workdir"
    )
    
    parser.add_argument(
        "-k", "--api-key", 
        help="Deepseek API key (overrides config file)",
        default=None
    )
    
    parser.add_argument(
        "-c", "--config", 
        help="Path to configuration file",
        default="config.ini"
    )
    
    parser.add_argument(
        "--timeout", 
        help="API timeout in seconds (default: 60)",
        type=int, 
        default=60
    )
    
    parser.add_argument(
        "--chunk-size", 
        help="Maximum size of text chunks to send to API (default: 3000)",
        type=int, 
        default=3000
    )
    
    parser.add_argument(
        "--max-retries", 
        help="Maximum number of API retries (default: 3)",
        type=int, 
        default=3
    )
    
    parser.add_argument(
        "--no-verify-ssl",
        help="Disable SSL certificate verification for API calls",
        action="store_true",
        default=False
    )
    
    parser.add_argument(
        "--log-level", 
        help="Logging level (default: info)",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info"
    )
    
    parser.add_argument(
        "--update-config",
        help="Update config.ini with successful settings",
        action="store_true"
    )
    
    return parser.parse_args()

def update_config(config_file, timeout, max_retries):
    """Update config file with new settings"""
    config = Config(config_file)
    config.set('deepseek', 'timeout', str(timeout))
    config.set('deepseek', 'max_retries', str(max_retries))
    config.save()
    print(f"Updated {config_file} with new timeout={timeout} and max_retries={max_retries}")

def main():
    """Main function to run optimized terminology extraction"""
    args = parse_arguments()
    logger = setup_logging(args.log_level)
    
    print("\n==== Optimized DeepSeek Terminology Extraction ====")
    print("This script breaks large requests into smaller chunks to avoid timeouts")
    
    # Determine if input is an EPUB file or a workdir
    input_path = args.input_file
    is_workdir = os.path.isdir(input_path)
    
    if is_workdir:
        workdir = input_path
        logger.info(f"Using existing workdir: {workdir}")
    else:
        # If it's an EPUB file, use the standard naming convention for workdir
        if not input_path.endswith('.epub'):
            logger.warning(f"Input file does not have .epub extension: {input_path}")
            
        workdir = os.path.splitext(os.path.basename(input_path))[0] + "_workdir"
        
        # Check if workdir exists
        if not os.path.exists(workdir):
            logger.error(f"Working directory not found: {workdir}")
            print(f"ERROR: Working directory not found: {workdir}")
            print("Please run Phase 1 (preparation) first with:")
            print(f"python main.py {input_path} --phase prepare")
            sys.exit(1)
            
        logger.info(f"Using workdir from EPUB file: {workdir}")
        
    # Load configuration
    try:
        config = Config(args.config)
        if args.api_key:
            config.set('deepseek', 'api_key', args.api_key)
            
        # Get API key
        api_key = config.get('deepseek', 'api_key')
        if not api_key:
            logger.error("No DeepSeek API key provided")
            print("ERROR: No DeepSeek API key provided")
            print("Please provide your API key using --api-key or add it to your config.ini file")
            sys.exit(1)
            
        # Set up the translator with optimized settings
        translator = DeepseekTranslator(
            api_key=api_key,
            source_lang="auto",  # Auto-detect is fine for terminology
            target_lang="zh-CN", # Not used for terminology extraction
            model=config.get('deepseek', 'model'),
            max_retries=args.max_retries,
            timeout=args.timeout,
            rate_limit=config.getint('deepseek', 'rate_limit'),
            verify_ssl=not args.no_verify_ssl
        )
        logger.info(f"Initialized DeepSeek translator with timeout={args.timeout}s, max_retries={args.max_retries}")
        
        # Set up the optimized terminology extractor
        term_extractor = OptimizedTerminologyExtractor(
            translator=translator,
            workdir=workdir,
            use_deepseek=True,
            max_chunk_size=args.chunk_size
        )
        
        # First, ensure the translator API is enabled
        translator.enable_api()
        
        # Run terminology extraction
        print(f"Starting optimized terminology extraction with chunk size {args.chunk_size} characters...")
        print(f"API timeout: {args.timeout}s, Max retries: {args.max_retries}")
        if args.no_verify_ssl:
            print("SSL verification: Disabled")
        
        start_time = time.time()
        try:
            # Extract terminology
            terminology = term_extractor.generate_terminology_with_deepseek()
            
            # Check results
            if terminology:
                elapsed = time.time() - start_time
                preserved_terms = [term for term, info in terminology.items() 
                                if info.get('preserve', False)]
                
                print(f"\n✅ Success! Extracted {len(preserved_terms)} terms in {elapsed:.2f} seconds")
                print(f"Terms saved to {os.path.join(workdir, 'terminology', 'final_terminology.csv')}")
                
                # Update config if requested
                if args.update_config:
                    update_config(args.config, args.timeout, args.max_retries)
                    
                # Next steps
                print("\nNext steps:")
                print(f"1. Check terminology in {os.path.join(workdir, 'terminology')}")
                print(f"2. Run the translation phase with:")
                print(f"   python main.py {input_path} --phase translate")
                
                return 0
            else:
                elapsed = time.time() - start_time
                logger.error(f"No terminology generated after {elapsed:.2f} seconds")
                print(f"\n❌ Error: No terminology was generated after {elapsed:.2f} seconds")
                return 1
                
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Error during terminology extraction: {e}")
            print(f"\n❌ Error during terminology extraction after {elapsed:.2f} seconds: {e}")
            
            # Provide troubleshooting advice
            print("\nTroubleshooting steps:")
            print("1. Try running the connection test script:")
            print("   python fix_deepseek_api.py --timeout 60 --no-verify-ssl")
            print("2. Check your DeepSeek API key and credits")
            print("3. Try with a longer timeout: --timeout 120")
            print("4. Try with smaller chunks: --chunk-size 1500")
            
            return 1
            
    except Exception as e:
        logger.error(f"Error during setup: {e}")
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
