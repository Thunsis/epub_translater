#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
EPUB Translator using Deepseek API
Package for translating EPUB books while preserving formatting and images.
"""

__version__ = "0.1.0"
__author__ = "Epub Translator Team"

from .config import Config
from .translator import DeepseekTranslator
from .term_extractor import TerminologyExtractor
from .epub_processor import EPUBProcessor
