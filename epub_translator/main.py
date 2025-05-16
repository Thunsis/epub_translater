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

from .config import Config
from .epub_processor import EPUBProcessor
from .translator import DeepseekTranslator
from .term_extractor import TerminologyExtractor


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
        "--auto-terms", 
        help="Automatically extract domain-specific terminology",
        action="store_true"
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
        
        term_extractor = TerminologyExtractor(
            min_frequency=args.min_term_freq,
            custom_terminology_file=args.terminology
        )
        
        epub_processor = EPUBProcessor(
            translator=translator,
            term_extractor=term_extractor,
            batch_size=args.batch_size,
            auto_extract_terms=args.auto_terms
        )
        
        # Process the EPUB file
        logger.info(f"Starting translation of {args.input_file}")
        epub_processor.translate_epub(args.input_file, args.output)
        logger.info(f"Translation completed. Output saved to {args.output}")
        
    except Exception as e:
        logger.error(f"Error during translation: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
