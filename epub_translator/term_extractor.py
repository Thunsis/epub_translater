#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Terminology Extractor for EPUB Translator.
Identifies domain-specific terminology and protects it during translation.
"""

import os
import re
import csv
import logging
import string
import collections
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.util import ngrams
from nltk.corpus import stopwords
import nltk

logger = logging.getLogger("epub_translator.term_extractor")

class TerminologyExtractor:
    """Extracts and manages domain-specific terminology."""
    
    # Special markers for protecting terms during translation
    PROTECT_START = "[[TERM:"
    PROTECT_END = "]]"
    
    def __init__(self, min_frequency=3, max_term_length=5, ignore_case=True, custom_terminology_file=None):
        """Initialize terminology extractor.
        
        Args:
            min_frequency: Minimum frequency for automatic term extraction
            max_term_length: Maximum number of words in a term
            ignore_case: Whether to ignore case when matching terms
            custom_terminology_file: Path to CSV file with custom terminology
        """
        self.min_frequency = min_frequency
        self.max_term_length = max_term_length
        self.ignore_case = ignore_case
        self.terminology = {}  # {term: frequency}
        self.custom_terminology = {}  # {term: translation}
        
        # Download NLTK resources if not already available
        try:
            self._ensure_nltk_resources()
        except Exception as e:
            logger.warning(f"Could not download NLTK resources: {e}")
        
        # Load custom terminology if provided
        if custom_terminology_file:
            self.load_terminology(custom_terminology_file)
    
    def _ensure_nltk_resources(self):
        """Ensure required NLTK resources are available."""
        resources = [
            ('tokenizers/punkt', 'punkt'),
            ('corpora/stopwords', 'stopwords')
        ]
        
        for resource_path, resource_name in resources:
            try:
                nltk.data.find(resource_path)
            except LookupError:
                logger.info(f"Downloading NLTK resource: {resource_name}")
                nltk.download(resource_name, quiet=True)
    
    def load_terminology(self, terminology_file):
        """Load custom terminology from a CSV file.
        
        Args:
            terminology_file: Path to CSV file with terminology (format: term,translation)
        """
        if not os.path.exists(terminology_file):
            logger.warning(f"Terminology file not found: {terminology_file}")
            return
        
        try:
            with open(terminology_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 1:
                        term = row[0].strip()
                        translation = row[1].strip() if len(row) > 1 else term
                        
                        # Add to custom terminology
                        self.custom_terminology[term] = translation
                        
                        # Also add to general terminology with high frequency
                        self.terminology[term] = 999  # High frequency to ensure it's used
            
            logger.info(f"Loaded {len(self.custom_terminology)} terms from {terminology_file}")
        except Exception as e:
            logger.error(f"Error loading terminology file: {e}")
    
    def extract_terminology(self, text):
        """Extract domain-specific terminology from text.
        
        Args:
            text: Text to extract terminology from
        
        Returns:
            Dictionary of extracted terms and their frequencies
        """
        logger.info("Extracting terminology from text...")
        
        # Preprocess text
        if self.ignore_case:
            text = text.lower()
        
        # Tokenize text into sentences
        try:
            sentences = sent_tokenize(text)
        except:
            # Fallback if NLTK fails
            sentences = re.split(r'[.!?]+', text)
        
        # Get stopwords
        try:
            stop_words = set(stopwords.words('english'))
        except:
            # Fallback if NLTK stopwords not available
            stop_words = set([
                'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 
                "you're", "you've", "you'll", "you'd", 'your', 'yours', 'yourself', 
                'yourselves', 'he', 'him', 'his', 'himself', 'she', "she's", 'her', 
                'hers', 'herself', 'it', "it's", 'its', 'itself', 'they', 'them', 
                'their', 'theirs', 'themselves', 'what', 'which', 'who', 'whom', 
                'this', 'that', "that'll", 'these', 'those', 'am', 'is', 'are', 'was',
                'were', 'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do', 
                'does', 'did', 'doing', 'a', 'an', 'the', 'and', 'but', 'if', 'or', 
                'because', 'as', 'until', 'while', 'of', 'at', 'by', 'for', 'with', 
                'about', 'against', 'between', 'into', 'through', 'during', 'before', 
                'after', 'above', 'below', 'to', 'from', 'up', 'down', 'in', 'out', 
                'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 
                'here', 'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both',
                'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 
                'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 
                'can', 'will', 'just', 'don', "don't", 'should', "should've", 'now', 
                'd', 'll', 'm', 'o', 're', 've', 'y'
            ])
        
        # Extract candidate terms
        term_candidates = collections.defaultdict(int)
        
        for sentence in sentences:
            # Tokenize sentence
            try:
                tokens = word_tokenize(sentence)
            except:
                # Fallback if NLTK fails
                tokens = re.findall(r'\b\w+\b', sentence)
            
            # Filter tokens
            tokens = [t for t in tokens if self._is_valid_token(t, stop_words)]
            
            # Extract n-grams (1 to max_term_length)
            for n in range(1, min(self.max_term_length + 1, len(tokens) + 1)):
                for n_gram in ngrams(tokens, n):
                    term = ' '.join(n_gram)
                    term_candidates[term] += 1
        
        # Filter terms by frequency
        extracted_terms = {
            term: freq for term, freq in term_candidates.items()
            if freq >= self.min_frequency
        }
        
        # Add to terminology dictionary
        self.terminology.update(extracted_terms)
        
        logger.info(f"Extracted {len(extracted_terms)} terms")
        return extracted_terms
    
    def _is_valid_token(self, token, stop_words):
        """Check if a token is valid for terminology extraction.
        
        Args:
            token: Token to check
            stop_words: Set of stopwords to filter out
        
        Returns:
            True if token is valid, False otherwise
        """
        # Filter out very short tokens
        if len(token) < 3:
            return False
        
        # Filter out tokens that are just punctuation
        if all(c in string.punctuation for c in token):
            return False
        
        # Filter out tokens that are mainly digits
        if sum(c.isdigit() for c in token) / len(token) > 0.5:
            return False
        
        # Filter out stopwords
        if token.lower() in stop_words:
            return False
        
        return True
    
    def protect_terminology(self, text):
        """Protect terminology in text from translation.
        
        Args:
            text: Text to protect terminology in
        
        Returns:
            Text with protected terminology
        """
        if not self.terminology and not self.custom_terminology:
            return text
        
        # Sort terms by length (descending) to handle longer terms first
        # This prevents issues with overlapping terms
        all_terms = list(set(list(self.terminology.keys()) + list(self.custom_terminology.keys())))
        all_terms.sort(key=len, reverse=True)
        
        protected_text = text
        
        for term in all_terms:
            # Skip very short terms
            if len(term) < 3:
                continue
            
            # Create pattern based on case sensitivity setting
            if self.ignore_case:
                pattern = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
            else:
                pattern = re.compile(r'\b' + re.escape(term) + r'\b')
            
            # Replace term with protected version
            protected_term = f"{self.PROTECT_START}{term}{self.PROTECT_END}"
            protected_text = pattern.sub(protected_term, protected_text)
        
        return protected_text
    
    def restore_terminology(self, text):
        """Restore protected terminology in translated text.
        
        Args:
            text: Text with protected terminology
        
        Returns:
            Text with restored terminology
        """
        # Pattern to find protected terms
        pattern = re.compile(f"{re.escape(self.PROTECT_START)}(.*?){re.escape(self.PROTECT_END)}")
        
        # Replace protected terms with original or custom translation
        def replace_term(match):
            term = match.group(1)
            # If there's a custom translation, use it
            if term in self.custom_terminology:
                return self.custom_terminology[term]
            # Otherwise keep the original term
            return term
        
        restored_text = pattern.sub(replace_term, text)
        return restored_text
    
    def save_terminology(self, output_file):
        """Save extracted terminology to a CSV file.
        
        Args:
            output_file: Path to output CSV file
        """
        try:
            with open(output_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Term', 'Frequency', 'Custom Translation'])
                
                for term, freq in sorted(self.terminology.items(), key=lambda x: x[1], reverse=True):
                    custom_trans = self.custom_terminology.get(term, '')
                    writer.writerow([term, freq, custom_trans])
            
            logger.info(f"Saved {len(self.terminology)} terms to {output_file}")
        except Exception as e:
            logger.error(f"Error saving terminology to {output_file}: {e}")
