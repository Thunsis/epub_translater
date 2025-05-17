#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
EPUB Processor for translation.
Handles reading, parsing, translating, and writing EPUB files
while preserving formatting and images.
Features checkpoint support for resumable processing and detailed content tracking.
"""

# Import core module for EPUBProcessor class definition
from epub_translator.epub_processor_core import EPUBProcessor

# Import extraction functions
from epub_translator.epub_processor_extraction import extract_and_prepare_content

# Import trabao chnslation functions
from epub_translator.epub_processor_translation import (
    translate_prepared_content,
    translate_epub,
    _translate_prepared_batch,
    _translate_item_parallel,
    _translate_batch
)

# Import utility functions
from epub_translator.epub_processor_utils import (
    _extract_metadata,
    _set_metadata,
    _save_translation_cache,
    _dummy_extract_terminology,
    _extract_toc_text,
    _extract_text_from_item,
    _update_segment,
    _extract_translatable_segments
)

# Add methods to EPUBProcessor class
EPUBProcessor.extract_and_prepare_content = extract_and_prepare_content
EPUBProcessor.translate_prepared_content = translate_prepared_content
EPUBProcessor.translate_epub = translate_epub
EPUBProcessor._translate_prepared_batch = _translate_prepared_batch
EPUBProcessor._translate_item_parallel = _translate_item_parallel
EPUBProcessor._translate_batch = _translate_batch
EPUBProcessor._extract_metadata = _extract_metadata
EPUBProcessor._set_metadata = _set_metadata
EPUBProcessor._save_translation_cache = _save_translation_cache
EPUBProcessor._extract_terminology = _dummy_extract_terminology
EPUBProcessor._extract_toc_text = _extract_toc_text
EPUBProcessor._extract_text_from_item = _extract_text_from_item
EPUBProcessor._update_segment = _update_segment
EPUBProcessor._extract_translatable_segments = _extract_translatable_segments

# Keep the EPUBProcessor class at the module level for backward compatibility
__all__ = ['EPUBProcessor']
