#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Simplified Terminology Extractor for EPUB Translator.
Focuses on extracting technical terminology directly from book structure:
1. Extracts table of contents (TOC) and index
2. Uses DeepSeek to analyze and identify technical terms to preserve during translation
"""

import os
import re
import csv
import json
import time
import logging
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup

logger = logging.getLogger("epub_translator.term_extractor")

class TerminologyExtractor:
    """Extract and manage domain-specific terminology using book structure and DeepSeek AI."""
    
    def __init__(self, translator=None, workdir=None, use_deepseek=True):
        """Initialize the terminology extractor.
        
        Args:
            translator: Translator instance for DeepSeek API calls
            workdir: Working directory for storing terminology files
            use_deepseek: Whether to use DeepSeek for terminology analysis
        """
        self.translator = translator
        self.workdir = workdir
        self.use_deepseek = use_deepseek
        
        # Final terminology list
        self.final_terminology = {}
        
        # Don't create terminology directory in phase 1
        # Terminology directory will be created on-demand in phase 2 when needed
    
    def extract_terminology(self, text_content=None):
        """Extract terminology directly using DeepSeek analysis.
        
        Args:
            text_content: Not used, just kept for API compatibility
            
        Returns:
            Dictionary with extracted terminology
        """
        return self.enhance_terminology_with_deepseek()
    
    def enhance_terminology_with_deepseek(self):
        """Use DeepSeek to analyze book structure and identify terminology.
        
        Returns:
            Dictionary of final terminology
        """
        if not self.translator or not self.use_deepseek:
            logger.warning("DeepSeek terminology extraction skipped (not enabled or no translator available)")
            return {}
            
        # Check for existing terminology to avoid duplicate work
        if self.workdir:
            # Check if final terminology file exists (without relying on completion marker)
            final_terminology_file = os.path.join(self.workdir, "terminology", "final_terminology.json")
            
            if os.path.exists(final_terminology_file):
                try:
                    with open(final_terminology_file, 'r', encoding='utf-8') as f:
                        self.final_terminology = json.load(f)
                    logger.info(f"Loaded existing terminology from {final_terminology_file}")
                    return self.final_terminology
                except Exception as e:
                    logger.warning(f"Could not load existing terminology: {e}")
        
        logger.info("Starting DeepSeek terminology extraction from book structure")
        
        # Check if API is enabled in the translator
        if hasattr(self.translator, 'api_enabled') and not self.translator.api_enabled:
            logger.warning("Skipping DeepSeek terminology extraction - API not enabled yet")
            return {}
        
        # Prepare data with TOC and index only
        book_context = self._extract_book_structure()
        
        # Create system message for DeepSeek
        system_message = self._get_terminology_system_message()
        
        try:
            # Send to DeepSeek for analysis
            logger.info("Sending book structure to DeepSeek for terminology analysis")
            if hasattr(self.translator, 'translate_with_system_message'):
                response = self.translator.translate_with_system_message(book_context, system_message)
            else:
                logger.warning("Translator doesn't support system messages, using standard translation")
                response = self.translator.translate_text(book_context)
            
            # Process the response
            final_terminology = self._process_deepseek_response(response)
            
            # Save results
            if self.workdir:
                self._save_final_terminology(final_terminology)
                
                # Skip creating the completion marker file
                # (This is required by the user)
            
            self.final_terminology = final_terminology
            logger.info(f"DeepSeek terminology analysis complete - identified {len(final_terminology)} terms")
            return final_terminology
            
        except Exception as e:
            logger.error(f"Error during DeepSeek terminology analysis: {e}")
            return {}
    
    def _extract_book_structure(self):
        """Extract book structure (TOC and index) to provide context to DeepSeek.
        
        Returns:
            String containing the book structure data
        """
        result = "I'm analyzing a technical e-book and need to identify terminology that should be preserved (not translated) during translation. Please help me analyze the book structure below.\n\n"
        
        # Extract and include table of contents
        toc_content = self._extract_toc_content()
        if toc_content:
            result += "=== TABLE OF CONTENTS ===\n\n" + toc_content + "\n\n"
        else:
            result += "=== TABLE OF CONTENTS ===\n\nNot available\n\n"
        
        # Extract and include index
        index_content = self._extract_index_content()
        if index_content:
            result += "=== BOOK INDEX ===\n\n" + index_content + "\n\n"
        else:
            result += "=== BOOK INDEX ===\n\nNot available\n\n"
        
        # Add request for analysis
        result += "Based on this book structure, please identify technical terms, proper names, programming concepts, and other domain-specific terminology that should NOT be translated. Consider terms from the table of contents and index, but also infer other related terms that might appear in the book."
        
        return result
    
    def _extract_toc_content(self):
        """Extract table of contents from the working directory.
        
        Returns:
            String containing the TOC or empty string if not found
        """
        if not self.workdir:
            return ""
            
        # Look for TOC in common locations
        possible_paths = [
            os.path.join(self.workdir, "html_items", "toc", "original.txt"),
            os.path.join(self.workdir, "html_items", "contents", "original.txt")
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    logger.info(f"Extracted TOC from {path}")
                    return content
                except Exception as e:
                    logger.error(f"Error reading TOC file {path}: {e}")
        
        logger.warning("TOC content not found in working directory")
        return ""
    
    def _extract_index_content(self):
        """Extract index content from the working directory.
        
        Returns:
            String containing the index or empty string if not found
        """
        if not self.workdir:
            return ""
            
        # Look for index in common locations
        possible_paths = [
            os.path.join(self.workdir, "html_items", "index", "original.txt"),
            os.path.join(self.workdir, "html_items", "index", "original.html")
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Process HTML if needed
                    if path.endswith('.html'):
                        try:
                            soup = BeautifulSoup(content, 'html.parser')
                            content = soup.get_text()
                        except Exception:
                            # Simple HTML stripping as fallback
                            content = re.sub(r'<[^>]+>', ' ', content)
                    
                    # Limit size if needed
                    if len(content) > 8000:
                        content = content[:8000] + "...[content truncated]"
                        
                    logger.info(f"Extracted index from {path}")
                    return content
                except Exception as e:
                    logger.error(f"Error reading index file {path}: {e}")
        
        logger.warning("Index content not found in working directory")
        return ""
    
    def _get_terminology_system_message(self):
        """Get the system message for DeepSeek terminology analysis.
        
        Returns:
            String containing the system message
        """
        return (
            "You are an expert terminology analyst specializing in technical and professional content. "
            "I will provide you with a book's table of contents and index (if available). "
            "Your task is to analyze this structure and identify domain-specific terminology "
            "that should be preserved (not translated) during translation."
            "\n\nYou should:"
            "\n1. Analyze the book structure to understand the domain and subject matter"
            "\n2. Identify technical terms, specialized vocabulary, and proper nouns"
            "\n3. Include both terms explicitly mentioned and those likely to appear based on context"
            "\n4. Consider programming languages, frameworks, tools, design patterns, and technical concepts"
            "\n\nProvide your response as a JSON object with the following structure:"
            "\n{"
            "\n  \"domain_analysis\": \"Your analysis of the book's domain and subject matter\","
            "\n  \"terms\": ["
            "\n    {\"term\": \"term1\", \"preserve\": true, \"reason\": \"Why this should be preserved\"},"
            "\n    {\"term\": \"term2\", \"preserve\": true, \"reason\": \"Why this should be preserved\"},"
            "\n    ..."
            "\n  ]"
            "\n}"
            "\n\nBe comprehensive in your analysis, as missed terms might be incorrectly translated."
        )
    
    def _process_deepseek_response(self, response):
        """Process DeepSeek's response to extract final terminology.
        
        Args:
            response: Response from DeepSeek
            
        Returns:
            Dictionary of final terminology
        """
        final_terminology = {}
        
        try:
            # Try to extract JSON from the response
            json_match = re.search(r'({.*})', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                result = json.loads(json_str)
            else:
                result = json.loads(response)
            
            # Process the terms from the result
            if "terms" in result:
                for term_data in result["terms"]:
                    term = term_data.get("term", "").strip()
                    if not term or len(term) < 2:
                        continue
                    
                    preserve = term_data.get("preserve", False)
                    reason = term_data.get("reason", "")
                    
                    # Add to final terminology
                    final_terminology[term] = {
                        "preserve": preserve,
                        "reason": reason
                    }
                    
                # Include domain analysis if available
                if "domain_analysis" in result and result["domain_analysis"]:
                    logger.info(f"Domain analysis: {result['domain_analysis']}")
                    
        except json.JSONDecodeError:
            logger.error("Failed to parse DeepSeek response as JSON")
            # Fall back to regex-based extraction
            terms = re.findall(r'term[:\s]+"([^"]+)"', response)
            for term in terms:
                term = term.strip()
                if term and len(term) >= 2:
                    # Add the term to final terminology, assuming it should be preserved
                    final_terminology[term] = {
                        "preserve": True,
                        "reason": "Extracted from DeepSeek response"
                    }
        except Exception as e:
            logger.error(f"Error processing DeepSeek response: {e}")
            return {}
        
        return final_terminology
    
    def _save_final_terminology(self, final_terminology):
        """Save final terminology to CSV and JSON files.
        
        Args:
            final_terminology: Dictionary of final terminology
        """
        if not self.workdir:
            return
            
        try:
            term_dir = os.path.join(self.workdir, "terminology")
            os.makedirs(term_dir, exist_ok=True)
            
            # Save as CSV
            final_file = os.path.join(term_dir, "final_terminology.csv")
            with open(final_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Term', 'Preserve', 'Reason'])
                
                for term, info in sorted(final_terminology.items()):
                    if info.get('preserve', True):  # Default to preserve
                        writer.writerow([
                            term,
                            True,
                            info.get('reason', '')
                        ])
            
            # Save as JSON
            with open(os.path.join(term_dir, "final_terminology.json"), 'w', encoding='utf-8') as f:
                json.dump(final_terminology, f, ensure_ascii=False, indent=2)
            
            # Save a simple terms list (one per line)
            terms_file = os.path.join(term_dir, "terms.txt")
            with open(terms_file, 'w', encoding='utf-8') as f:
                for term, info in sorted(final_terminology.items()):
                    if info.get('preserve', True):
                        f.write(f"{term}\n")
                
            logger.info(f"Saved {len(final_terminology)} terms to {final_file}")
            
        except Exception as e:
            logger.error(f"Error saving final terminology: {e}")
