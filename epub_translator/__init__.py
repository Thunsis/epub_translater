#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
EPUB Translator using Deepseek API
Package for translating EPUB books while preserving formatting and images.
Features checkpoint support for resumable processing and detailed progress reporting.
"""

import logging
import sys
import os

__version__ = "0.2.0"
__author__ = "Epub Translator Team"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# Check for checkpoint support modules
CHECKPOINT_SUPPORT = False
try:
    from .checkpoint_manager import CheckpointManager
    from .progress_tracker import ProgressTracker
    from .content_manager import ContentManager
    from .paragraph_divider import TextDivider
    CHECKPOINT_SUPPORT = True
except ImportError:
    pass

# Fix for circular imports - defer actual imports
def get_translator(config):
    from .translator import DeepseekTranslator
    return DeepseekTranslator(
        api_key=config.get("deepseek", "api_key"),
        source_lang=config.get("translation", "source_lang", fallback="en"),
        target_lang=config.get("translation", "target_lang", fallback="zh-CN"),
        model=config.get("deepseek", "model"),
        max_retries=config.getint("deepseek", "max_retries"),
        timeout=config.getint("deepseek", "timeout"), 
        rate_limit=config.getint("deepseek", "rate_limit")
    )

def get_term_extractor(config, translator=None, checkpoint_manager=None, word_frequencies=None):
    from .term_extractor import TerminologyExtractor
    
    # Get workdir from checkpoint manager if available
    workdir = None
    if checkpoint_manager is not None:
        workdir = checkpoint_manager.workdir
    
    # Create terminology extractor with new interface
    term_extractor = TerminologyExtractor(
        translator=translator,
        workdir=workdir,
        min_frequency=config.getint("terminology", "min_term_frequency", fallback=3),
        max_term_length=config.getint("terminology", "max_term_length", fallback=5),
        ignore_case=config.getboolean("terminology", "ignore_case", fallback=True),
        use_deepseek=config.getboolean("terminology", "use_deepseek", fallback=True)
    )
    
    # Set word frequencies if provided
    if word_frequencies:
        term_extractor.word_frequencies.update(word_frequencies)
    
    return term_extractor

def get_processor(config, translator, term_extractor):
    from .epub_processor import EPUBProcessor
    processor = EPUBProcessor(
        translator=translator,
        term_extractor=term_extractor,
        batch_size=config.getint("processing", "batch_size"),
        auto_extract_terms=config.getboolean("terminology", "enable_auto_extraction"),
        max_workers=config.getint("processing", "max_parallel_requests"),
        chunk_size=config.getint("processing", "chunk_size", fallback=5000),
        config=config
    )
    
    # 确保术语提取器能够使用处理器中收集的词频信息
    if term_extractor and hasattr(processor, 'word_frequencies'):
        term_extractor.word_frequencies = processor.word_frequencies
        
    return processor

def has_checkpoint_support():
    """Check if checkpoint support is available.
    
    Returns:
        True if checkpoint support is available, False otherwise
    """
    return CHECKPOINT_SUPPORT

def create_checkpoint_manager(input_path, output_path, config=None):
    """Create a checkpoint manager.
    
    Args:
        input_path: Path to input EPUB file
        output_path: Path to output EPUB file
        config: Configuration object (optional)
    
    Returns:
        CheckpointManager instance or None if not supported
    """
    if not CHECKPOINT_SUPPORT:
        return None
        
    return CheckpointManager(input_path, output_path, config)

def create_progress_tracker(checkpoint_manager=None):
    """Create a progress tracker.
    
    Args:
        checkpoint_manager: CheckpointManager instance (optional)
    
    Returns:
        ProgressTracker instance or None if not supported
    """
    if not CHECKPOINT_SUPPORT:
        return None
        
    return ProgressTracker(checkpoint_manager)

def create_content_manager(workdir):
    """Create a content manager.
    
    Args:
        workdir: Working directory
    
    Returns:
        ContentManager instance or None if not supported
    """
    if not CHECKPOINT_SUPPORT:
        return None
        
    return ContentManager(workdir)
