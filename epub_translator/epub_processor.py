#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
EPUB Processor for translation.
Handles reading, parsing, translating, and writing EPUB files
while preserving formatting and images.
"""

import os
import logging
import tempfile
import copy
import re
from collections import defaultdict
from tqdm import tqdm
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import base64

logger = logging.getLogger("epub_translator.epub_processor")


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
    
    def __init__(self, translator, term_extractor, batch_size=10, auto_extract_terms=True):
        """Initialize EPUB processor.
        
        Args:
            translator: Translator instance for text translation
            term_extractor: TerminologyExtractor instance for terminology management
            batch_size: Number of paragraphs to translate in one batch
            auto_extract_terms: Whether to automatically extract terminology
        """
        self.translator = translator
        self.term_extractor = term_extractor
        self.batch_size = batch_size
        self.auto_extract_terms = auto_extract_terms
        self.translation_cache = {}
        self.total_chars = 0
        self.total_segments = 0
        self.translated_chars = 0
        self.translated_segments = 0
        
    def translate_epub(self, input_path, output_path):
        """Translate an EPUB file from input_path and save to output_path.
        
        Args:
            input_path: Path to input EPUB file
            output_path: Path to save translated EPUB file
        
        Returns:
            Dictionary with translation statistics
        """
        logger.info(f"Loading EPUB file: {input_path}")
        book = epub.read_epub(input_path)
        
        # Create a deep copy to avoid modifying the original
        translated_book = copy.deepcopy(book)
        
        # Extract metadata we want to preserve
        metadata = self._extract_metadata(book)
        
        # Get all HTML content items
        html_items = []
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                html_items.append(item)
        
        # Process terminology if auto-extraction is enabled
        if self.auto_extract_terms:
            logger.info("Auto-extracting terminology from EPUB content")
            self._extract_terminology(html_items)
        
        # Translate content with progress bar
        logger.info("Translating EPUB content")
        with tqdm(total=len(html_items), desc="Translating chapters") as pbar:
            for item in html_items:
                self._translate_item(item, translated_book)
                pbar.update(1)
        
        # Set metadata in translated book
        self._set_metadata(translated_book, metadata)
        
        # Write the translated book
        logger.info(f"Writing translated EPUB to: {output_path}")
        epub.write_epub(output_path, translated_book)
        
        # Return statistics
        stats = {
            'total_chars': self.total_chars,
            'total_segments': self.total_segments,
            'translated_chars': self.translated_chars,
            'translated_segments': self.translated_segments,
        }
        logger.info(f"Translation complete. Statistics: {stats}")
        return stats
    
    def _extract_metadata(self, book):
        """Extract metadata from the EPUB book.
        
        Args:
            book: ebooklib.epub.EpubBook instance
        
        Returns:
            Dictionary with metadata
        """
        metadata = {}
        
        # Get title and language
        metadata['title'] = book.get_metadata('DC', 'title')
        metadata['language'] = book.get_metadata('DC', 'language')
        
        # Get authors
        metadata['creators'] = book.get_metadata('DC', 'creator')
        
        # Get other metadata
        for meta_type in ['publisher', 'identifier', 'date', 'rights', 'coverage', 'description']:
            metadata[meta_type] = book.get_metadata('DC', meta_type)
        
        return metadata
    
    def _set_metadata(self, book, metadata):
        """Set metadata in the translated book.
        
        Args:
            book: ebooklib.epub.EpubBook instance
            metadata: Dictionary with metadata
        """
        # Clear existing metadata
        for item in list(book.metadata.values()):
            book.metadata.pop(item, None)
        
        # Translate title if available
        if metadata.get('title'):
            original_title = metadata['title'][0][0]
            translated_title = self.translator.translate_text(original_title)
            book.set_title(translated_title)
        
        # Set language to target language
        book.set_language(self.translator.target_lang)
        
        # Set authors (don't translate author names)
        if metadata.get('creators'):
            for creator in metadata['creators']:
                book.add_author(creator[0])
        
        # Set other metadata (translate description)
        if metadata.get('description'):
            desc = metadata['description'][0][0]
            translated_desc = self.translator.translate_text(desc)
            book.add_metadata('DC', 'description', translated_desc)
        
        # Copy other metadata unchanged
        for meta_type in ['publisher', 'identifier', 'date', 'rights', 'coverage']:
            if metadata.get(meta_type):
                for item in metadata[meta_type]:
                    book.add_metadata('DC', meta_type, item[0])
    
    def _extract_terminology(self, html_items):
        """Extract terminology from HTML items.
        
        Args:
            html_items: List of ebooklib.epub.EpubHtml items
        """
        # Extract text content from all items
        all_text = ""
        for item in html_items:
            content = item.get_content().decode('utf-8')
            soup = BeautifulSoup(content, 'html.parser')
            # Extract text, avoiding script, style, etc.
            for tag in soup.find_all(self.SKIP_TAGS):
                tag.extract()
            all_text += soup.get_text() + "\n"
        
        # Extract terminology from text
        self.term_extractor.extract_terminology(all_text)
        logger.info(f"Extracted {len(self.term_extractor.terminology)} terminology items")
    
    def _translate_item(self, item, translated_book):
        """Translate an EPUB HTML item.
        
        Args:
            item: ebooklib.epub.EpubHtml item to translate
            translated_book: Book to add translated item to
        """
        item_id = item.get_id()
        logger.debug(f"Translating item: {item_id}")
        
        # Get content and create BeautifulSoup object
        content = item.get_content().decode('utf-8')
        soup = BeautifulSoup(content, 'html.parser')
        
        # Find all text nodes that need translation
        translatable_segments = self._extract_translatable_segments(soup)
        
        # Group segments into batches for efficient translation
        batches = [
            translatable_segments[i:i + self.batch_size]
            for i in range(0, len(translatable_segments), self.batch_size)
        ]
        
        # Translate batches with progress
        for batch in batches:
            self._translate_batch(batch)
        
        # Update the content with translated text
        translated_content = str(soup)
        
        # Create a new item for the translated book
        translated_item = epub.EpubHtml(
            uid=item.get_id(),
            file_name=item.get_name(),
            media_type="application/xhtml+xml",
            content=translated_content.encode('utf-8')
        )
        
        # Copy properties
        translated_item.properties = item.properties
        
        # Add to the book
        translated_book.add_item(translated_item)
    
    def _extract_translatable_segments(self, soup):
        """Extract translatable text segments from BeautifulSoup object.
        
        Args:
            soup: BeautifulSoup object
        
        Returns:
            List of tuples (element, attribute, text)
            where:
                element: BeautifulSoup element
                attribute: Attribute name or None for text content
                text: Text to translate
        """
        segments = []
        
        # Process text nodes
        for element in soup.find_all(string=True):
            parent = element.parent
            
            # Skip non-translatable elements
            if parent.name in self.SKIP_TAGS:
                continue
            
            # Skip empty text or whitespace-only text
            text = element.strip()
            if not text:
                continue
            
            # Add to translatable segments
            segments.append((element, None, str(element)))
            self.total_segments += 1
            self.total_chars += len(str(element))
        
        # Process translatable attributes
        for tag in soup.find_all():
            for attr in self.TRANSLATABLE_ATTRS:
                if tag.has_attr(attr) and tag[attr].strip():
                    segments.append((tag, attr, tag[attr]))
                    self.total_segments += 1
                    self.total_chars += len(tag[attr])
        
        return segments
    
    def _translate_batch(self, segments):
        """Translate a batch of segments.
        
        Args:
            segments: List of tuples (element, attribute, text)
        """
        # Extract text for translation
        texts = [segment[2] for segment in segments]
        
        # Skip if no texts to translate
        if not texts:
            return
        
        # Apply terminology protection
        protected_texts = [
            self.term_extractor.protect_terminology(text) for text in texts
        ]
        
        # Translate texts
        translated_texts = self.translator.translate_batch(protected_texts)
        
        # Restore terminology
        translated_texts = [
            self.term_extractor.restore_terminology(text) for text in translated_texts
        ]
        
        # Update segments with translations
        for i, (element, attribute, original_text) in enumerate(segments):
            if i < len(translated_texts):
                translated_text = translated_texts[i]
                
                # Update the element
                if attribute is None:
                    # Text node
                    element.replace_with(translated_text)
                else:
                    # Attribute
                    element[attribute] = translated_text
                
                self.translated_segments += 1
                self.translated_chars += len(translated_text)
