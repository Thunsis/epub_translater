#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Translator module for the EPUB Translator.
Handles communication with the Deepseek API for text translation.
"""

import os
import json
import time
import logging
import requests
from tqdm import tqdm
import re

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
                 model="deepseek-chat", max_retries=3, timeout=30, rate_limit=10):
        """Initialize the Deepseek translator.
        
        Args:
            api_key: Deepseek API key
            source_lang: Source language code (default: en for English)
            target_lang: Target language code (default: zh-CN for Simplified Chinese)
            model: Deepseek model to use
            max_retries: Maximum number of retries for API calls
            timeout: Timeout for API calls in seconds
            rate_limit: Maximum requests per minute
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
                f"Analyze the subject matter domain of the content and identify domain-specific terminology. "
                f"DO NOT translate any professional terminology, including technical terms, product names, programming languages, "
                f"scientific concepts, industry standards, and specialized jargon. Keep these in their original form. "
                f"Use your understanding of various professional domains to identify these terms accurately. "
                f"Look for terms that have specific meaning within a technical or scientific context. "
                f"Reply only with the translations, separated by the same separator marker."
            )
        else:
            return (
                f"You are a highly skilled translator from {self.source_lang_name} to {self.target_lang_name} specializing in technical and academic content. "
                f"Translate the following text into {self.target_lang_name}. "
                f"Preserve original formatting, maintain the original meaning, and ensure a natural and fluent translation. "
                f"Analyze the subject matter domain of the content and identify domain-specific terminology. "
                f"DO NOT translate any professional terminology, including technical terms, product names, programming languages, "
                f"scientific concepts, industry standards, and specialized jargon. Keep these in their original form. "
                f"Use your understanding of various professional domains to identify these terms accurately. "
                f"Look for terms that have specific meaning within a technical or scientific context. "
                f"Reply only with the translation, no explanations or additional text."
            )
    
    def _make_api_request(self, messages):
        """Make request to Deepseek API.
        
        Args:
            messages: List of message dictionaries
        
        Returns:
            API response
        """
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
                    timeout=self.timeout
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
