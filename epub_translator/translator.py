#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Translator module for the EPUB Translator.
Handles communication with the Deepseek API for text translation.
Includes both synchronous and asynchronous implementations for optimal performance.
"""

import os
import json
import time
import logging
import re
from collections import deque
from tqdm import tqdm

# Import for synchronous implementation
import requests

# Imports for asynchronous implementation
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import List, Dict, Tuple, Optional, Union, Any

logger = logging.getLogger("epub_translator.translator")

class DeepseekTranslator:
    """Translator using the Deepseek API."""
    
    DEFAULT_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
    
    # Language mapping for Deepseek API
    LANGUAGE_MAP = {
        "auto": "auto",
        "en": "english",
        "zh-CN": "chinese",
        "zh-TW": "traditional chinese",
        "ja": "japanese",
        "ko": "korean",
        "fr": "french",
        "de": "german",
        "es": "spanish",
        "it": "italian",
        "pt": "portuguese",
        "ru": "russian",
        "ar": "arabic",
        "hi": "hindi",
    }
    
    def __init__(self, api_key, source_lang="en", target_lang="zh-CN", 
                 model="deepseek-chat", max_retries=3, timeout=30, rate_limit=10,
                 verify_ssl=True):
        """Initialize the Deepseek translator.
        
        Args:
            api_key: Deepseek API key
            source_lang: Source language code (default: en for English)
            target_lang: Target language code (default: zh-CN for Simplified Chinese)
            model: Deepseek model to use
            max_retries: Maximum number of retries for API calls
            timeout: Timeout for API calls in seconds
            rate_limit: Maximum requests per minute
            verify_ssl: Whether to verify SSL certificate (default: True)
        """
        self.api_key = api_key
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout
        self.rate_limit = rate_limit
        self.rate_limit_interval = 60 / rate_limit  # seconds between requests
        self.last_request_time = 0
        self.translation_cache = {}
        self.api_enabled = False  # Start with API disabled until files are prepared
        self.verify_ssl = verify_ssl
        
        # Ensure API key is provided
        if not api_key:
            logger.warning("No API key provided for Deepseek API")
        
        # Map language codes to Deepseek's expected format
        self.source_lang_name = self.LANGUAGE_MAP.get(source_lang, source_lang)
        self.target_lang_name = self.LANGUAGE_MAP.get(target_lang, target_lang)
        
        logger.info(f"Initialized Deepseek translator: {source_lang} → {target_lang}")
    
    def translate_text(self, text):
        """Translate a single text.
        
        Args:
            text: Text to translate
        
        Returns:
            Translated text
        """
        if not text.strip():
            return text
        
        # Check cache
        cache_key = (text, self.source_lang, self.target_lang)
        if cache_key in self.translation_cache:
            return self.translation_cache[cache_key]
        
        # Translate and cache
        result = self._translate_single_text(text)
        self.translation_cache[cache_key] = result
        return result
    
    def translate_batch(self, texts):
        """Translate a batch of texts.
        
        Args:
            texts: List of texts to translate
        
        Returns:
            List of translated texts
        """
        if not texts:
            return []
        
        # Filter out empty texts and prepare for translation
        translations = []
        texts_to_translate = []
        indices_to_translate = []
        
        for i, text in enumerate(texts):
            if not text.strip():
                translations.append(text)
            else:
                # Check cache
                cache_key = (text, self.source_lang, self.target_lang)
                if cache_key in self.translation_cache:
                    translations.append(self.translation_cache[cache_key])
                else:
                    texts_to_translate.append(text)
                    indices_to_translate.append(i)
                    # Add placeholder to keep array aligned
                    translations.append(None)
        
        # If all texts were in cache, return them
        if not texts_to_translate:
            return translations
        
        # Translate the batch
        batch_translations = self._translate_batch_texts(texts_to_translate)
        
        # Update translations list with results
        for idx, trans_idx in enumerate(indices_to_translate):
            if idx < len(batch_translations):
                translations[trans_idx] = batch_translations[idx]
                # Cache the translation
                cache_key = (texts_to_translate[idx], self.source_lang, self.target_lang)
                self.translation_cache[cache_key] = batch_translations[idx]
        
        return translations
    
    def _translate_single_text(self, text):
        """Translate a single text using Deepseek API.
        
        Args:
            text: Text to translate
        
        Returns:
            Translated text
        """
        # Construct system message with translation instructions
        system_message = self._get_system_message()
        
        # User message is the text to translate
        user_message = text
        
        # Make API request
        response = self._make_api_request([
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ])
        
        # Extract translation from response
        try:
            translation = response["choices"][0]["message"]["content"]
            return self._clean_translation(translation)
        except (KeyError, IndexError) as e:
            logger.error(f"Error extracting translation: {e}")
            logger.debug(f"Response: {response}")
            return text  # Return original text on error
    
    def _translate_batch_texts(self, texts):
        """Translate a batch of texts using Deepseek API.
        
        Args:
            texts: List of texts to translate
        
        Returns:
            List of translated texts
        """
        # For batches, we can optimize by sending all texts in one request
        # But need to ensure we can separate the responses
        
        # Construct system message with batch translation instructions
        system_message = self._get_system_message(is_batch=True)
        
        # Join texts with unique separators that are unlikely to appear in content
        separator = "-----TRANSLATE_SEPARATOR_" + str(int(time.time())) + "-----"
        joined_text = separator.join(texts)
        
        # Make API request
        response = self._make_api_request([
            {"role": "system", "content": system_message},
            {"role": "user", "content": joined_text}
        ])
        
        # Extract and split translations
        try:
            translation = response["choices"][0]["message"]["content"]
            # Split by the same separator
            translations = translation.split(separator)
            
            # Make sure we have the right number of translations
            if len(translations) != len(texts):
                logger.warning(f"Expected {len(texts)} translations, got {len(translations)}")
                # If we don't have enough translations, fill with original texts
                while len(translations) < len(texts):
                    translations.append(texts[len(translations)])
                # If we have too many translations, truncate
                translations = translations[:len(texts)]
            
            return [self._clean_translation(t) for t in translations]
            
        except (KeyError, IndexError) as e:
            logger.error(f"Error extracting translations: {e}")
            logger.debug(f"Response: {response}")
            return texts  # Return original texts on error
    
    def _get_system_message(self, is_batch=False):
        """Get system message for translation.
        
        Args:
            is_batch: Whether this is for batch translation
        
        Returns:
            System message for API request
        """
        if is_batch:
            return (
                f"You are a highly skilled translator from {self.source_lang_name} to {self.target_lang_name} specializing in technical and academic content. "
                f"Translate each section of text separated by '-----TRANSLATE_SEPARATOR_TIMESTAMP-----' into {self.target_lang_name}. "
                f"Preserve original formatting, maintain the original meaning, and ensure a natural and fluent translation. "
                f"\n\nCRITICAL INSTRUCTION: NEVER translate technical terminology. These terms MUST remain in their original form:"
                f"\n- Programming languages (Python, Java, JavaScript, TypeScript, C++, etc.)"
                f"\n- Libraries, frameworks, and tools (React, Angular, Django, TensorFlow, etc.)"
                f"\n- Technical concepts and design patterns (Observer Pattern, Dependency Injection, etc.)"
                f"\n- Product/company names and acronyms (GitHub, API, HTTP, REST, etc.)"
                f"\n- File formats and extensions (JSON, XML, CSV, .js, .py, etc.)"
                f"\n- Class names, method names, function names, variable names, and code identifiers"
                f"\n- Database terminology (SQL, ACID, JOIN, index, etc.)"
                
                f"\n\nHow to identify technical terms:"
                f"\n- Terms with capital letters in the middle (camelCase, PascalCase)"
                f"\n- Terms that use dots/periods (React.Component, numpy.array)"
                f"\n- Multiple words that form a specific technical concept (Dependency Injection)"
                f"\n- Words in code blocks or examples"
                f"\n- Any specialized jargon or domain-specific terminology"
                
                f"\n\nImportant guidelines:"
                f"\n1. NEVER partially translate a technical term - either keep the entire term in English or translate the whole phrase"
                f"\n2. When in doubt, preserve the original English term"
                f"\n3. Be consistent: if a term appears multiple times, handle it the same way throughout"
                f"\n4. Maintain the original capitalization and formatting of technical terms"
                f"\n5. For {self.target_lang_name == 'chinese' and '中文' or self.target_lang_name}, add spaces before and after English terms"
                
                f"\n\nReply only with the translations, separated by the same separator marker."
            )
        else:
            return (
                f"You are a highly skilled translator from {self.source_lang_name} to {self.target_lang_name} specializing in technical and academic content. "
                f"Translate the following text into {self.target_lang_name}. "
                f"Preserve original formatting, maintain the original meaning, and ensure a natural and fluent translation. "
                f"\n\nCRITICAL INSTRUCTION: NEVER translate technical terminology. These terms MUST remain in their original form:"
                f"\n- Programming languages (Python, Java, JavaScript, TypeScript, C++, etc.)"
                f"\n- Libraries, frameworks, and tools (React, Angular, Django, TensorFlow, etc.)"
                f"\n- Technical concepts and design patterns (Observer Pattern, Dependency Injection, etc.)"
                f"\n- Product/company names and acronyms (GitHub, API, HTTP, REST, etc.)"
                f"\n- File formats and extensions (JSON, XML, CSV, .js, .py, etc.)"
                f"\n- Class names, method names, function names, variable names, and code identifiers"
                f"\n- Database terminology (SQL, ACID, JOIN, index, etc.)"
                
                f"\n\nHow to identify technical terms:"
                f"\n- Terms with capital letters in the middle (camelCase, PascalCase)"
                f"\n- Terms that use dots/periods (React.Component, numpy.array)"
                f"\n- Multiple words that form a specific technical concept (Dependency Injection)"
                f"\n- Words in code blocks or examples"
                f"\n- Any specialized jargon or domain-specific terminology"
                
                f"\n\nImportant guidelines:"
                f"\n1. NEVER partially translate a technical term - either keep the entire term in English or translate the whole phrase"
                f"\n2. When in doubt, preserve the original English term"
                f"\n3. Be consistent: if a term appears multiple times, handle it the same way throughout"
                f"\n4. Maintain the original capitalization and formatting of technical terms"
                f"\n5. For {self.target_lang_name == 'chinese' and '中文' or self.target_lang_name}, add spaces before and after English terms"
                
                f"\n\nReply only with the translation, no explanations or additional text."
            )
    
    def enable_api(self):
        """Enable API calls. Should be called only after working directory is fully prepared."""
        if not self.api_enabled:
            logger.info("Enabling API calls - working directory preparation is complete")
            self.api_enabled = True
    
    def _make_api_request(self, messages):
        """Make request to Deepseek API.
        
        Args:
            messages: List of message dictionaries
        
        Returns:
            API response
        """
        # Check if API is enabled
        if not self.api_enabled:
            logger.warning("API call attempted before working directory preparation complete")
            return {"choices": [{"message": {"content": "API NOT ENABLED YET - Dummy response until working directory is prepared"}}]}
        # Rate limiting
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < self.rate_limit_interval:
            sleep_time = self.rate_limit_interval - time_since_last_request
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        # Prepare request
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,  # Lower temperature for more consistent translations
            "max_tokens": 4096
        }
        
        # Make request with retries
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(
                    self.DEFAULT_ENDPOINT,
                    headers=headers,
                    data=json.dumps(data),
                    timeout=self.timeout,
                    verify=self.verify_ssl
                )
                response.raise_for_status()
                self.last_request_time = time.time()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"API request failed. Retrying in {wait_time} seconds... ({attempt+1}/{self.max_retries})")
                    logger.debug(f"Error details: {str(e)}")
                    time.sleep(wait_time)
                else:
                    logger.error(f"API request failed after {self.max_retries} retries: {str(e)}")
                    raise
    
    def translate_with_system_message(self, text, system_message):
        """Translate text using a custom system message.
        
        Args:
            text: Text to translate
            system_message: Custom system message for Deepseek
        
        Returns:
            Translated text
        """
        if not text.strip():
            return text
        
        # Make API request with custom system message
        response = self._make_api_request([
            {"role": "system", "content": system_message},
            {"role": "user", "content": text}
        ])
        
        # Extract translation from response
        try:
            translation = response["choices"][0]["message"]["content"]
            return translation.strip()  # No cleaning for custom system messages
        except (KeyError, IndexError) as e:
            logger.error(f"Error extracting translation: {e}")
            logger.debug(f"Response: {response}")
            return text  # Return original text on error
    
    def _clean_translation(self, text):
        """Clean and post-process translation.
        
        Args:
            text: Raw translation from API
        
        Returns:
            Cleaned translation
        """
        # Remove any prefixes that might be included
        prefixes = [
            "Translation:",
            "Translated text:",
            "Here's the translation:",
        ]
        
        cleaned_text = text.strip()
        
        for prefix in prefixes:
            if cleaned_text.startswith(prefix):
                cleaned_text = cleaned_text[len(prefix):].strip()
        
        # Remove any quotes that might wrap the whole translation
        if (cleaned_text.startswith('"') and cleaned_text.endswith('"')) or \
           (cleaned_text.startswith("'") and cleaned_text.endswith("'")):
            cleaned_text = cleaned_text[1:-1]
        
        return cleaned_text

    #
    # Optimized Asynchronous Implementation
    #
    
    async def _ensure_async_session(self):
        """Ensure aiohttp session exists."""
        if not hasattr(self, '_async_session') or self._async_session is None or self._async_session.closed:
            self._async_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept-Encoding": "gzip, deflate"  # Enable compression
                },
                connector=aiohttp.TCPConnector(
                    limit=10,  # Limit concurrent connections
                    verify_ssl=self.verify_ssl,  # Use the same SSL verification setting
                    keepalive_timeout=60,
                    ssl=None
                )
            )
        
        if not hasattr(self, '_async_semaphore') or self._async_semaphore is None:
            self._async_semaphore = asyncio.Semaphore(10)  # Limit concurrent requests
            
        if not hasattr(self, '_request_timestamps'):
            self._request_timestamps = deque(maxlen=self.rate_limit)  # For token bucket rate limiting

    def _get_event_loop(self):
        """Get or create event loop."""
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop
    
    async def _close_async_session(self):
        """Close aiohttp session."""
        if hasattr(self, '_async_session') and self._async_session and not self._async_session.closed:
            await self._async_session.close()
            self._async_session = None
    
    def translate_text_optimized(self, text):
        """Translate a single text using optimized async implementation.
        
        Args:
            text: Text to translate
        
        Returns:
            Translated text
        """
        if not text.strip():
            return text
        
        # Check cache
        cache_key = (text, self.source_lang, self.target_lang)
        if cache_key in self.translation_cache:
            return self.translation_cache[cache_key]
        
        # Get or create event loop
        loop = self._get_event_loop()
        
        # Run async translation in sync context
        result = loop.run_until_complete(self._translate_single_text_async(text))
        
        # Cache the result
        self.translation_cache[cache_key] = result
        return result
    
    def translate_batch_optimized(self, texts, max_tokens=4000, max_batch_size=20):
        """Translate a batch of texts with optimized async processing.
        
        Args:
            texts: List of texts to translate
            max_tokens: Maximum number of tokens per request
            max_batch_size: Maximum number of texts in a batch
            
        Returns:
            List of translated texts
        """
        if not texts:
            return []
        
        # Filter out empty texts and prepare for translation
        translations = []
        texts_to_translate = []
        indices_to_translate = []
        
        for i, text in enumerate(texts):
            if not text.strip():
                translations.append(text)
            else:
                # Check cache
                cache_key = (text, self.source_lang, self.target_lang)
                if cache_key in self.translation_cache:
                    translations.append(self.translation_cache[cache_key])
                else:
                    texts_to_translate.append(text)
                    indices_to_translate.append(i)
                    # Add placeholder to keep array aligned
                    translations.append(None)
        
        # If all texts were in cache, return them
        if not texts_to_translate:
            return translations
        
        # Get or create event loop
        loop = self._get_event_loop()
        
        # Translate the batch using async processing
        batch_translations = loop.run_until_complete(
            self._translate_batch_texts_async(texts_to_translate, max_tokens)
        )
        
        # Update translations list with results
        for idx, trans_idx in enumerate(indices_to_translate):
            if idx < len(batch_translations):
                translations[trans_idx] = batch_translations[idx]
                # Cache the translation
                cache_key = (texts_to_translate[idx], self.source_lang, self.target_lang)
                self.translation_cache[cache_key] = batch_translations[idx]
        
        return translations
    
    async def _translate_single_text_async(self, text):
        """Translate a single text using Deepseek API asynchronously.
        
        Args:
            text: Text to translate
        
        Returns:
            Translated text
        """
        # Construct system message with translation instructions
        system_message = self._get_system_message()
        
        # User message is the text to translate
        user_message = text
        
        # Make API request
        response = await self._make_api_request_async([
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ])
        
        # Extract translation from response
        try:
            translation = response["choices"][0]["message"]["content"]
            return self._clean_translation(translation)
        except (KeyError, IndexError) as e:
            logger.error(f"Error extracting translation: {e}")
            logger.debug(f"Response: {response}")
            return text  # Return original text on error
    
    async def _translate_batch_texts_async(self, texts, max_tokens=4000):
        """Translate a batch of texts using Deepseek API asynchronously with smart chunking.
        
        Args:
            texts: List of texts to translate
            max_tokens: Maximum number of tokens per request
        
        Returns:
            List of translated texts
        """
        # Use smart chunking strategy based on text length to optimize batch processing
        chunks = self._create_optimal_chunks(texts, max_tokens)
        
        # Process all chunks in parallel
        tasks = []
        for chunk in chunks:
            tasks.append(self._process_chunk_async(chunk))
        
        # Gather results from all chunks
        chunk_results = await asyncio.gather(*tasks)
        
        # Flatten and reorder results
        flat_results = []
        for chunk_result in chunk_results:
            flat_results.extend(chunk_result)
        
        return flat_results
    
    def _create_optimal_chunks(self, texts, max_tokens=4000):
        """Create optimal chunks for batch processing based on text lengths.
        
        Args:
            texts: List of texts to translate
            max_tokens: Maximum number of tokens per request
        
        Returns:
            List of chunks, where each chunk is a list of texts
        """
        chunks = []
        current_chunk = []
        current_size = 0
        
        for text in texts:
            # Estimate token count (rough approximation: 4 chars = 1 token)
            text_size = len(text) // 4
            
            # If adding this text would exceed max_tokens, start a new chunk
            if current_size + text_size > max_tokens // 2:  # Leave room for response
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = [text]
                current_size = text_size
            else:
                current_chunk.append(text)
                current_size += text_size
        
        # Add the last chunk if it's not empty
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    async def _process_chunk_async(self, texts):
        """Process a chunk of texts asynchronously.
        
        Args:
            texts: List of texts in this chunk
        
        Returns:
            List of translated texts for this chunk
        """
        if len(texts) == 1:
            # Single text, translate directly
            result = await self._translate_single_text_async(texts[0])
            return [result]
        
        # Multiple texts, use batch translation
        # Construct system message with batch translation instructions
        system_message = self._get_system_message(is_batch=True)
        
        # Join texts with unique separators that are unlikely to appear in content
        separator = "-----TRANSLATE_SEPARATOR_" + str(int(time.time())) + "-----"
        joined_text = separator.join(texts)
        
        # Make API request
        response = await self._make_api_request_async([
            {"role": "system", "content": system_message},
            {"role": "user", "content": joined_text}
        ])
        
        # Extract and split translations
        try:
            translation = response["choices"][0]["message"]["content"]
            # Split by the same separator
            translations = translation.split(separator)
            
            # Make sure we have the right number of translations
            if len(translations) != len(texts):
                logger.warning(f"Expected {len(texts)} translations, got {len(translations)}")
                # If we don't have enough translations, fill with original texts
                while len(translations) < len(texts):
                    translations.append(texts[len(translations)])
                # If we have too many translations, truncate
                translations = translations[:len(texts)]
            
            return [self._clean_translation(t) for t in translations]
            
        except (KeyError, IndexError) as e:
            logger.error(f"Error extracting translations: {e}")
            logger.debug(f"Response: {response}")
            return texts  # Return original texts on error
    
    async def _make_api_request_async(self, messages):
        """Make request to Deepseek API asynchronously with smart rate limiting.
        
        Args:
            messages: List of message dictionaries
        
        Returns:
            API response
        """
        # Check if API is enabled
        if not self.api_enabled:
            logger.warning("Async API call attempted before working directory preparation complete")
            return {"choices": [{"message": {"content": "API NOT ENABLED YET - Dummy response until working directory is prepared"}}]}
        await self._ensure_async_session()
        
        # Apply smart rate limiting
        await self._apply_rate_limit()
        
        # Prepare request
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,  # Lower temperature for more consistent translations
            "max_tokens": 4096
        }
        
        # Use semaphore to limit concurrent requests
        async with self._async_semaphore:
            # Make request with retries and exponential backoff
            for attempt in range(self.max_retries + 1):
                try:
                    # Record request timestamp for rate limiting
                    self._request_timestamps.append(time.time())
                    
                    async with self._async_session.post(
                        self.DEFAULT_ENDPOINT,
                        json=data
                    ) as response:
                        if response.status == 429:  # Too Many Requests
                            wait_time = 2 ** attempt + 1  # Exponential backoff
                            logger.warning(f"Rate limited by API. Waiting {wait_time} seconds...")
                            await asyncio.sleep(wait_time)
                            continue
                            
                        response.raise_for_status()
                        return await response.json()
                        
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    if attempt < self.max_retries:
                        wait_time = 2 ** attempt  # Exponential backoff
                        logger.warning(f"API request failed. Retrying in {wait_time} seconds... ({attempt+1}/{self.max_retries})")
                        logger.debug(f"Error details: {str(e)}")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"API request failed after {self.max_retries} retries: {str(e)}")
                        raise
    
    async def _apply_rate_limit(self):
        """Apply smart rate limiting to avoid hitting API limits."""
        # If we haven't made enough requests to hit the limit, proceed immediately
        if not hasattr(self, '_request_timestamps') or len(self._request_timestamps) < self.rate_limit:
            return
        
        # Calculate how long to wait based on the oldest request in our window
        current_time = time.time()
        oldest_request_time = self._request_timestamps[0]
        time_since_oldest = current_time - oldest_request_time
        
        # If the oldest request is less than our interval window, we need to wait
        if time_since_oldest < 60:  # 60 seconds = 1 minute
            wait_time = 60 - time_since_oldest + 0.1  # Add a small buffer
            logger.debug(f"Rate limiting: waiting for {wait_time:.2f} seconds")
            await asyncio.sleep(wait_time)
    
    def translate_texts_parallel(self, texts, batch_size=20, max_workers=5):
        """Translate multiple texts using parallel processing for maximum throughput.
        
        This method combines both multithreading and async to maximize throughput:
        - Splits texts into batches
        - Processes batches in parallel using ThreadPoolExecutor
        - Each thread uses async to process its batch
        
        Args:
            texts: List of texts to translate
            batch_size: Size of batches to process in parallel
            max_workers: Maximum number of worker threads
        
        Returns:
            List of translated texts
        """
        if not texts:
            return []
        
        # Create batches
        batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]
        
        # Function to process a single batch using async
        def process_batch(batch):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._translate_batch_texts_async(batch))
            finally:
                loop.close()
        
        # Use ThreadPoolExecutor to process batches in parallel
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            batch_results = list(executor.map(process_batch, batches))
            
        # Combine results
        for batch_result in batch_results:
            results.extend(batch_result)
        
        return results
    
    def cleanup(self):
        """Clean up resources."""
        if hasattr(self, '_async_session') and self._async_session:
            loop = self._get_event_loop()
            loop.run_until_complete(self._close_async_session())
