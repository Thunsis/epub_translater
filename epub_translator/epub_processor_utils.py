#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Utility functions for the EPUBProcessor class.
Contains shared functionality for handling metadata, translatable segments,
and other common operations.
"""

import os
import logging
import re
import json
from collections import Counter
import nltk
from bs4 import BeautifulSoup

# Configure logger
logger = logging.getLogger("epub_translator.epub_processor")

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

def _collect_word_frequencies(self, text):
    """Collect word frequencies from text to enhance terminology extraction.
    
    This helps identify important technical terms by frequency analysis.
    
    Args:
        text: Text to analyze
        
    Returns:
        Counter object with word frequencies
    """
    # Split text into words (keeping only alphanumeric)
    words = re.findall(r'\b[a-zA-Z0-9_\-]+\b', text)
    
    # Count frequencies (case-insensitive)
    word_freq = Counter([word.lower() for word in words if len(word) > 2])
    
    # Update global word frequencies
    self.word_frequencies.update(word_freq)
    
    return word_freq

def _save_translation_cache(self):
    """Save translation cache to file."""
    if not self.checkpoint_manager or not self.translation_cache:
        return
        
    try:
        # We need to convert keys to string for JSON serialization
        serializable_cache = {}
        for key, value in self.translation_cache.items():
            if isinstance(key, tuple):
                serializable_cache[str(key)] = value
            else:
                serializable_cache[key] = value
        
        cache_path = f"{self.checkpoint_manager.workdir}/translation_cache.json"
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_cache, f, ensure_ascii=False)
            
        logger.debug(f"Saved {len(self.translation_cache)} translations to cache file")
    except Exception as e:
        logger.error(f"Error saving translation cache: {e}")

def _dummy_extract_terminology(self, html_items):
    """Dummy function that always returns 0.
    This is a placeholder to maintain API compatibility after terminology extraction was deprecated.
    
    Args:
        html_items: List of HTML items from the EPUB (not used)
    
    Returns:
        Always 0
    """
    logger.info("Local terminology extraction is completely deprecated")
    return 0

def _extract_toc_text(self, html_items):
    """Extract text from the table of contents.
    
    Args:
        html_items: List of ebooklib.epub.EpubHtml items
    
    Returns:
        String containing the table of contents text or empty string if not found
    """
    # Look for common TOC identifiers in HTML items
    toc_text = ""
    toc_identifiers = [
        'toc', 'contents', 'table-of-contents', 'tableofcontents', 
        'content-table', 'index', 'nav', 'catalog', 'menu'
    ]
    
    # Try to find TOC by looking for nav elements and common TOC identifiers
    for item in html_items:
        content = item.get_content().decode('utf-8')
        soup = BeautifulSoup(content, 'html.parser')
        
        # Look for nav elements which often contain the TOC
        nav_elements = soup.find_all('nav')
        if nav_elements:
            for nav in nav_elements:
                toc_text += nav.get_text() + "\n"
                
        # Check if this item looks like a TOC based on ID/class/filename
        item_id = item.get_id().lower()
        file_name = item.get_name().lower()
        
        is_toc = False
        for identifier in toc_identifiers:
            if (identifier in item_id or 
                identifier in file_name or 
                soup.find(id=identifier) or 
                soup.find(class_=identifier)):
                is_toc = True
                break
        
        if is_toc:
            # Extract just the text from this item, skipping non-content elements
            for tag in soup.find_all(self.SKIP_TAGS):
                tag.extract()
            toc_text += soup.get_text() + "\n"
            
        # Look for headings with chapter/section indicators
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        for heading in headings:
            heading_text = heading.get_text().strip()
            if heading_text:
                toc_text += heading_text + "\n"
    
    # Also extract chapter titles, which likely contain domain terminology
    for item in html_items:
        content = item.get_content().decode('utf-8')
        soup = BeautifulSoup(content, 'html.parser')
        
        # Get main headings which are often chapter titles
        headings = soup.find_all(['h1', 'h2'], limit=5)  # Limit to first few headings
        for heading in headings:
            heading_text = heading.get_text().strip()
            if heading_text and len(heading_text.split()) > 1:  # Skip single-word headings
                toc_text += heading_text + "\n"
    
    return toc_text

def _extract_text_from_item(self, item):
    """Extract text content from an EPUB HTML item.
    
    Args:
        item: ebooklib.epub.EpubHtml item
    
    Returns:
        Extracted text content
    """
    content = item.get_content().decode('utf-8')
    soup = BeautifulSoup(content, 'html.parser')
    
    # Extract text, avoiding script, style, etc.
    for tag in soup.find_all(self.SKIP_TAGS):
        tag.extract()
    
    return soup.get_text()

def _update_segment(self, element, attribute, translated_text):
    """Update a segment with translated text.
    
    Args:
        element: BeautifulSoup element
        attribute: Attribute name or None for text content
        translated_text: Translated text
    """
    # Update the element
    if attribute is None:
        # Text node
        element.replace_with(translated_text)
    else:
        # Attribute
        element[attribute] = translated_text
    
    # Thread-safe increment of statistics
    with self.lock:
        self.translated_segments += 1
        self.translated_chars += len(translated_text)

def _extract_translatable_segments(self, soup, item_id=None):
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
    # Special case for index files - do not translate index files at all
    # Return empty segments list for index files to preserve original content
    if item_id and 'index' in item_id.lower():
        logger.debug(f"Detected index file: {item_id} - skipping translation completely")
        return []
    
    segments = []
    processed_elements = set()
    
    # Additional skip patterns for special content like XML declarations, DOCTYPE, etc.
    skip_patterns = [
        r'^\s*<\?xml.*\?>\s*$',   # XML declaration
        r'^\s*xml\s+version=.*\?>\s*$',  # Partial XML declaration without opening <?
        r'^\s*xml\s+version=.*$',  # Just the XML version part
        r'^\s*<!DOCTYPE.*>\s*$',  # DOCTYPE declaration
        r'^\s*<html.*>\s*$',      # HTML tag
        r'^\s*html.*>\s*$',       # Partial HTML tag
        r'^\s*html\s*$',          # Just the html word
        r'^\s*HTML\s*$',          # Just the HTML word (uppercase)
        r'^\s*<\/html>\s*$',      # HTML closing tag
        r'^\s*<body.*>\s*$',      # BODY tag
        r'^\s*body.*>\s*$',       # Partial BODY tag
        r'^\s*body\s*$',          # Just the body word
        r'^\s*<\/body>\s*$',      # BODY closing tag
        r'^\s*<head.*>\s*$',      # HEAD tag
        r'^\s*head.*>\s*$',       # Partial HEAD tag
        r'^\s*head\s*$',          # Just the head word
        r'^\s*<\/head>\s*$',      # HEAD closing tag
        r'^\s*\W+$',              # Strings with only non-word characters (symbols, arrows, etc.)
        r'^\s*↪\s*$',             # Special line continuation character
        # Only filter standalone figure/table words, not when they're part of a title or sentence
        r'^\s*figure\s*$',        # Single word "figure" - common in technical books
        r'^\s*Figure\s*$',        # Single word "Figure" - common in technical books
        r'^\s*TABLE\s*$',         # Single word "TABLE"
        r'^\s*Table\s*$',         # Single word "Table"
        r'^\s*LISTING\s*$',       # Single word "LISTING"
        r'^\s*Listing\s*$',       # Single word "Listing"
        r'^\s*Example\s*$',       # Single word "Example"
        r'^\s*EXAMPLE\s*$',       # Single word "EXAMPLE"
        r'^\s*fig\.\s*\d+\s*$',   # Figure numbers like "fig. 1"
    ]

    # More nuanced handling for code listings and titles
    listing_patterns = [
        r'^\s*[Ff]igure\s+\d+', # Figure references with or without text
        r'^\s*[Tt]able\s+\d+',  # Table references with or without text
        r'^\s*[Ll]isting\s+\d+', # Listing references with or without text
        r'^\s*\d+\.\d+\s+', # Section numbers with text
        r'^\s*Example\s+\d+', # Example references
    ]
    
    def should_skip_text(text, item_id=None):
        """Check if text matches any patterns that should be skipped.
        
        Args:
            text: The text to check
            item_id: Optional ID of the HTML item (for item-specific rules)
        """
        if not text or not text.strip():
            return True
            
        # Check against standard skip patterns
        for pattern in skip_patterns:
            if re.match(pattern, text):
                return True
        
        return False
    
    def is_title_or_heading(text):
        """Check if text is a title or heading that should be kept intact."""
        # Special case for listings, figures, tables with titles
        for pattern in listing_patterns:
            if re.match(pattern, text):
                return True
        return False
    
    # First identify paragraphs and other block-level elements that we want
    # to process as cohesive units
    paragraph_elements = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'figcaption', 
                          'th', 'td', 'blockquote']
    container_elements = ['div', 'section', 'article', 'main', 'aside', 'header', 'footer']
    
    # Create a preprocessing step to identify text nodes that belong together logically
    def get_parent_paragraph(node):
        """Get the top-level paragraph element that contains this node."""
        current = node
        while current and current.parent and current.parent.name not in ['body', 'html']:
            if current.parent.name in paragraph_elements:
                return current.parent
            current = current.parent
        return None
        
    # First, group text nodes by their parent paragraphs to maintain context
    paragraph_to_nodes = {}
    for node in soup.find_all(string=True):
        # Skip if in non-translatable area
        if node.parent.name in self.SKIP_TAGS or any(p.name in self.SKIP_TAGS for p in node.parent.parents):
            continue
            
        # Skip empty nodes
        if not node.strip():
            continue
            
        # Find containing paragraph
        parent_para = get_parent_paragraph(node)
        if parent_para:
            if parent_para not in paragraph_to_nodes:
                paragraph_to_nodes[parent_para] = []
            paragraph_to_nodes[parent_para].append(node)
    
    # Process each paragraph as a unit
    for parent_elem, text_nodes in paragraph_to_nodes.items():
        # Skip already processed elements
        if parent_elem in processed_elements:
            continue
            
        # Filter out nodes from non-translatable elements and those matching skip patterns
        text_nodes = [node for node in text_nodes 
                     if node.parent.name not in self.SKIP_TAGS and 
                     not any(p.name in self.SKIP_TAGS for p in node.parent.parents) and
                     not should_skip_text(str(node), item_id)]
        
        if not text_nodes:
            continue
        
        # Skip nodes that are already processed
        text_nodes = [node for node in text_nodes if node not in processed_elements]
        if not text_nodes:
            continue
            
        # For headings and special elements, always preserve the full text
        if parent_elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] or is_title_or_heading(parent_elem.get_text()):
            combined_text = parent_elem.get_text().strip()
            if combined_text and not should_skip_text(combined_text, item_id):
                segments.append((text_nodes[0], None, combined_text))
                processed_elements.add(parent_elem)
                processed_elements.update(text_nodes)
                with self.lock:
                    self.total_segments += 1
                    self.total_chars += len(combined_text)
            continue
        
        # For all other paragraph elements, join the text with proper spacing
        filtered_nodes = []
        for node in text_nodes:
            if node not in processed_elements and not should_skip_text(str(node), item_id):
                filtered_nodes.append(node)
                
        if not filtered_nodes:
            continue
            
        # Join all text in the paragraph, preserving natural spacing
        full_paragraph = parent_elem.get_text(" ").strip()
        
        # Only include if the paragraph has meaningful content
        if full_paragraph and not should_skip_text(full_paragraph, item_id):
            segments.append((filtered_nodes[0], None, full_paragraph))
            processed_elements.add(parent_elem)
            processed_elements.update(filtered_nodes)
            with self.lock:
                self.total_segments += 1
                self.total_chars += len(full_paragraph)
    
    # Next, process container elements that might contain orphaned text nodes
    # but only if they contain direct text (not just child elements with text)
    for container in soup.find_all(container_elements):
        # Skip containers that are in non-translatable areas
        if container.name in self.SKIP_TAGS or any(parent.name in self.SKIP_TAGS 
                                              for parent in container.parents):
            continue
            
        # Skip already processed containers
        if container in processed_elements:
            continue
        
        # Look only at direct text children (not inside other elements)
        direct_text_nodes = [node for node in container.contents 
                            if isinstance(node, str) and node.strip() and
                            not should_skip_text(str(node), item_id)]
        
        if direct_text_nodes:
            # Filter out already processed nodes
            direct_text_nodes = [node for node in direct_text_nodes 
                                if node not in processed_elements]
            
            if direct_text_nodes:
                # Filter and join valid text nodes
                valid_texts = []
                for node in direct_text_nodes:
                    node_text = str(node).strip()
                    if not should_skip_text(node_text, item_id):
                        valid_texts.append(node_text)
                        
                combined_text = " ".join(valid_texts)
                
                if combined_text.strip() and not should_skip_text(combined_text, item_id):
                    segments.append((direct_text_nodes[0], None, combined_text))
                    processed_elements.update(direct_text_nodes)
                    
                    # Thread-safe increment of statistics
                    with self.lock:
                        self.total_segments += 1
                        self.total_chars += len(combined_text)
    
    # Process remaining text nodes that weren't part of a paragraph or container
    for element in soup.find_all(string=True):
        if element in processed_elements:
            continue
            
        parent = element.parent
        
        # Skip non-translatable elements
        if parent.name in self.SKIP_TAGS:
            continue
        
        # Skip empty text, whitespace-only text, or special content
        text = str(element).strip()
        if not text or should_skip_text(text, item_id):
            continue
        
        # Add to translatable segments
        segments.append((element, None, text))
        
        # Thread-safe increment of statistics
        with self.lock:
            self.total_segments += 1
            self.total_chars += len(text)
    
    # Process translatable attributes
    for tag in soup.find_all():
        for attr in self.TRANSLATABLE_ATTRS:
            if tag.has_attr(attr) and tag[attr].strip():
                attr_text = tag[attr].strip()
                if not should_skip_text(attr_text, item_id):
                    segments.append((tag, attr, attr_text))
                    
                    # Thread-safe increment of statistics
                    with self.lock:
                        self.total_segments += 1
                        self.total_chars += len(attr_text)
    
    return segments
