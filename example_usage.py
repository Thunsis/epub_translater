#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Example showing how to use the EPUB Translator programmatically.
This demonstrates programmatic use of the library instead of via command line.
"""

import os
import sys
import logging

# Add parent directory to path to allow importing the package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from epub_translator.config import Config
from epub_translator.epub_processor import EPUBProcessor
from epub_translator.translator import DeepseekTranslator
from epub_translator.term_extractor import TerminologyExtractor

def setup_logging():
    """Set up logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("epub_translator_example")

def translate_epub(input_path, output_path, api_key, source_lang="auto", target_lang="zh-CN"):
    """Translate an EPUB file programmatically.
    
    Args:
        input_path: Path to input EPUB file
        output_path: Path to save translated EPUB file
        api_key: Deepseek API key
        source_lang: Source language (default: auto)
        target_lang: Target language (default: zh-CN)
    """
    logger = setup_logging()
    
    # Validate input file
    if not os.path.exists(input_path):
        logger.error(f"Input file does not exist: {input_path}")
        return False
    
    try:
        # Initialize components
        translator = DeepseekTranslator(
            api_key=api_key,
            source_lang=source_lang,
            target_lang=target_lang
        )
        
        # Initialize terminology extractor with custom terminology file (if exists)
        term_extractor = TerminologyExtractor(
            min_frequency=3,
            custom_terminology_file="sample_terminology.csv" if os.path.exists("sample_terminology.csv") else None
        )
        
        # Initialize EPUB processor
        epub_processor = EPUBProcessor(
            translator=translator,
            term_extractor=term_extractor,
            batch_size=10,
            auto_extract_terms=True
        )
        
        # Process the EPUB file
        logger.info(f"Starting translation of {input_path}")
        stats = epub_processor.translate_epub(input_path, output_path)
        logger.info(f"Translation completed. Output saved to {output_path}")
        
        # Print statistics
        logger.info(f"Total characters: {stats['total_chars']}")
        logger.info(f"Total segments: {stats['total_segments']}")
        logger.info(f"Translated characters: {stats['translated_chars']}")
        logger.info(f"Translated segments: {stats['translated_segments']}")
        
        # Optionally save extracted terminology
        if hasattr(term_extractor, 'terminology') and term_extractor.terminology:
            term_output = os.path.splitext(output_path)[0] + "_terms.csv"
            term_extractor.save_terminology(term_output)
            logger.info(f"Extracted terminology saved to {term_output}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error during translation: {str(e)}", exc_info=True)
        return False

def main():
    """Example usage"""
    # Update these values
    input_epub = "path/to/your/book.epub"
    output_epub = "path/to/your/translated_book.epub"
    api_key = "YOUR_DEEPSEEK_API_KEY"  # Replace with your actual API key
    
    # Check if API key is provided
    if api_key == "YOUR_DEEPSEEK_API_KEY":
        print("Please update the script with your actual Deepseek API key")
        print("Or you can set the API_KEY environment variable:")
        print("  export DEEPSEEK_API_KEY='your_api_key'")
        
        # Try to get API key from environment variable
        import os
        env_api_key = os.environ.get('DEEPSEEK_API_KEY')
        if env_api_key:
            api_key = env_api_key
            print(f"Using API key from environment variable")
        else:
            print("No API key found. Exiting.")
            return
    
    # Validate input file existence
    if not os.path.exists(input_epub):
        print(f"Input file doesn't exist: {input_epub}")
        print("Please update the script with a valid input EPUB file path")
        return
    
    # Translate the EPUB file
    success = translate_epub(
        input_path=input_epub,
        output_path=output_epub,
        api_key=api_key,
        source_lang="en",  # Source language (or "auto" for automatic detection)
        target_lang="zh-CN"  # Target language
    )
    
    if success:
        print(f"\nTranslation completed successfully!")
        print(f"Translated EPUB saved to: {output_epub}")
    else:
        print(f"\nTranslation failed. See the error logs above for details.")

if __name__ == "__main__":
    print("EPUB Translator Example Usage")
    print("=============================")
    print("This example demonstrates how to use the EPUB Translator programmatically.")
    print("To run this example, edit the script to set your EPUB file path and API key,")
    print("or set the DEEPSEEK_API_KEY environment variable.\n")
    
    # Uncomment to run the main function:
    # main()
    
    print("To use this example, edit this file to configure your input/output files")
    print("and API key, then uncomment the main() function call.")
