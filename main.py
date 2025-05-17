#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Main module for EPUB Translator.
Provides command-line interface and high-level functionality.
"""

import os
import sys
import logging
import argparse
import time
import nltk

from epub_translator.config import Config
from epub_translator import get_translator, get_term_extractor, get_processor

logger = logging.getLogger("epub_translator")

def check_nltk_data():
    """Check if required NLTK data is available, suggest downloading if not."""
    try:
        nltk.data.find('tokenizers/punkt')
        return True
    except LookupError:
        logger.error("NLTK punkt tokenizer not found. This is required for text processing.")
        logger.error("Please run 'python -m epub_translator.download_nltk' first to download required data.")
        return False

def translate_epub(input_path, output_path, config_path=None, api_key=None, 
                  source_lang=None, target_lang=None, terminology_file=None,
                  batch_size=None, max_workers=None):
    """Translate an EPUB file from one language to another.
    
    Args:
        input_path: Path to input EPUB file
        output_path: Path to save translated EPUB file
        config_path: Path to configuration file (default: config.ini)
        api_key: Deepseek API key (overrides config)
        source_lang: Source language code (overrides config)
        target_lang: Target language code (overrides config)
        terminology_file: Path to custom terminology file
        batch_size: Number of paragraphs to batch for translation
        max_workers: Maximum number of worker threads
    
    Returns:
        Dictionary with translation statistics
    """
    # Verify input file exists
    if not os.path.exists(input_path):
        logger.error(f"Input file not found: {input_path}")
        return
    
    # Default output path if not provided
    if not output_path:
        base_name = os.path.basename(input_path)
        output_path = f"translated_{base_name}"
    
    # Create output directory if needed
    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)
    
    # Verify NLTK data is available
    if not check_nltk_data():
        return None
    
    # Load configuration
    start_time = time.time()
    config = Config(config_path or "config.ini")
    
    # Override config with command-line arguments
    if api_key:
        config.set("deepseek", "api_key", api_key)
    if source_lang:
        config.set("translation", "source_lang", source_lang)
    if target_lang:
        config.set("translation", "target_lang", target_lang)
    if batch_size:
        config.set("processing", "batch_size", str(batch_size))
    if max_workers:
        config.set("processing", "max_parallel_requests", str(max_workers))
    
    # Check API key
    if not config.get("deepseek", "api_key"):
        logger.error("No API key provided. Set API_KEY environment variable or use --api-key option.")
        return
    
    # Initialize components using factory methods
    try:
        logger.info(f"Initializing components for translation")
        
        # Initialize translator with optimized methods if available
        translator = get_translator(config)
        
        # Check if we should use the optimized methods (monkeypatch)
        if hasattr(translator, 'translate_batch_optimized') and config.getboolean("processing", "use_optimized_translator", fallback=True):
            logger.info("Using optimized async translation methods")
            translator.translate_batch = translator.translate_batch_optimized
            translator.translate_text = translator.translate_text_optimized
        
        # Initialize term extractor (pass translator for DeepSeek-powered term extraction)
        term_extractor = get_term_extractor(config, translator)
        
        # Load custom terminology if provided
        if terminology_file:
            if os.path.exists(terminology_file):
                term_extractor.load_terminology(terminology_file)
            else:
                logger.warning(f"Terminology file not found: {terminology_file}")
        
        # Initialize EPUB processor
        processor = get_processor(config, translator, term_extractor)
        
        # Process the EPUB file
        logger.info(f"Translating EPUB: {input_path} -> {output_path}")
        stats = processor.translate_epub(input_path, output_path)
        
        # Add total processing time to stats
        end_time = time.time()
        stats['total_time'] = end_time - start_time
        
        # Clean up resources
        if hasattr(translator, 'cleanup'):
            translator.cleanup()
        
        # Report results
        logger.info(f"Translation completed in {stats['total_time']:.2f} seconds")
        logger.info(f"Total characters: {stats['total_chars']}")
        logger.info(f"Total segments: {stats['total_segments']}")
        
        return stats
        
    except Exception as e:
        logger.error(f"Error during translation: {str(e)}", exc_info=True)
        return None

def main():
    """Main entry point for command-line interface."""
    parser = argparse.ArgumentParser(description="Translate EPUB books using Deepseek API")
    
    # Add download-only option
    parser.add_argument("--download-nltk", action="store_true", 
                        help="Download required NLTK data and exit")
    
    # Input/output arguments
    parser.add_argument("input", nargs="?", help="Input EPUB file path")
    parser.add_argument("-o", "--output", help="Output EPUB file path")
    
    # Configuration arguments
    parser.add_argument("-c", "--config", help="Configuration file path")
    parser.add_argument("-k", "--api-key", help="Deepseek API key")
    parser.add_argument("-s", "--source-lang", help="Source language code")
    parser.add_argument("-t", "--target-lang", help="Target language code")
    
    # Terminology arguments
    parser.add_argument("--terminology", help="Path to custom terminology file")
    parser.add_argument("--no-auto-terms", action="store_true", help="Disable automatic terminology extraction")
    parser.add_argument("--min-term-freq", type=int, help="Minimum term frequency for extraction")
    
    # Processing arguments
    parser.add_argument("--batch-size", type=int, help="Number of paragraphs to batch for translation")
    parser.add_argument("--max-workers", type=int, help="Maximum number of worker threads")
    parser.add_argument("--chunk-size", type=int, help="Size of content chunks in characters")
    
    # Optimization flags
    parser.add_argument("--optimize", action="store_true", help="Use optimized async translation (default)", default=True)
    parser.add_argument("--no-optimize", action="store_true", help="Disable optimized async translation")
    
    # Logging arguments
    parser.add_argument("--log-level", choices=["debug", "info", "warning", "error"], default="info", help="Logging level")
    
    args = parser.parse_args()
    
    # Set log level
    log_level = getattr(logging, args.log_level.upper())
    for handler in logging.root.handlers:
        handler.setLevel(log_level)
        
    # Handle download-only mode
    if args.download_nltk:
        print("NLTK Downloader for EPUB Translator")
        print("===================================")
        try:
            import ssl
            try:
                _create_unverified_https_context = ssl._create_unverified_context
            except AttributeError:
                pass
            else:
                ssl._create_default_https_context = _create_unverified_https_context
            
            print("Downloading NLTK punkt tokenizer...")
            nltk.download('punkt', quiet=False)
            print("Download complete. You can now run the translator.")
            return 0
        except Exception as e:
            print(f"Error downloading NLTK data: {e}")
            print("Please run the script 'python -m epub_translator.download_nltk' instead.")
            return 1
    
    # Determine whether to use optimized methods
    use_optimized = args.optimize and not args.no_optimize
    
    # Check if input was provided (required unless downloading)
    if not args.input and not args.download_nltk:
        parser.error("the following arguments are required: input")
        return 1
        
    # Translate the file
    config = Config(args.config or "config.ini")
    config.set("processing", "use_optimized_translator", str(use_optimized))
    
    if args.no_auto_terms:
        config.set("terminology", "enable_auto_extraction", "False")
    
    if args.min_term_freq:
        config.set("terminology", "min_term_frequency", str(args.min_term_freq))
    
    stats = translate_epub(
        args.input,
        args.output,
        config_path=args.config,
        api_key=args.api_key,
        source_lang=args.source_lang,
        target_lang=args.target_lang,
        terminology_file=args.terminology,
        batch_size=args.batch_size,
        max_workers=args.max_workers
    )
    
    if stats:
        # Print a summary of the translation
        print("\nTranslation Summary:")
        print(f"- Input file: {args.input}")
        print(f"- Output file: {args.output or ('translated_' + os.path.basename(args.input))}")
        print(f"- Characters processed: {stats['translated_chars']:,} / {stats['total_chars']:,}")
        print(f"- Segments processed: {stats['translated_segments']:,} / {stats['total_segments']:,}")
        print(f"- Processing time: {stats['total_time']:.2f} seconds")
        print(f"- Processing speed: {stats['chars_per_second']:.2f} characters per second")
        
        # Calculate word stats (rough estimate: 5 chars per word)
        words_per_second = stats['chars_per_second'] / 5
        print(f"- Approximate words per second: {words_per_second:.2f}")
        
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main())
