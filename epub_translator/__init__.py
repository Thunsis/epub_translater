#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
EPUB Translator using Deepseek API
Package for translating EPUB books while preserving formatting and images.
"""

import logging
import sys

__version__ = "0.1.0"
__author__ = "Epub Translator Team"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

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

def get_term_extractor(config, translator=None):
    from .term_extractor import TerminologyExtractor
    return TerminologyExtractor(
        min_frequency=config.getint("terminology", "min_term_frequency"),
        max_term_length=config.getint("terminology", "max_term_length"),
        ignore_case=config.getboolean("terminology", "ignore_case"),
        translator=translator
    )

def get_processor(config, translator, term_extractor):
    from .epub_processor import EPUBProcessor
    return EPUBProcessor(
        translator=translator,
        term_extractor=term_extractor,
        batch_size=config.getint("processing", "batch_size"),
        auto_extract_terms=config.getboolean("terminology", "enable_auto_extraction"),
        max_workers=config.getint("processing", "max_parallel_requests")
    )
