#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Terminology Extractor for EPUB Translator.
Identifies domain-specific terminology and protects it during translation.
Simple implementation without external NLP dependencies.
"""

import os
import re
import csv
import logging
import string
import collections

logger = logging.getLogger("epub_translator.term_extractor")

# Simple stopwords list (most common English words)
STOPWORDS = {
    'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 
    'yours', 'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', 
    'her', 'hers', 'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 
    'theirs', 'themselves', 'what', 'which', 'who', 'whom', 'this', 'that', 
    'these', 'those', 'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 
    'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'a', 'an', 
    'the', 'and', 'but', 'if', 'or', 'because', 'as', 'until', 'while', 'of', 
    'at', 'by', 'for', 'with', 'about', 'against', 'between', 'into', 'through', 
    'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down', 
    'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further', 'then', 
    'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'any', 
    'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 
    'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very'
}

def simple_sentence_tokenize(text):
    """Simple sentence tokenizer using regex."""
    # Split on sentence-ending punctuation followed by whitespace or end of string
    sentences = re.split(r'[.!?](?:\s|\Z)', text)
    return [s.strip() for s in sentences if s.strip()]

def simple_word_tokenize(text):
    """Simple word tokenizer using regex."""
    # Find all words (sequences of letters, numbers, and some punctuation)
    return re.findall(r'\b[\w\-\']+\b', text)

def generate_ngrams(tokens, n):
    """Generate n-grams from a list of tokens."""
    return [' '.join(tokens[i:i+n]) for i in range(len(tokens)-n+1)]

class TerminologyExtractor:
    """Extracts and manages domain-specific terminology."""
    
    # Special markers for protecting terms during translation
    PROTECT_START = "[[TERM:"
    PROTECT_END = "]]"
    
    def __init__(self, min_frequency=3, max_term_length=5, ignore_case=True, custom_terminology_file=None, 
                 use_deepseek=True, translator=None):
        """Initialize terminology extractor.
        
        Args:
            min_frequency: Minimum frequency for automatic term extraction
            max_term_length: Maximum number of words in a term
            ignore_case: Whether to ignore case when matching terms
            custom_terminology_file: Path to CSV file with custom terminology
            use_deepseek: Whether to use Deepseek for terminology extraction
            translator: Translator instance for terminology translation
        """
        self.min_frequency = min_frequency
        self.max_term_length = max_term_length
        self.ignore_case = ignore_case
        self.terminology = {}  # {term: frequency}
        self.custom_terminology = {}  # {term: translation}
        self.use_deepseek = use_deepseek
        self.translator = translator
        
        # Load custom terminology if provided
        if custom_terminology_file:
            self.load_terminology(custom_terminology_file)
    
    def load_terminology(self, terminology_file):
        """Load custom terminology from a file.
        
        Args:
            terminology_file: Path to file with terminology (one term per line, or CSV)
        """
        if not os.path.exists(terminology_file):
            logger.warning(f"Terminology file not found: {terminology_file}")
            return
        
        try:
            terms_loaded = 0
            with open(terminology_file, 'r', encoding='utf-8') as f:
                # Try to determine format (CSV or simple list)
                sample = f.read(1024)
                f.seek(0)  # Reset file pointer
                
                if ',' in sample:  # Likely CSV format
                    reader = csv.reader(f)
                    for row in reader:
                        if row and len(row) >= 1:
                            term = row[0].strip()
                            if term and not term.startswith('#'):  # Skip empty lines and comments
                                # Add term with itself as translation (preserve it)
                                self.custom_terminology[term] = term
                                # Add to general terminology with high frequency
                                self.terminology[term] = 999  # High frequency to ensure it's used
                                terms_loaded += 1
                else:  # Simple list format (one term per line)
                    for line in f:
                        term = line.strip()
                        if term and not term.startswith('#'):  # Skip empty lines and comments
                            # Add term with itself as translation (preserve it)
                            self.custom_terminology[term] = term
                            # Add to general terminology with high frequency
                            self.terminology[term] = 999
                            terms_loaded += 1
            
            logger.info(f"Loaded {terms_loaded} terms from {terminology_file}")
        except Exception as e:
            logger.error(f"Error loading terminology file: {e}")
    
    def extract_terminology(self, text, is_toc=False):
        """Extract domain-specific terminology from text.
        
        Args:
            text: Text to extract terminology from
            is_toc: Whether the text is from a table of contents
        
        Returns:
            Dictionary of extracted terms and their frequencies
        """
        # Check if we should use DeepSeek for smart extraction
        if self.use_deepseek and self.translator:
            if is_toc:
                logger.info("Using DeepSeek to extract domain terminology from TOC...")
                return self.extract_terminology_with_deepseek(text, is_toc=True)
            elif len(text) < 100000:  # For manageable text size
                logger.info("Using DeepSeek to extract domain terminology...")
                return self.extract_terminology_with_deepseek(text)
        
        # Fall back to frequency-based extraction for very large texts
        # or when DeepSeek is not available
        logger.info("Extracting terminology using frequency analysis...")
        
        # Preprocess text
        if self.ignore_case:
            text = text.lower()
        
        # Tokenize text into sentences
        sentences = simple_sentence_tokenize(text)
        
        # Extract candidate terms
        term_candidates = collections.defaultdict(int)
        
        for sentence in sentences:
            # Tokenize sentence
            tokens = simple_word_tokenize(sentence)
            
            # Filter tokens
            tokens = [t for t in tokens if self._is_valid_token(t)]
            
            # Extract n-grams (1 to max_term_length)
            for n in range(1, min(self.max_term_length + 1, len(tokens) + 1)):
                for term in generate_ngrams(tokens, n):
                    term_candidates[term] += 1
        
        # Filter terms by frequency
        extracted_terms = {
            term: freq for term, freq in term_candidates.items()
            if freq >= self.min_frequency
        }
        
        # Add to terminology dictionary
        self.terminology.update(extracted_terms)
        
        logger.info(f"Extracted {len(extracted_terms)} terms through frequency analysis")
        
        # Process the terms (preserve them in their original form)
        if extracted_terms:
            self.process_terminology(extracted_terms.keys())
        
        return extracted_terms
    
    def extract_terminology_with_deepseek(self, text, is_toc=False):
        """Extract domain-specific terminology using DeepSeek's understanding.
        
        Args:
            text: Text to extract terminology from
            is_toc: Whether the text is from table of contents
        
        Returns:
            Dictionary of extracted terms and their frequencies
        """
        if not self.translator:
            logger.warning("No translator available for DeepSeek terminology extraction")
            return {}
        
        # Create a system message for terminology extraction from TOC/content
        if is_toc:
            system_message = (
                "You are an expert terminology extractor that specializes in identifying domain-specific"
                " technical terms from book tables of contents and chapter titles. "
                "Analyze the provided table of contents and extract all domain-specific technical terminology. "
                "Focus on identifying:"
                "\n1. Professional/technical terms specific to the book's domain"
                "\n2. Specialized jargon and technical nomenclature"
                "\n3. Important proper nouns that should not be translated"
                "\n4. Technology names, frameworks, standards, and protocols"
                "\n5. Scientific concepts and methodologies mentioned in chapter titles"
                "\nReturn ONLY a list of the extracted terms (one term per line). Do not include explanations, "
                "definitions, or any other text beyond the extracted terms."
            )
        else:
            system_message = (
                "You are an expert terminology extractor that specializes in identifying domain-specific"
                " technical terms from technical content. "
                "Analyze the provided text and extract all domain-specific technical terminology. "
                "Focus on identifying:"
                "\n1. Professional/technical terms"
                "\n2. Specialized jargon and nomenclature"
                "\n3. Important proper nouns"
                "\n4. Technology names, frameworks, standards, and protocols"
                "\n5. Scientific concepts and methodologies"
                "\nReturn ONLY a list of the extracted terms (one term per line). Do not include explanations, "
                "definitions, or any other text beyond the extracted terms."
            )
        
        # Truncate text if it's too long
        max_length = 10000 if is_toc else 20000
        if len(text) > max_length:
            logger.info(f"Truncating text to {max_length} characters for terminology extraction")
            # For TOC, take the beginning which contains the most important terms
            if is_toc:
                sample_text = text[:max_length]
            else:
                # For full text, take samples from beginning, middle and end
                third = max_length // 3
                sample_text = text[:third] + "\n\n" + text[len(text)//2-third//2:len(text)//2+third//2] + "\n\n" + text[-third:]
        else:
            sample_text = text
        
        # Extract terminology using Deepseek
        try:
            logger.info("Sending terminology extraction request to DeepSeek...")
            response = self._translate_batch_with_deepseek(sample_text, system_message)
            
            # Process the response - expect one term per line
            terms = [line.strip() for line in response.split('\n') if line.strip()]
            
            # Filter out very short terms and non-terminology
            terms = [term for term in terms if len(term) >= 3 and not term.lower() in STOPWORDS]
            
            # Add terms to terminology dictionary with high frequency to ensure they're used
            extracted_terms = {term: 100 for term in terms}
            
            # Update the global terminology dictionary
            self.terminology.update(extracted_terms)
            
            logger.info(f"DeepSeek identified {len(extracted_terms)} terminology items")
            
            # Process the terms (preserve them in their original form)
            if extracted_terms:
                self.process_terminology(extracted_terms.keys())
            
            return extracted_terms
            
        except Exception as e:
            logger.error(f"Error using DeepSeek for terminology extraction: {e}")
            logger.info("Falling back to frequency-based extraction")
            return self.extract_terminology(text, is_toc=False)
    
    def process_terminology(self, terms):
        """Process terminology - preserve terms without translation.
        
        Args:
            terms: List or set of terms to process
        
        Returns:
            Dictionary of preserved terms {term: term}
        """
        if not terms:
            return {}
        
        logger.info(f"Processing {len(terms)} terminology items (preserving original)")
        
        # Process all terms
        for term in terms:
            # Add the term with itself as the "translation" (preserving it)
            self.custom_terminology[term] = term
            
        logger.info(f"Preserved {len(self.custom_terminology)} terms in their original form")
        return self.custom_terminology
    
    def _translate_batch_with_deepseek(self, text, system_message):
        """Send batch of text to Deepseek for translation with custom system message.
        
        Args:
            text: Text to translate
            system_message: Custom system message for Deepseek
            
        Returns:
            Translated text
        """
        try:
            # Try to use translator's custom method for system message translation if available
            if hasattr(self.translator, 'translate_with_system_message'):
                return self.translator.translate_with_system_message(text, system_message)
            
            # Fallback to regular translation
            return self.translator.translate_text(text)
        except Exception as e:
            logger.error(f"Error translating terminology: {e}")
            return ""
    
    def _is_valid_token(self, token):
        """Check if a token is valid for terminology extraction.
        
        Args:
            token: Token to check
        
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
        if token.lower() in STOPWORDS:
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
