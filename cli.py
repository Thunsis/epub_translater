#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Command-line entry point for the EPUB Translator.
This script allows running the translator without installing the package.
"""

import sys
import os

# Add parent directory to path to allow importing the package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from epub_translator.main import main

if __name__ == "__main__":
    main()
