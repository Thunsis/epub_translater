#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Configuration handler for EPUB Translator.
Handles loading, saving, and accessing configuration parameters.
"""

import os
import configparser
import logging

logger = logging.getLogger("epub_translator.config")

class Config:
    """Configuration handler for the EPUB translator."""
    
    DEFAULT_CONFIG = {
        'deepseek': {
            'api_key': '',
            'model': 'deepseek-chat',
            'api_endpoint': 'https://api.deepseek.com/v1/chat/completions',
            'timeout': '30',
            'max_retries': '3',
            'rate_limit': '10'  # requests per minute
        },
        'translation': {
            'preserve_formatting': 'True',
            'preserve_line_breaks': 'True',
            'translate_titles': 'True',
            'translate_captions': 'True',
            'translate_alt_text': 'True',
            'translate_metadata': 'True'
        },
        'terminology': {
            'use_deepseek': 'True'
        },
        'processing': {
            'batch_size': '10',  # paragraphs per API request
            'max_parallel_requests': '3',
            'cache_translations': 'True',
            'cache_dir': '.translation_cache'
        }
    }
    
    def __init__(self, config_file="config.ini"):
        """Initialize configuration from file or create default."""
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        
        # Load existing config or create default
        if os.path.exists(config_file):
            logger.info(f"Loading configuration from {config_file}")
            self.config.read(config_file)
            self._validate_config()
        else:
            logger.info(f"Creating default configuration in {config_file}")
            self._create_default_config()
            self.save()
    
    def _create_default_config(self):
        """Create default configuration."""
        for section, options in self.DEFAULT_CONFIG.items():
            if not self.config.has_section(section):
                self.config.add_section(section)
            
            for option, value in options.items():
                self.config.set(section, option, value)
    
    def _validate_config(self):
        """Ensure all required configuration options are present."""
        # Add any missing sections or options
        for section, options in self.DEFAULT_CONFIG.items():
            if not self.config.has_section(section):
                logger.warning(f"Missing section '{section}' in config, adding defaults")
                self.config.add_section(section)
            
            for option, default_value in options.items():
                if not self.config.has_option(section, option):
                    logger.warning(f"Missing option '{option}' in section '{section}', adding default")
                    self.config.set(section, option, default_value)
    
    def get(self, section, option, fallback=None):
        """Get configuration value."""
        try:
            return self.config.get(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError):
            if fallback is not None:
                return fallback
            # If no fallback is provided, check if there's a default
            try:
                return self.DEFAULT_CONFIG[section][option]
            except KeyError:
                logger.error(f"Configuration option '{section}.{option}' not found")
                return None
    
    def getboolean(self, section, option, fallback=None):
        """Get boolean configuration value."""
        try:
            return self.config.getboolean(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            if fallback is not None:
                return fallback
            # If no fallback is provided, check if there's a default
            try:
                return self.config.getboolean(section, self.DEFAULT_CONFIG[section][option])
            except (KeyError, ValueError):
                logger.error(f"Boolean configuration option '{section}.{option}' not found or invalid")
                return None
    
    def getint(self, section, option, fallback=None):
        """Get integer configuration value."""
        try:
            return self.config.getint(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            if fallback is not None:
                return fallback
            # If no fallback is provided, check if there's a default
            try:
                return int(self.DEFAULT_CONFIG[section][option])
            except (KeyError, ValueError):
                logger.error(f"Integer configuration option '{section}.{option}' not found or invalid")
                return None
    
    def getfloat(self, section, option, fallback=None):
        """Get float configuration value."""
        try:
            return self.config.getfloat(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            if fallback is not None:
                return fallback
            # If no fallback is provided, check if there's a default
            try:
                return float(self.DEFAULT_CONFIG[section][option])
            except (KeyError, ValueError):
                logger.error(f"Float configuration option '{section}.{option}' not found or invalid")
                return None
    
    def set(self, section, option, value):
        """Set configuration value."""
        if not self.config.has_section(section):
            self.config.add_section(section)
        
        self.config.set(section, option, str(value))
    
    def save(self):
        """Save configuration to file."""
        with open(self.config_file, 'w') as f:
            self.config.write(f)
        logger.info(f"Configuration saved to {self.config_file}")
