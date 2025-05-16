#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test script for EPUB Translator.
This script demonstrates basic functionality without requiring an actual EPUB file.
"""

import sys
import os
import logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from epub_translator.config import Config
from epub_translator.translator import DeepseekTranslator
from epub_translator.term_extractor import TerminologyExtractor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("epub_translator_test")

def test_terminology_protection():
    """Test terminology extraction and protection."""
    
    print("\n=== Testing Terminology Protection ===\n")
    
    # Sample text with technical terms
    sample_text = """
    Introduction to Machine Learning
    
    Machine learning is a subset of artificial intelligence that provides systems the ability to 
    automatically learn and improve from experience without being explicitly programmed. 
    Deep learning is a part of machine learning based on neural networks.
    
    TensorFlow and PyTorch are popular frameworks for developing machine learning models, 
    especially neural networks. Both frameworks support GPU acceleration.
    
    In this book, we'll explore how to build neural networks using Python and these frameworks.
    We'll also cover natural language processing techniques using transformer models.
    """
    
    # Initialize terminology extractor with custom terminology
    term_extractor = TerminologyExtractor(
        min_frequency=2,
        custom_terminology_file="sample_terminology.csv"
    )
    
    # Extract terminology from the sample text
    extracted_terms = term_extractor.extract_terminology(sample_text)
    
    print("Extracted terminology:")
    for term, freq in sorted(extracted_terms.items(), key=lambda x: x[1], reverse=True):
        if freq >= 2:
            print(f"  {term}: {freq}")
    
    # Protect terminology in the text
    protected_text = term_extractor.protect_terminology(sample_text)
    
    print("\nProtected text:")
    print(protected_text)
    
    return term_extractor, protected_text

def test_translation(term_extractor, protected_text, api_key=None):
    """Test translation with protected terminology."""
    
    if not api_key:
        print("\n=== Skipping Translation Test (No API Key) ===\n")
        print("To test translation, run with API key: python test_translation.py YOUR_API_KEY")
        return
    
    print("\n=== Testing Translation ===\n")
    
    # Initialize translator
    translator = DeepseekTranslator(
        api_key=api_key,
        source_lang="en",
        target_lang="zh-CN"
    )
    
    # Translate the protected text
    translated_text = translator.translate_text(protected_text)
    
    # Restore terminology in the translated text
    final_text = term_extractor.restore_terminology(translated_text)
    
    print("Translated text with preserved terminology:")
    print(final_text)

def main():
    """Main function."""
    
    # Get API key from command line argument
    api_key = None
    if len(sys.argv) > 1:
        api_key = sys.argv[1]
    
    # Test terminology protection
    term_extractor, protected_text = test_terminology_protection()
    
    # Test translation if API key provided
    test_translation(term_extractor, protected_text, api_key)
    
    print("\n=== Testing Complete ===")

if __name__ == "__main__":
    main()
