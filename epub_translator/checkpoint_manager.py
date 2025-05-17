#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Checkpoint Manager for EPUB Translator.
Handles saving and loading translation progress for resilient processing
with resume capability.
"""

import os
import json
import time
import logging
import hashlib
import shutil
from datetime import datetime

logger = logging.getLogger("epub_translator.checkpoint_manager")

class CheckpointManager:
    """Manages translation checkpoints for resumable processing."""
    
    def __init__(self, input_path, output_path, config=None):
        """Initialize checkpoint manager.
        
        Args:
            input_path: Path to input EPUB file
            output_path: Path to output EPUB file
            config: Configuration object (optional)
        """
        self.input_path = input_path
        self.output_path = output_path
        self.config = config
        
        # Create checkpoint directory structure
        self.base_name = os.path.basename(input_path).split('.')[0]
        self.workdir = f"{self.base_name}_workdir"
        self.checkpoint_dir = f"{self.workdir}/checkpoint"
        
        # Initialize checkpoint state
        self.state = {
            "source_file": input_path,
            "target_file": output_path,
            "source_file_hash": self._calculate_file_hash(input_path),
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "auto_resume_enabled": True,
            "total_progress": 0.0,
            "phases": {
                "local_processing": {
                    "parsing_completed": False,
                    "content_extraction_completed": False,
                    "chapter_organization_completed": False,
                    "batch_division_completed": False,
                    "terminology_extraction_completed": False,
                    "term_protection_completed": False,
                    "translation_preparation_completed": False,
                    "details": {}
                },
                "terminology": {
                    "completed": False,
                    "terms_file": None,
                    "terms_count": 0
                },
                "preprocessing": {
                    "completed": False,
                    "items_processed": 0
                },
                "translation": {
                    "completed": False,
                    "items_total": 0,
                    "items_completed": 0,
                    "completed_items": [],
                    "current_item": None,
                    "item_progress": 0.0,
                    "translated_segments": 0,
                    "total_segments": 0,
                    "translated_chars": 0,
                    "total_chars": 0,
                    "batches_total": 0,
                    "batches_completed": 0,
                    "completed_batches": []
                },
                "postprocessing": {
                    "completed": False
                }
            },
            "config": self._extract_config(config)
        }
        
        # Create directories
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Create necessary directories for checkpoints and work files."""
        directories = [
            self.workdir,
            self.checkpoint_dir,
            f"{self.workdir}/html_items",
            # terminology directory is no longer created in phase 1
            f"{self.workdir}/chapters_original",
            f"{self.workdir}/chapters_translated",
            f"{self.workdir}/batches",
            f"{self.checkpoint_dir}/batches"
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
    
    def _calculate_file_hash(self, file_path):
        """Calculate MD5 hash of a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            MD5 hash string
        """
        if not os.path.exists(file_path):
            return None
            
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            buf = f.read(65536)  # Read in 64k chunks
            while buf:
                hasher.update(buf)
                buf = f.read(65536)
        
        return hasher.hexdigest()
    
    def _extract_config(self, config):
        """Extract relevant configuration parameters.
        
        Args:
            config: Configuration object
            
        Returns:
            Dictionary with configuration parameters
        """
        if config is None:
            return {}
            
        # Extract parameters that affect batch processing
        config_dict = {
            "batch_size": getattr(config, "get", lambda x, y, z: 10)("processing", "batch_size", 10),
            "max_workers": getattr(config, "get", lambda x, y, z: 4)("processing", "max_parallel_requests", 4),
            "chunk_size": getattr(config, "get", lambda x, y, z: 5000)("processing", "chunk_size", 5000),
            "use_optimized_translator": getattr(config, "getboolean", lambda x, y, z: True)("processing", "use_optimized_translator", True),
            "max_tokens": getattr(config, "getint", lambda x, y, z: 4000)("processing", "max_tokens", 4000),
            "source_lang": getattr(config, "get", lambda x, y, z: "en")("translation", "source_lang", "en"),
            "target_lang": getattr(config, "get", lambda x, y, z: "zh-CN")("translation", "target_lang", "zh-CN")
        }
        
        return config_dict
    
    def check_existing_checkpoint(self):
        """Check if a checkpoint exists for the input file.
        
        Returns:
            Tuple (exists, valid): Whether checkpoint exists and is valid
        """
        checkpoint_file = f"{self.checkpoint_dir}/status.json"
        
        if not os.path.exists(checkpoint_file):
            return False, False
        
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint = json.load(f)
            
            # Check if source file has changed
            current_hash = self._calculate_file_hash(self.input_path)
            saved_hash = checkpoint.get("source_file_hash")
            
            if current_hash != saved_hash:
                logger.warning("Source file has changed since last checkpoint")
                return True, False
            
            # Verify the workdir and key directories exist
            required_dirs = [
                self.workdir,
                self.checkpoint_dir,
                f"{self.workdir}/html_items",
                f"{self.workdir}/batches",
                f"{self.workdir}/chapters_original"
            ]
            
            for directory in required_dirs:
                if not os.path.exists(directory) or not os.path.isdir(directory):
                    logger.warning(f"Required directory does not exist: {directory}")
                    return True, False
            
            # Check if batch files exist for phases marked as completed
            if checkpoint["phases"]["local_processing"].get("batch_division_completed", False):
                # Check for at least one batch file
                batch_files = os.listdir(f"{self.workdir}/batches")
                if not batch_files:
                    logger.warning("Batch division marked as completed but no batch files found")
                    return True, False
            
            # Update state with loaded checkpoint
            self.state = checkpoint
            return True, True
        
        except Exception as e:
            logger.error(f"Error loading checkpoint: {e}")
            return True, False
    
    def save_checkpoint(self):
        """Save current state to checkpoint file."""
        self.state["last_updated"] = datetime.now().isoformat()
        
        checkpoint_file = f"{self.checkpoint_dir}/status.json"
        try:
            with open(checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Checkpoint saved to {checkpoint_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving checkpoint: {e}")
            return False
    
    def update_progress(self, phase, **kwargs):
        """Update progress for a specific phase.
        
        Args:
            phase: Phase name (terminology, preprocessing, translation, postprocessing)
            **kwargs: Phase-specific progress information
        """
        if phase not in self.state["phases"]:
            logger.warning(f"Unknown phase: {phase}")
            return
        
        # Update phase-specific progress
        self.state["phases"][phase].update(kwargs)
        
        # Update total progress
        self._calculate_total_progress()
        
        # Save checkpoint
        self.save_checkpoint()
    
    def _calculate_total_progress(self):
        """Calculate overall progress percentage."""
        phases = self.state["phases"]
        
        # Weight for each phase
        weights = {
            "terminology": 0.05,
            "preprocessing": 0.05,
            "translation": 0.85,
            "postprocessing": 0.05
        }
        
        progress = 0.0
        
        # Terminology phase
        if phases["terminology"]["completed"]:
            progress += weights["terminology"]
        
        # Preprocessing phase
        if phases["preprocessing"]["completed"]:
            progress += weights["preprocessing"]
        else:
            items_total = phases["preprocessing"].get("items_total", 1)
            items_processed = phases["preprocessing"].get("items_processed", 0)
            if items_total > 0:
                progress += weights["preprocessing"] * (items_processed / items_total)
        
        # Translation phase
        if phases["translation"]["completed"]:
            progress += weights["translation"]
        else:
            chars_total = phases["translation"].get("total_chars", 1)
            chars_translated = phases["translation"].get("translated_chars", 0)
            if chars_total > 0:
                progress += weights["translation"] * (chars_translated / chars_total)
        
        # Postprocessing phase
        if phases["postprocessing"]["completed"]:
            progress += weights["postprocessing"]
        
        self.state["total_progress"] = min(100.0, progress * 100)
    
    def update_terminology_phase(self, completed=False, terms_file=None, terms_count=0):
        """Update terminology extraction phase progress.
        
        Args:
            completed: Whether phase is completed
            terms_file: Path to terminology file
            terms_count: Number of terms extracted
        """
        self.update_progress("terminology", 
            completed=completed, 
            terms_file=terms_file, 
            terms_count=terms_count
        )
    
    def update_preprocessing_phase(self, completed=False, items_total=0, items_processed=0):
        """Update preprocessing phase progress.
        
        Args:
            completed: Whether phase is completed
            items_total: Total number of HTML items
            items_processed: Number of processed HTML items
        """
        self.update_progress("preprocessing", 
            completed=completed, 
            items_total=items_total, 
            items_processed=items_processed
        )
    
    def update_translation_phase(self, completed=False, **kwargs):
        """Update translation phase progress.
        
        Args:
            completed: Whether phase is completed
            **kwargs: Translation-specific progress information
        """
        self.update_progress("translation", completed=completed, **kwargs)
    
    def update_postprocessing_phase(self, completed=False):
        """Update postprocessing phase progress.
        
        Args:
            completed: Whether phase is completed
        """
        self.update_progress("postprocessing", completed=completed)
    
    def update_local_processing_phase(self, step_name, completed=True, **details):
        """Update local processing phase progress.
        
        Args:
            step_name: Name of the local processing step
            completed: Whether step is completed
            **details: Additional details about the step
        """
        if step_name not in self.state["phases"]["local_processing"]:
            logger.warning(f"Unknown local processing step: {step_name}")
            return False
            
        # Update step status
        self.state["phases"]["local_processing"][step_name] = completed
        
        # Update details if provided
        if details:
            # Ensure details dictionary exists
            if "details" not in self.state["phases"]["local_processing"]:
                self.state["phases"]["local_processing"]["details"] = {}
                
            # Add step-specific details
            self.state["phases"]["local_processing"]["details"][step_name] = details
        
        # Save checkpoint
        return self.save_checkpoint()
    
    def is_local_processing_step_completed(self, step_name):
        """Check if a local processing step is completed.
        
        Args:
            step_name: Name of the local processing step
            
        Returns:
            Boolean indicating whether the step is completed
        """
        try:
            # First, check if the workdir exists - if not, no step is complete
            if not os.path.exists(self.workdir) or not os.path.isdir(self.workdir):
                logger.warning(f"Working directory {self.workdir} does not exist, treating all steps as incomplete")
                return False
                
            # Step-specific validation to ensure files exist
            if step_name == "batch_division_completed":
                # Check if batches directory exists and has files
                batches_dir = f"{self.workdir}/batches"
                if not os.path.exists(batches_dir) or not os.path.isdir(batches_dir):
                    logger.warning(f"Batches directory does not exist, treating batch division as incomplete")
                    return False
                
                # Check if there are batch files
                files = os.listdir(batches_dir)
                if not files:
                    logger.warning(f"No batch files found, treating batch division as incomplete")
                    return False
            
            elif step_name == "chapter_organization_completed":
                # Check if chapters directory exists and has files
                chapters_dir = f"{self.workdir}/chapters_original"
                if not os.path.exists(chapters_dir) or not os.path.isdir(chapters_dir):
                    logger.warning(f"Chapters directory does not exist, treating chapter organization as incomplete")
                    return False
                
            
            # If all validation passes, check the state
            return self.state["phases"]["local_processing"].get(step_name, False)
        except Exception as e:
            logger.error(f"Error checking step completion: {e}")
            return False
    
    def get_local_processing_details(self, step_name=None):
        """Get details for local processing steps.
        
        Args:
            step_name: Name of specific step or None for all details
            
        Returns:
            Dictionary with step details or all details if step_name is None
        """
        try:
            details = self.state["phases"]["local_processing"].get("details", {})
            if step_name:
                return details.get(step_name, {})
            return details
        except:
            return {} if step_name else {}
    
    def save_batch_status(self, batch_id, status_info):
        """Save status information for a batch.
        
        Args:
            batch_id: Batch identifier (typically "{item_id}_{batch_number}")
            status_info: Dictionary with batch status information
            
        Returns:
            Boolean indicating success
        """
        try:
            # Ensure batches directory exists
            batches_dir = f"{self.checkpoint_dir}/batches"
            os.makedirs(batches_dir, exist_ok=True)
            
            # Create batch status file path
            status_file = f"{batches_dir}/batch_{batch_id}_status.json"
            
            # Save status information
            with open(status_file, 'w', encoding='utf-8') as f:
                json.dump(status_info, f, indent=2, ensure_ascii=False)
                
            # Update batch in completed_batches list if completed
            if status_info.get("translation_completed", False):
                completed_batches = self.state["phases"]["translation"].get("completed_batches", [])
                if batch_id not in completed_batches:
                    completed_batches.append(batch_id)
                    self.state["phases"]["translation"]["completed_batches"] = completed_batches
                    self.state["phases"]["translation"]["batches_completed"] = len(completed_batches)
                
            # Save overall checkpoint
            self.save_checkpoint()
            
            return True
        except Exception as e:
            logger.error(f"Error saving batch status for {batch_id}: {e}")
            return False
    
    def load_batch_status(self, batch_id):
        """Load status information for a batch.
        
        Args:
            batch_id: Batch identifier
            
        Returns:
            Dictionary with batch status information or None if not found
        """
        try:
            status_file = f"{self.checkpoint_dir}/batches/batch_{batch_id}_status.json"
            
            if not os.path.exists(status_file):
                return None
                
            with open(status_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading batch status for {batch_id}: {e}")
            return None
    
    def save_batch_info(self, item_id, batch_info):
        """Save batch information for an HTML item.
        
        Args:
            item_id: HTML item ID
            batch_info: Dictionary with batch information
        """
        safe_id = item_id.replace('/', '_')
        batch_file = f"{self.checkpoint_dir}/batches/item_{safe_id}_batches.json"
        
        try:
            with open(batch_file, 'w', encoding='utf-8') as f:
                json.dump(batch_info, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Batch info saved for item {item_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving batch info for item {item_id}: {e}")
            return False
    
    def load_batch_info(self, item_id):
        """Load batch information for an HTML item.
        
        Args:
            item_id: HTML item ID
            
        Returns:
            Dictionary with batch information or None if not found
        """
        safe_id = item_id.replace('/', '_')
        batch_file = f"{self.checkpoint_dir}/batches/item_{safe_id}_batches.json"
        
        if not os.path.exists(batch_file):
            return None
        
        try:
            with open(batch_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading batch info for item {item_id}: {e}")
            return None
    
    def clear_checkpoint(self):
        """Clear checkpoint information."""
        try:
            if os.path.exists(self.checkpoint_dir):
                shutil.rmtree(self.checkpoint_dir)
            
            # Recreate empty directories
            self._ensure_directories()
            
            # Reset state
            self.state["last_updated"] = datetime.now().isoformat()
            self.state["total_progress"] = 0.0
            for phase in self.state["phases"]:
                self.state["phases"][phase]["completed"] = False
            
            logger.info("Checkpoint cleared")
            return True
        except Exception as e:
            logger.error(f"Error clearing checkpoint: {e}")
            return False
    
    def get_progress_info(self):
        """Get progress information.
        
        Returns:
            Dictionary with progress information
        """
        phases = self.state["phases"]
        
        # Calculate expected time remaining
        translation_phase = phases["translation"]
        
        progress_info = {
            "total_progress": self.state["total_progress"],
            "phases": {
                "terminology": {
                    "completed": phases["terminology"]["completed"],
                    "terms_count": phases["terminology"]["terms_count"]
                },
                "preprocessing": {
                    "completed": phases["preprocessing"]["completed"],
                    "items_total": phases["preprocessing"].get("items_total", 0),
                    "items_processed": phases["preprocessing"].get("items_processed", 0)
                },
                "translation": {
                    "completed": translation_phase["completed"],
                    "items_total": translation_phase.get("items_total", 0),
                    "items_completed": len(translation_phase.get("completed_items", [])),
                    "translated_segments": translation_phase.get("translated_segments", 0),
                    "total_segments": translation_phase.get("total_segments", 0),
                    "translated_chars": translation_phase.get("translated_chars", 0),
                    "total_chars": translation_phase.get("total_chars", 0)
                },
                "postprocessing": {
                    "completed": phases["postprocessing"]["completed"]
                }
            },
            "last_updated": self.state["last_updated"]
        }
        
        return progress_info
    
    def _extract_toc(self, book):
        """Extract TOC from EPUB book.
        
        Args:
            book: ebooklib.epub.EpubBook instance
            
        Returns:
            List of TOC items with their hierarchy
        """
        def process_toc_entries(entries, depth=0):
            result = []
            for entry in entries:
                # Handle different TOC entry types with more robust type checking
                if isinstance(entry, tuple) and len(entry) >= 2:
                    # tuple: (title, href) or (title, href, children)
                    title, href = entry[0], entry[1]
                    children = entry[2] if len(entry) > 2 else []
                    
                    item = {
                        "title": str(title),
                        "href": str(href),
                        "depth": depth
                    }
                    result.append(item)
                    
                    # Process children
                    if children:
                        result.extend(process_toc_entries(children, depth + 1))
                        
                elif hasattr(entry, 'title') and hasattr(entry, 'href'):
                    # ebooklib TOC entry object
                    item = {
                        "title": str(entry.title),
                        "href": str(entry.href),
                        "depth": depth
                    }
                    result.append(item)
                    
                    # Process children
                    if hasattr(entry, 'children') and entry.children:
                        result.extend(process_toc_entries(entry.children, depth + 1))
                        
                elif hasattr(entry, '__dict__'):
                    # Generic object with attributes - handle Section or other custom types
                    try:
                        # Extract whatever properties we can
                        props = {}
                        if hasattr(entry, 'title'):
                            props["title"] = str(entry.title)
                        elif hasattr(entry, 'name'):
                            props["title"] = str(entry.name)
                        else:
                            props["title"] = str(entry)
                            
                        if hasattr(entry, 'href'):
                            props["href"] = str(entry.href)
                        elif hasattr(entry, 'file_name'):
                            props["href"] = str(entry.file_name)
                        else:
                            props["href"] = "#"
                            
                        props["depth"] = depth
                        result.append(props)
                        
                        # Process any children
                        if hasattr(entry, 'children') and entry.children:
                            result.extend(process_toc_entries(entry.children, depth + 1))
                        elif hasattr(entry, 'subitems') and entry.subitems:
                            result.extend(process_toc_entries(entry.subitems, depth + 1))
                    except Exception as e:
                        # If we can't extract properties, just add a simple entry
                        logger.warning(f"Could not fully process TOC entry: {str(e)}")
                        result.append({
                            "title": f"Entry {len(result) + 1}",
                            "href": "#",
                            "depth": depth
                        })
                else:
                    # Fallback for any other type
                    result.append({
                        "title": str(entry),
                        "href": "#",
                        "depth": depth
                    })
            
            return result
        
        try:
            return process_toc_entries(book.toc)
        except Exception as e:
            logger.error(f"Error extracting TOC: {str(e)}")
            # Return empty TOC in case of error
            return []
    
    def _generate_toc_text(self, book):
        """Generate TOC text from EPUB book.
        
        Args:
            book: ebooklib.epub.EpubBook instance
            
        Returns:
            String containing the TOC text
        """
        toc_items = self._extract_toc(book)
        toc_text = ""
        
        for item in toc_items:
            depth = item.get("depth", 0)
            title = item.get("title", "")
            toc_text += "  " * depth + title + "\n"
            
        return toc_text
