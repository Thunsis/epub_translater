#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Paragraph Divider for EPUB Translator.
Provides paragraph-aware text chunking to ensure translation batches respect paragraph boundaries.
"""

import re
import logging
import nltk
from typing import List, Tuple

logger = logging.getLogger("epub_translator.paragraph_divider")

# Try to ensure NLTK data is available
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    logger.warning("NLTK punkt tokenizer not found, falling back to regex-based sentence splitting")

class TextDivider:
    """Split text into paragraphs and create batches that respect paragraph boundaries."""
    
    def __init__(self):
        """Initialize the text divider with required resources."""
        # Check if NLTK data is available for better sentence tokenization
        self.use_nltk = False
        try:
            nltk.data.find('tokenizers/punkt')
            self.use_nltk = True
        except LookupError:
            logger.warning("NLTK punkt tokenizer not available, using regex-based sentence splitting")
    
    def split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences using the best available method.
        
        Args:
            text: Input text to split into sentences
            
        Returns:
            List of sentences
        """
        if not text or not text.strip():
            return []
            
        if self.use_nltk:
            try:
                return nltk.sent_tokenize(text)
            except Exception as e:
                logger.warning(f"NLTK sentence tokenization failed: {e}, falling back to regex")
        
        # Fallback: regex-based sentence splitting
        # This simple pattern splits on sentence-ending punctuation followed by space or end of string
        sentences = re.split(r'([.!?])\s+', text)
        
        # The split pattern creates separate groups for punctuation, so we need to join them back
        result = []
        i = 0
        while i < len(sentences):
            if i + 1 < len(sentences) and sentences[i+1] in ['.', '!', '?']:
                result.append(sentences[i] + sentences[i+1])
                i += 2
            else:
                result.append(sentences[i])
                i += 1
                
        # Filter out empty sentences
        return [s for s in result if s.strip()]
    
    def detect_paragraphs(self, text: str) -> List[str]:
        """Detect paragraphs in text based on line breaks and other markers.
        
        Args:
            text: Input text to split into paragraphs
            
        Returns:
            List of paragraphs
        """
        if not text or not text.strip():
            return []
            
        # Split on double line breaks, which typically indicate paragraphs
        paragraphs = re.split(r'\n\s*\n', text)
        
        # Filter out empty paragraphs
        return [p.strip() for p in paragraphs if p.strip()]
    
    def merge_sentences_into_paragraphs(self, sentences: List[str], max_length: int = 1000) -> List[str]:
        """Merge sentences into paragraph-like chunks without exceeding max_length.
        
        Args:
            sentences: List of sentences to merge
            max_length: Maximum length of merged chunk
            
        Returns:
            List of merged paragraph chunks
        """
        if not sentences:
            return []
            
        paragraphs = []
        current_paragraph = ""
        
        for sentence in sentences:
            # If adding this sentence would exceed max_length, start a new paragraph
            if len(current_paragraph) + len(sentence) > max_length and current_paragraph:
                paragraphs.append(current_paragraph)
                current_paragraph = sentence
            else:
                # Add space between sentences if needed
                if current_paragraph and not current_paragraph.endswith((' ', '\n', '\t')):
                    current_paragraph += " "
                current_paragraph += sentence
        
        # Add the last paragraph if it's not empty
        if current_paragraph:
            paragraphs.append(current_paragraph)
        
        return paragraphs
    
    def split_long_segment(self, text: str, max_length: int = 5000) -> List[str]:
        """Split a very long text segment into smaller chunks that respect sentence boundaries.
        
        Args:
            text: Text to split
            max_length: Maximum length of split chunks
            
        Returns:
            List of text chunks
        """
        if len(text) <= max_length:
            return [text]
            
        # First try to split by paragraphs
        paragraphs = self.detect_paragraphs(text)
        if len(paragraphs) > 1:
            # Process each paragraph separately
            result = []
            for paragraph in paragraphs:
                if len(paragraph) > max_length:
                    # If paragraph is too long, split by sentences
                    sentences = self.split_into_sentences(paragraph)
                    result.extend(self.merge_sentences_into_paragraphs(sentences, max_length))
                else:
                    result.append(paragraph)
            return result
        
        # If no paragraphs found, split into sentences
        sentences = self.split_into_sentences(text)
        
        # Merge sentences into paragraphs
        return self.merge_sentences_into_paragraphs(sentences, max_length)
    
    def optimize_segments(self, segments, batch_size: int = 10, max_segment_length: int = 5000) -> List[Tuple]:
        """Optimize segments for translation by ensuring paragraph and sentence integrity.
        
        This method processes the raw extracted segments from the HTML to:
        1. Try to identify paragraph boundaries in longer text
        2. Split very long paragraphs into sentence-aware smaller chunks
        3. Group segments into batches that respect paragraph boundaries when possible
        
        Args:
            segments: List of (element, attribute, text) tuples
            batch_size: Target number of segments per batch
            max_segment_length: Maximum length of any single segment
            
        Returns:
            List of optimized (element, attribute, text) tuples
        """
        if not segments:
            return []
            
        optimized_segments = []
        
        # First, handle paragraphs and split any very long segments
        for element, attribute, text in segments:
            # Check if this segment might contain multiple paragraphs
            if '\n\n' in text or len(text) > max_segment_length:
                # Try to split by paragraphs first
                paragraphs = self.detect_paragraphs(text)
                
                # If we found multiple paragraphs, use those
                if len(paragraphs) > 1:
                    for paragraph in paragraphs:
                        # If paragraph is still too long, split it by sentences
                        if len(paragraph) > max_segment_length:
                            for chunk in self.split_long_segment(paragraph, max_segment_length):
                                optimized_segments.append((element, attribute, chunk))
                        else:
                            optimized_segments.append((element, attribute, paragraph))
                # Otherwise, fall back to sentence splitting for long text
                elif len(text) > max_segment_length:
                    chunks = self.split_long_segment(text, max_segment_length)
                    for chunk in chunks:
                        optimized_segments.append((element, attribute, chunk))
                else:
                    optimized_segments.append((element, attribute, text))
            else:
                # Keep shorter segments as-is
                optimized_segments.append((element, attribute, text))
        
        return optimized_segments
    
    def group_into_content_aware_batches(self, segments, batch_size: int = 10) -> List[List[Tuple]]:
        """Group segments into batches that respect paragraph boundaries when possible.
        
        Args:
            segments: List of (element, attribute, text) tuples
            batch_size: Target number of segments per batch
            
        Returns:
            List of batches, where each batch is a list of (element, attribute, text) tuples
        """
        # Handle empty input
        if not segments:
            return []
        
        # Simple approach that's safer: just keep logical paragraph chunks together
        # when possible while respecting batch size
        batches = []
        current_batch = []
        current_batch_size = 0
        i = 0
        
        while i < len(segments):
            # Each segment is (element, attribute, text)
            element, attribute, text = segments[i]
            
            # Skip segments with None text
            if text is None:
                i += 1
                continue
                
            # Start a new paragraph?
            is_new_paragraph = False
            
            # Check if it's a heading
            if text and text.strip() and re.match(r'^(Chapter|Section|Part|Appendix|Figure|Table|Note|Warning)\b', text.strip()):
                is_new_paragraph = True
            
            # Check if it's a very short line that might be a heading
            elif text and len(text.strip()) < 40 and not text.strip().endswith(('.', ',', ';', ':', '?', '!')):
                is_new_paragraph = True
            
            # If it's a new paragraph and would make the batch too big, start a new batch
            if is_new_paragraph and current_batch_size > 0 and current_batch_size + 1 > batch_size:
                batches.append(current_batch)
                current_batch = []
                current_batch_size = 0
            
            # Add this segment to the current batch
            current_batch.append((element, attribute, text))
            current_batch_size += 1
            
            # If we've reached batch size, start a new batch
            if current_batch_size >= batch_size:
                batches.append(current_batch)
                current_batch = []
                current_batch_size = 0
            
            i += 1
        
        # Add the last batch if it's not empty
        if current_batch:
            batches.append(current_batch)
        
        return batches
