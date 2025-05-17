#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Core EPUB Processor module containing the base EPUBProcessor class,
initialization, configuration, and signal handling.
"""

import os
import logging
import signal
import sys
import threading
from collections import Counter
import nltk

# Configure logger
logger = logging.getLogger("epub_translator.epub_processor")

# Import our custom modules conditionally to handle the case when they're not available
try:
    from epub_translator.checkpoint_manager import CheckpointManager
    from epub_translator.progress_tracker import ProgressTracker
    from epub_translator.content_manager import ContentManager
    from epub_translator.paragraph_divider import TextDivider
    CHECKPOINT_SUPPORT = True
except ImportError:
    logger.warning("Checkpoint support modules not found, running without checkpoint capabilities")
    CHECKPOINT_SUPPORT = False

# Try to ensure NLTK data is available for smart text splitting
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    logger.info("Downloading NLTK punkt tokenizer for smart text splitting")
    # Disable SSL verification to avoid download issues
    try:
        import ssl
        _create_unverified_https_context = ssl._create_unverified_context
    except AttributeError:
        pass
    else:
        ssl._create_default_https_context = _create_unverified_https_context
    
    # Set a timeout for the download to prevent hanging
    nltk.download('punkt', quiet=True, timeout=30)


class EPUBProcessor:
    """Processor for translating EPUB files."""
    
    # Elements that should not be translated
    SKIP_TAGS = {
        'script', 'style', 'code', 'pre', 'head', 'math', 'svg', 'video',
        'audio', 'iframe', 'canvas', 'object', 'embed', 'noscript',
    }
    
    # Attributes that may contain translatable text
    TRANSLATABLE_ATTRS = {
        'alt', 'title', 'aria-label', 'placeholder'
    }
    
    def __init__(self, translator=None, term_extractor=None, batch_size=10, auto_extract_terms=True, 
                 max_workers=4, chunk_size=5000, config=None, local_only=False):
        """Initialize EPUB processor.
        
        Args:
            translator: Translator instance for text translation
            term_extractor: TerminologyExtractor instance for terminology management
            batch_size: Number of paragraphs to translate in one batch
            auto_extract_terms: Whether to automatically extract terminology
            max_workers: Maximum number of worker threads for parallel processing
            chunk_size: Size of content chunks for processing (in characters)
            config: Configuration object (optional)
            local_only: Whether to only perform local processing (no API calls)
        """
        self.translator = translator
        self.term_extractor = term_extractor
        self.batch_size = batch_size
        self.auto_extract_terms = auto_extract_terms
        self.max_workers = max_workers
        self.chunk_size = chunk_size
        self.translation_cache = {}
        self.total_chars = 0
        self.total_segments = 0
        self.translated_chars = 0
        self.translated_segments = 0
        self.lock = threading.Lock()  # Lock for thread-safe operations
        self.config = config
        self.local_only = local_only
        
        # Checkpoint and progress tracking support
        self.checkpoint_manager = None
        self.progress_tracker = None
        self.content_manager = None
        self.force_restart = False
        
        # Initialize text divider for paragraph-aware batching
        self.text_divider = TextDivider()
        
        # Signal handling for graceful termination
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful termination."""
        if sys.platform != 'win32':  # Not all signals available on Windows
            signal.signal(signal.SIGTERM, self._handle_termination)
        signal.signal(signal.SIGINT, self._handle_termination)
    
    def _handle_termination(self, signum, frame):
        """Handle termination signals by saving checkpoint."""
        logger.warning(f"Received termination signal {signum}, saving checkpoint before exit")
        if self.checkpoint_manager:
            self.checkpoint_manager.save_checkpoint()
        if self.progress_tracker:
            self.progress_tracker._print_progress("Translation interrupted, checkpoint saved", newline=True)
        sys.exit(1)
