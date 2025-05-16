#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Main entry point for the EPUB Translator.
This script imports and runs the main function from the epub_translator package.
"""

import sys
import os

# Add the current directory to the path so we can import the package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the main function from the package
from epub_translator.main import main

if __name__ == "__main__":
    main()
