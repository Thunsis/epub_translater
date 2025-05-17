# EPUB Translator

## Setup

### Virtual Environment

```bash
# Create a virtual environment
python -m venv venv

# Activate virtual environment
# On Windows
venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate
```

### Install Requirements

```bash
pip install -r requirements.txt
```

## Usage

```bash
# All phases in one go
python main.py input.epub -o translated.epub

# Phase 1 only: No API calls, just file analysis and preparation
python main.py input.epub --phase prepare

# Phase 2 only: Terminology enhancement with DeepSeek
python main.py input.epub --phase terminology

# Phase 3 only: Translation with DeepSeek
python main.py input.epub -o translated.epub --phase translate
