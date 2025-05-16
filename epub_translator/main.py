#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
EPUB Translator using Deepseek API
This script translates EPUB books while preserving formatting and images.
It also detects and preserves domain-specific terminology.
"""

import argparse
import os
import sys
import logging
from tqdm import tqdm

# Fix imports to work both as a module and as a script
try:
    # When run as a module in the package
    from .config import Config
    from .epub_processor import EPUBProcessor
    from .translator import DeepseekTranslator
    from .term_extractor import TerminologyExtractor
except ImportError:
    # When run as a script directly
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from epub_translator.config import Config
    from epub_translator.epub_processor import EPUBProcessor
    from epub_translator.translator import DeepseekTranslator
    from epub_translator.term_extractor import TerminologyExtractor


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
    parser = argparse.ArgumentParser(description="Translate EPUB files using Deepseek API")
    
    parser.add_argument(
        "input_file", 
        help="Path to the input EPUB file"
    )
    
    parser.add_argument(
        "-o", "--output", 
        help="Path to the output EPUB file (default: translated_[input_filename])",
        default=None
    )
    
    parser.add_argument(
        "-s", "--source-lang", 
        help="Source language (default: auto-detect)",
        default="auto"
    )
    
    parser.add_argument(
        "-t", "--target-lang", 
        help="Target language (default: zh-CN)",
        default="zh-CN"
    )
    
    parser.add_argument(
        "-c", "--config", 
        help="Path to configuration file",
        default="config.ini"
    )
    
    parser.add_argument(
        "-k", "--api-key", 
        help="Deepseek API key (overrides config file)",
        default=None
    )
    
    parser.add_argument(
        "--terminology", 
        help="Path to custom terminology file (CSV format: term,translation)",
        default=None
    )
    
    parser.add_argument(
        "--no-auto-terms", 
        help="Disable automatic domain-specific terminology extraction (enabled by default)",
        action="store_false",
        dest="auto_terms",
        default=True
    )
    
    parser.add_argument(
        "--min-term-freq", 
        help="Minimum frequency for auto-detected terminology (default: 3)",
        type=int, 
        default=3
    )
    
    parser.add_argument(
        "--batch-size", 
        help="Number of paragraphs to translate in one batch (default: 10)",
        type=int, 
        default=10
    )
    
    parser.add_argument(
        "--max-workers", 
        help="Maximum number of worker threads for parallel processing (default: 4)",
        type=int, 
        default=4
    )
    
    parser.add_argument(
        "--chunk-size", 
        help="Size of content chunks for processing in characters (default: 5000)",
        type=int, 
        default=5000
    )
    
    parser.add_argument(
        "--log-level", 
        help="Logging level (default: info)",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info"
    )
    
    return parser.parse_args()


def main():
    """Main function"""
    args = parse_arguments()
    logger = setup_logging(args.log_level)
    
    # Validate input file
    if not os.path.exists(args.input_file):
        logger.error(f"Input file does not exist: {args.input_file}")
        sys.exit(1)
    
    # Set output file if not specified
    if args.output is None:
        input_basename = os.path.basename(args.input_file)
        input_dirname = os.path.dirname(args.input_file)
        output_basename = f"translated_{input_basename}"
        args.output = os.path.join(input_dirname, output_basename)
    
    try:
        # Load configuration
        config = Config(args.config)
        if args.api_key:
            config.set('deepseek', 'api_key', args.api_key)
        
        # Initialize components
        translator = DeepseekTranslator(
            api_key=config.get('deepseek', 'api_key'),
            source_lang=args.source_lang,
            target_lang=args.target_lang
        )
        
        # Initialize terminology extractor with translator for Deepseek-powered terminology
        term_extractor = TerminologyExtractor(
            min_frequency=args.min_term_freq,
            custom_terminology_file=args.terminology,
            use_deepseek=True,  # Enable Deepseek for terminology translation
            translator=translator  # Connect translator for terminology translation
        )
        
        epub_processor = EPUBProcessor(
            translator=translator,
            term_extractor=term_extractor,
            batch_size=args.batch_size,
            auto_extract_terms=args.auto_terms,
            max_workers=args.max_workers,
            chunk_size=args.chunk_size
        )
        
        # Create data/terminology directory if it doesn't exist
        terminology_dir = os.path.join('data', 'terminology')
        os.makedirs(terminology_dir, exist_ok=True)
        
        # Process the EPUB file
        logger.info(f"Starting translation of {args.input_file}")
        stats = epub_processor.translate_epub(args.input_file, args.output)
        
        # Save extracted terminology to file
        if args.auto_terms and hasattr(term_extractor, 'terminology') and term_extractor.terminology:
            # Create terminology filename based on input file
            input_basename = os.path.splitext(os.path.basename(args.input_file))[0]
            term_output = os.path.join(terminology_dir, f"{input_basename}_terms.csv")
            term_extractor.save_terminology(term_output)
            logger.info(f"Extracted terminology saved to {term_output}")
        
        # Display performance statistics
        if 'processing_time' in stats and 'chars_per_second' in stats:
            logger.info(f"Translation completed in {stats['processing_time']:.2f} seconds")
            logger.info(f"Processing speed: {stats['chars_per_second']:.2f} characters per second")
        
        logger.info(f"Output saved to {args.output}")
        
    except Exception as e:
        logger.error(f"Error during translation: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
