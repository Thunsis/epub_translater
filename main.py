#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
EPUB Translator with Three-Phase Processing
------------------------------------------
This script translates EPUB books using a three-phase approach:
1. Local processing and preparation (no API calls)
2. Terminology extraction and analysis (for statistics and reference)
3. AI-powered translation with implicit terminology preservation

This approach leverages DeepSeek's natural language understanding capabilities
to recognize and preserve domain-specific terminology without explicit marking
or special segmentation.
"""

import argparse
import os
import sys
import logging
import time
from pathlib import Path
from tqdm import tqdm
import pytz

# Import our modules
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
    parser = argparse.ArgumentParser(description="Three-phase EPUB translation workflow")
    
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
        "-p", "--phase",
        help="Processing phase to run (default: all)",
        choices=["prepare", "terminology", "translate", "all"],
        default="all"
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
        "--force", 
        help="Force restart of the specified phase, ignoring checkpoints",
        action="store_true"
    )
    
    parser.add_argument(
        "--log-level", 
        help="Logging level (default: info)",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info"
    )
    
    return parser.parse_args()


def main():
    """Main function implementing the three-phase workflow"""
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
        
        # Override config with command line arguments where provided
        if args.min_term_freq:
            config.set('terminology', 'min_term_frequency', str(args.min_term_freq))
        if args.batch_size:
            config.set('processing', 'batch_size', str(args.batch_size))
        if args.max_workers:
            config.set('processing', 'max_parallel_requests', str(args.max_workers))
        if args.chunk_size:
            config.set('processing', 'chunk_size', str(args.chunk_size))
        
        # Check if we need DeepSeek API for the requested phase
        api_needed = args.phase in ["terminology", "translate", "all"]
        
        # Initialize components differently based on the phase
        # For prepare phase, we use local_only=True to avoid API calls
        # For other phases, we need the API
        
        # Set up the translator - but don't create it for prepare-only mode
        translator = None
        if api_needed:
            # Verify we have an API key if needed
            api_key = config.get('deepseek', 'api_key')
            if not api_key:
                logger.error(f"DeepSeek API key required for phase '{args.phase}'. Provide it via --api-key or config.ini")
                sys.exit(1)
                
            translator = DeepseekTranslator(
                api_key=api_key,
                source_lang=args.source_lang,
                target_lang=args.target_lang,
                model=config.get('deepseek', 'model'),
                max_retries=config.getint('deepseek', 'max_retries'),
                timeout=config.getint('deepseek', 'timeout'),
                rate_limit=config.getint('deepseek', 'rate_limit')
            )
            logger.info(f"Initialized DeepSeek translator: {args.source_lang} → {args.target_lang}")
        
        # Set up terminology extractor
        # For prepare phase, initialize without the translator to enable local-only mode
        term_extractor = TerminologyExtractor(
            translator=translator,  # Will be None for prepare-only mode
            workdir=os.path.splitext(os.path.basename(args.input_file))[0] + "_workdir",
            use_deepseek=config.getboolean("terminology", "use_deepseek", fallback=True) and api_needed
        )
        
        # Initialize processor with local_only flag for prepare-only mode
        epub_processor = EPUBProcessor(
            translator=translator,
            term_extractor=term_extractor,
            batch_size=config.getint('processing', 'batch_size'),
            auto_extract_terms=config.getboolean('terminology', 'enable_auto_extraction'),
            max_workers=config.getint('processing', 'max_parallel_requests'),
            chunk_size=config.getint('processing', 'chunk_size'),
            config=config,
            local_only=(args.phase == "prepare")
        )
        
        # -------------------------------------------------------------------
        # Phase 1: Local Processing and Preparation
        # -------------------------------------------------------------------
        if args.phase in ["prepare", "all"]:
            logger.info("=== Phase 1: Local Processing and Preparation ===")
            print("Starting local file processing and preparation (no API calls)...")
            
            start_time = time.time()
            
            # Run the extraction and preparation phase
            stats = epub_processor.extract_and_prepare_content(
                args.input_file, 
                args.output, 
                force_restart=args.force
            )
            
            preparation_time = time.time() - start_time
            
            # Display results
            print(f"\n--- Phase 1 Complete: Local Processing and Preparation ---")
            print(f"Processing time: {preparation_time:.2f} seconds")
            print(f"Total segments: {stats['total_segments']}, Total characters: {stats['total_chars']}")
            
            if stats.get('workdir'):
                print(f"Working directory: {stats['workdir']}")
                print("This directory contains all extracted content and prepared batches.")
            
            # Manual cost estimation if not shown in the prepare phase
            try:
                from epub_translator.cost_estimator import estimate_api_cost, format_cost_estimate
                if "api_cost_estimate" not in stats:
                    cost_estimate = estimate_api_cost(stats['total_chars'])
                    cost_report = format_cost_estimate(cost_estimate)
                    print("\n--- DeepSeek API Cost Estimate for Phases 2 & 3 ---")
                    print(cost_report)
            except ImportError:
                logger.warning("Cost estimator not available for manual estimation")
                
            if args.phase == "prepare":
                print("\nLocal-only preparation phase complete.")
                print("You can now run phases 2 and 3 with DeepSeek API integration.")
                return
            
            print("\nContinuing to next phase...\n")
        
        # -------------------------------------------------------------------
        # Phase 2: Terminology Enhancement with DeepSeek
        # -------------------------------------------------------------------
        if args.phase in ["terminology", "all"]:
            logger.info("=== Phase 2: Terminology Enhancement with DeepSeek ===")
            print("Starting terminology enhancement with DeepSeek API...")
            
            start_time = time.time()
            
            # If we didn't run phase 1, we need to load what was prepared previously
            if args.phase == "terminology":
                # We don't have a dedicated method for this yet, but we could add one
                # For now, just extract terminology from the workspace
                workdir = os.path.splitext(os.path.basename(args.input_file))[0] + "_workdir"
                if not os.path.exists(workdir):
                    logger.error(f"Working directory not found: {workdir}")
                    logger.error("Run Phase 1 (--phase prepare) first to generate the working directory")
                    sys.exit(1)
                
                term_extractor.workdir = workdir
                
                # Load terminology candidates from the workdir
                try:
                    term_candidates_file = os.path.join(workdir, "terminology", "term_candidates.json")
                    if os.path.exists(term_candidates_file):
                        # This method is defined in term_extractor to load saved candidates
                        term_extractor._load_term_candidates()
                        logger.info(f"Loaded {len(term_extractor.term_candidates)} term candidates from {term_candidates_file}")
                    else:
                        logger.warning(f"Term candidates file not found: {term_candidates_file}")
                        logger.info("This is normal with the new simplified terminology flow")
                except Exception as e:
                    logger.error(f"Error loading term candidates: {e}")
                    logger.info("Continuing with simplified terminology flow")
            
            # Now enhance terminology with DeepSeek
            try:
                print("Sending book structure to DeepSeek for terminology analysis...")
                # This method will use the DeepSeek API to enhance terminology
                final_terminology = term_extractor.enhance_terminology_with_deepseek()
                
                # Output results
                if final_terminology:
                    preserved_terms = [term for term, info in final_terminology.items() 
                                      if info.get('preserve', False)]
                    print(f"DeepSeek identified {len(preserved_terms)} terms to preserve during translation")
                    print(f"Total terms analyzed: {len(final_terminology)}")
                    
                    # Save terminology to data/terminology directory for reference
                    terminology_dir = os.path.join('data', 'terminology')
                    os.makedirs(terminology_dir, exist_ok=True)
                    
                    # Create terminology filename based on input file
                    input_basename = os.path.splitext(os.path.basename(args.input_file))[0]
                    term_output = os.path.join(terminology_dir, f"{input_basename}_terms.csv")
                    with open(term_output, 'w', encoding='utf-8') as f:
                        f.write("Term,Preserve,Reason\n")
                        for term, info in sorted(final_terminology.items()):
                            if info.get('preserve', True):
                                f.write(f"{term},{info.get('preserve', True)},{info.get('reason', '')}\n")
                    print(f"Terminology saved to {term_output}")
                else:
                    logger.warning("No terminology was enhanced by DeepSeek")
                    print("No terminology was enhanced - translation will proceed with DeepSeek's implicit term handling")
            except Exception as e:
                logger.error(f"Error enhancing terminology: {e}")
                print(f"Error enhancing terminology: {e}")
                if args.phase == "terminology":
                    sys.exit(1)
                print("Continuing to translation phase with DeepSeek's implicit term handling...")
            
            terminology_time = time.time() - start_time
            
            # Display results
            print(f"\n--- Phase 2 Complete: Terminology Enhancement ---")
            print(f"Processing time: {terminology_time:.2f} seconds")
            
            if args.phase == "terminology":
                print("\nTerminology enhancement phase complete.")
                print("You can now run Phase 3 (translation) to translate the content.")
                return
            
            print("\nContinuing to final phase...\n")
        
        # -------------------------------------------------------------------
        # Phase 3: Translation with DeepSeek
        # -------------------------------------------------------------------
        if args.phase in ["translate", "all"]:
            logger.info("=== Phase 3: Translation with DeepSeek ===")
            print("Starting translation with DeepSeek API...")
            
            start_time = time.time()
            
            # For "translate" phase, we need to work with already prepared content
            if args.phase == "translate":
                # Check if we have the required workdir
                workdir = os.path.splitext(os.path.basename(args.input_file))[0] + "_workdir"
                if not os.path.exists(workdir):
                    logger.error(f"Working directory not found: {workdir}")
                    logger.error("Run Phase 1 (--phase prepare) first to generate the working directory")
                    sys.exit(1)
                
                # Check if the prepared content is available
                checkpoint_file = os.path.join(workdir, "checkpoint", "status.json")
                if not os.path.exists(checkpoint_file):
                    logger.error(f"Checkpoint file not found: {checkpoint_file}")
                    logger.error("Run Phase 1 (--phase prepare) first to prepare the content")
                    sys.exit(1)
            
            # Translate the prepared content
            try:
                translation_stats = epub_processor.translate_prepared_content(
                    args.input_file,
                    args.output,
                    force_restart=args.force
                )
                
                if not translation_stats:
                    logger.error("Translation failed - no statistics returned")
                    sys.exit(1)
                
                # Display performance statistics
                translation_time = time.time() - start_time
                
                print(f"\n--- Phase 3 Complete: Translation ---")
                print(f"Translation completed in {translation_time:.2f} seconds")
                print(f"Processing speed: {translation_stats['chars_per_second']:.2f} characters per second")
                print(f"Total segments: {translation_stats['total_segments']}")
                print(f"Total characters: {translation_stats['total_chars']}")
                print(f"Output saved to {args.output}")
            except Exception as e:
                logger.error(f"Error during translation: {e}")
                print(f"Error during translation: {e}")
                sys.exit(1)
        
        # All phases complete
        if args.phase == "all":
            total_time = time.time() - start_time
            print(f"\n--- All Phases Complete ---")
            print(f"Total processing time: {total_time:.2f} seconds")
            print(f"Output saved to {args.output}")
        
    except Exception as e:
        logger.error(f"Error during processing: {str(e)}", exc_info=True)
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
