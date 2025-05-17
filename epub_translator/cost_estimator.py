#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Cost estimator module for DeepSeek API usage.
Estimates the cost of using DeepSeek API for terminology extraction and translation
based on content size and time of day (Beijing time).
"""

import logging
import pytz
from datetime import datetime, time

logger = logging.getLogger("epub_translator.cost_estimator")

# Debug flag - set to True to force logging of cost estimator execution
DEBUG_COST_ESTIMATOR = True

# DeepSeek API pricing per 1000 tokens (subject to change)
# Pricing varies based on Beijing time (peak vs. off-peak hours)
DEEPSEEK_PRICING = {
    # Peak pricing (8:00-24:00 Beijing time)
    "peak": {
        "deepseek-chat": 0.002,  # $0.002 per 1000 tokens for input
        "deepseek-chat-response": 0.008  # $0.008 per 1000 tokens for output
    },
    # Off-peak pricing (0:00-8:00 Beijing time)
    "off_peak": {
        "deepseek-chat": 0.001,  # $0.001 per 1000 tokens for input
        "deepseek-chat-response": 0.004  # $0.004 per 1000 tokens for output
    }
}

# Token estimation factors
CHARS_PER_TOKEN = 5  # Average characters per token (rough estimate)
TERMINOLOGY_TOKEN_FACTOR = 0.3  # Terminology phase uses about 30% of total tokens
TRANSLATION_INPUT_OUTPUT_RATIO = 2.0  # Output tokens are about 2x input tokens for translation

def is_peak_hour_beijing():
    """Determine if current time is peak pricing hours in Beijing.
    
    Returns:
        Boolean indicating if it's peak pricing hours (8:00-24:00 Beijing time)
    """
    beijing_tz = pytz.timezone('Asia/Shanghai')
    beijing_time = datetime.now(beijing_tz).time()
    
    # Peak hours: 8:00 - 24:00 Beijing time
    peak_start = time(8, 0)
    peak_end = time(23, 59, 59)
    
    return peak_start <= beijing_time <= peak_end

def get_current_pricing():
    """Get current pricing based on Beijing time.
    
    Returns:
        Dictionary with current pricing for DeepSeek API
    """
    if is_peak_hour_beijing():
        return DEEPSEEK_PRICING["peak"]
    else:
        return DEEPSEEK_PRICING["off_peak"]

def chars_to_tokens(char_count):
    """Convert character count to estimated token count.
    
    Args:
        char_count: Number of characters
        
    Returns:
        Estimated number of tokens
    """
    return char_count / CHARS_PER_TOKEN

def estimate_api_cost(char_count, model="deepseek-chat"):
    """Estimate DeepSeek API cost based on character count.
    
    Args:
        char_count: Number of characters
        model: DeepSeek model name
        
    Returns:
        Dictionary with cost estimates for terminology and translation phases
    """
    # Get current pricing
    pricing = get_current_pricing()
    
    # Convert characters to tokens
    total_tokens = chars_to_tokens(char_count)
    
    # Estimate terminology phase cost
    terminology_tokens = total_tokens * TERMINOLOGY_TOKEN_FACTOR
    terminology_cost = (terminology_tokens / 1000) * pricing[model]
    
    # Estimate translation phase cost
    translation_input_tokens = total_tokens
    translation_output_tokens = total_tokens * TRANSLATION_INPUT_OUTPUT_RATIO
    translation_input_cost = (translation_input_tokens / 1000) * pricing[model]
    translation_output_cost = (translation_output_tokens / 1000) * pricing[model + "-response"]
    translation_cost = translation_input_cost + translation_output_cost
    
    # Total cost
    total_cost = terminology_cost + translation_cost
    
    return {
        "terminology_cost": terminology_cost,
        "translation_cost": translation_cost,
        "total_cost": total_cost,
        "terminology_tokens": terminology_tokens,
        "translation_input_tokens": translation_input_tokens,
        "translation_output_tokens": translation_output_tokens,
        "total_tokens": terminology_tokens + translation_input_tokens + translation_output_tokens,
        "is_peak_pricing": is_peak_hour_beijing(),
        "pricing_period": "Peak (8:00-24:00 Beijing)" if is_peak_hour_beijing() else "Off-peak (0:00-8:00 Beijing)"
    }

def format_cost_estimate(cost_estimate):
    """Format cost estimate for display.
    
    Args:
        cost_estimate: Cost estimate dictionary from estimate_api_cost()
        
    Returns:
        Formatted string with cost estimate
    """
    return f"""
=== DeepSeek API Cost Estimate ===
Pricing period: {cost_estimate['pricing_period']}

Terminology phase (Phase 2):
  • Estimated tokens: {cost_estimate['terminology_tokens']:,.0f}
  • Estimated cost: ${cost_estimate['terminology_cost']:.2f} USD

Translation phase (Phase 3):
  • Input tokens: {cost_estimate['translation_input_tokens']:,.0f}
  • Output tokens: {cost_estimate['translation_output_tokens']:,.0f}
  • Estimated cost: ${cost_estimate['translation_cost']:.2f} USD

Total estimated cost: ${cost_estimate['total_cost']:.2f} USD
Total estimated tokens: {cost_estimate['total_tokens']:,.0f}

Note: This is an estimate only. Actual costs may vary based on the specific content,
model efficiency, and any changes to DeepSeek's pricing structure.
"""
