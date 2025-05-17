#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
EPUB translation module for the EPUBProcessor class.
Handles translating content, managing batches, and rebuilding
the translated EPUB file.
"""

import os
import logging
import copy
import time
import json
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

# Configure logger
logger = logging.getLogger("epub_translator.epub_processor")

# Import our custom modules conditionally to handle the case when they're not available
try:
    from epub_translator.checkpoint_manager import CheckpointManager
    from epub_translator.progress_tracker import ProgressTracker
    from epub_translator.content_manager import ContentManager
    CHECKPOINT_SUPPORT = True
except ImportError:
    logger.warning("Checkpoint support modules not found, running without checkpoint capabilities")
    CHECKPOINT_SUPPORT = False

def translate_prepared_content(self, input_path, output_path, force_restart=False):
    """Translate prepared content from workdir and save to output_path.
    
    This method assumes extract_and_prepare_content has been called first.
    
    Args:
        input_path: Path to input EPUB file (used to locate workdir)
        output_path: Path to save translated EPUB file
        force_restart: Whether to force restart translation (ignore checkpoints)
        
    Returns:
        Dictionary with translation statistics
    """
    if not self.translator:
        raise ValueError("Translator instance is required for translation")
    
    self.force_restart = force_restart
    start_time = time.time()
    
    # Initialize checkpoint and progress tracking if supported
    if CHECKPOINT_SUPPORT:
        self.checkpoint_manager = CheckpointManager(input_path, output_path, self.config)
        self.progress_tracker = ProgressTracker(self.checkpoint_manager)
        self.content_manager = ContentManager(self.checkpoint_manager.workdir)
        
        # Set up progress tracker
        self.progress_tracker.setup(self.checkpoint_manager.workdir)
        
        # 检查是否存在checkpoint并加载它
        if not force_restart:
            checkpoint_exists, valid = self.checkpoint_manager.check_existing_checkpoint()
            if checkpoint_exists and valid:
                logger.info("找到有效的checkpoint，准备恢复翻译状态")
                # 如果有翻译缓存，也可以恢复它
                cache_path = f"{self.checkpoint_manager.workdir}/translation_cache.json"
                if os.path.exists(cache_path):
                    try:
                        with open(cache_path, 'r', encoding='utf-8') as f:
                            import json
                            self.translation_cache = json.load(f)
                        logger.info(f"已恢复 {len(self.translation_cache)} 个缓存的翻译")
                    except Exception as e:
                        logger.error(f"恢复翻译缓存时出错: {e}")
            elif checkpoint_exists and not valid:
                logger.warning("找到无效的checkpoint，将开始新的翻译")
                self.checkpoint_manager.clear_checkpoint()
        
        # Check if all the required phases from local processing are completed
        local_processing = self.checkpoint_manager.state["phases"]["local_processing"]
        if not local_processing.get("translation_preparation_completed", False):
            logger.error("Content preparation has not been completed. Run with --phase prepare first.")
            logger.debug(f"Local processing state: {local_processing}")
            return None
    else:
        logger.error("Checkpoint support is required for two-phase processing")
        return None
        
    try:
        logger.info(f"Loading EPUB file: {input_path}")
        if self.progress_tracker:
            self.progress_tracker.start_phase("translation", f"Translating prepared content using {self.max_workers} parallel workers")
        
        # Load original EPUB to get basic structure
        book = epub.read_epub(input_path)
        
        # Create a deep copy to avoid modifying the original
        translated_book = copy.deepcopy(book)
        
        # Extract metadata we want to preserve
        from epub_translator.epub_processor_utils import _extract_metadata
        metadata = _extract_metadata(self, book)
        
        # Get batch details from checkpoint
        if not self.checkpoint_manager:
            logger.error("Checkpoint manager is required for translate-only mode")
            return None
            
        # Get total number of batches and segments
        batch_details = self.checkpoint_manager.get_local_processing_details("batch_division_completed")
        if not batch_details:
            logger.error("Batch division information not found in checkpoint")
            return None
            
        total_segments = batch_details.get("total_segments", 0)
        total_batches = batch_details.get("total_batches", 0)
        
        # Update translation stats
        self.total_segments = total_segments
        
        if self.progress_tracker:
            self.progress_tracker.update_translation_progress(
                translated_segments=0,
                total_segments=total_segments,
                translated_chars=0,
                total_chars=self.total_chars
            )
        
        # Create HTML items tracking
        html_items = []
        item_map = {}
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                html_items.append(item)
                item_map[item.get_id()] = item
        
        # Process all batch files
        logger.info(f"Translating batches: found {total_batches} batches with {total_segments} segments")
        
        # Get all item info files
        batch_files = []
        for item_id in sorted(item_map.keys()):
            # Load batch info
            batch_info = self.checkpoint_manager.load_batch_info(item_id)
            if not batch_info:
                logger.warning(f"No batch info found for item {item_id}")
                continue
            
            # Process each batch
            for batch_data in batch_info.get("batches", []):
                batch_id = batch_data.get("batch_id")
                batch_key = batch_data.get("batch_key", f"{item_id.replace('/', '_')}_{batch_id:03d}")
                batch_files.append({
                    "item_id": item_id,
                    "batch_id": batch_id,
                    "batch_key": batch_key,
                    "completed": batch_data.get("completed", False)
                })
        
        # Update count in checkpoint
        if self.checkpoint_manager:
            self.checkpoint_manager.update_translation_phase(
                batches_total=len(batch_files),
                batches_completed=0
            )
        
        # Track processed items for final assembly
        processed_item_batches = defaultdict(list)
        
        # Process batches with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            batch_info_map = {}
            
            # Submit all non-completed batches for translation
            for batch_info in batch_files:
                item_id = batch_info["item_id"]
                batch_id = batch_info["batch_id"]
                batch_key = batch_info["batch_key"]
                
                # Skip completed batches if not force restarting
                batch_status = self.checkpoint_manager.load_batch_status(batch_key)
                if not self.force_restart and batch_status and batch_status.get("translation_completed", False):
                    logger.debug(f"Skipping already translated batch: {batch_key}")
                    processed_item_batches[item_id].append(batch_id)
                    continue
                
                # Schedule batch for translation
                future = executor.submit(
                    _translate_prepared_batch,
                    self,
                    item_id=item_id,
                    batch_id=batch_id,
                    batch_key=batch_key
                )
                futures[future] = batch_info
                batch_info_map[future] = batch_info
            
            # Process results as they complete
            completed_count = 0
            for future in tqdm(
                as_completed(futures),
                total=len(futures),
                desc="Translating batches"
            ):
                batch_info = batch_info_map[future]
                item_id = batch_info["item_id"]
                batch_id = batch_info["batch_id"]
                
                try:
                    success = future.result()
                    if success:
                        processed_item_batches[item_id].append(batch_id)
                        completed_count += 1
                        
                        # Update progress
                        if self.progress_tracker:
                            progress_pct = (completed_count / len(futures)) * 100
                            self.progress_tracker.update_translation_progress(
                                translated_segments=self.translated_segments,
                                total_segments=self.total_segments,
                                translated_chars=self.translated_chars,
                                total_chars=self.total_chars,
                                item_progress=progress_pct
                            )
                        
                        # Update checkpoint
                        if self.checkpoint_manager:
                            self.checkpoint_manager.update_translation_phase(
                                translated_segments=self.translated_segments,
                                total_segments=self.total_segments,
                                translated_chars=self.translated_chars,
                                total_chars=self.total_chars,
                                batches_completed=completed_count
                            )
                except Exception as e:
                    logger.error(f"Error processing batch {batch_info['batch_key']}: {str(e)}")
        
        # Now rebuild the HTML files from translated batches
        logger.info("Rebuilding HTML files from translated batches")
        results = {}
        
        for item_id, batch_ids in processed_item_batches.items():
            # Get original item
            original_item = item_map.get(item_id)
            if not original_item:
                logger.warning(f"Original item {item_id} not found in book")
                continue
            
            # First try to load the translated item directly
            item_dir = f"{self.checkpoint_manager.workdir}/html_items/{item_id.replace('/', '_')}"
            translated_path = f"{item_dir}/translated.html"
            
            if os.path.exists(translated_path):
                try:
                    with open(translated_path, 'rb') as f:
                        content = f.read()
                    
                    # Create a new item for the translated book
                    translated_item = epub.EpubHtml(
                        uid=original_item.get_id(),
                        file_name=original_item.get_name(),
                        media_type="application/xhtml+xml",
                        content=content
                    )
                    # Copy properties
                    translated_item.properties = original_item.properties
                    results[item_id] = translated_item
                    logger.info(f"Loaded translated item {item_id} from file")
                    continue
                except Exception as e:
                    logger.error(f"Error loading translated item {item_id}: {e}")
                    # Continue with batch-based reconstruction
            
            # Get content and create BeautifulSoup object for rebuilding
            content = original_item.get_content().decode('utf-8')
            soup = BeautifulSoup(content, 'html.parser')
            
            # Load each batch and apply translations
            for batch_id in sorted(batch_ids):
                batch_file = f"{self.checkpoint_manager.workdir}/html_items/{item_id.replace('/', '_')}/batches/batch_{batch_id:03d}/translated.txt"
                
                if not os.path.exists(batch_file):
                    logger.warning(f"Translated batch file not found: {batch_file}")
                    continue
                
                try:
                    with open(batch_file, 'r', encoding='utf-8') as f:
                        translated_texts = f.read().split('\n---\n')
                    
                    # Get the segment indices for this batch
                    batch_info = self.checkpoint_manager.load_batch_info(item_id)
                    if not batch_info or batch_id >= len(batch_info.get("batches", [])):
                        logger.warning(f"Batch info not found for {item_id}, batch {batch_id}")
                        continue
                        
                    segment_indices = batch_info["batches"][batch_id].get("segment_indices", [])
                    
                    # Get all translatable segments to apply translations
                    from epub_translator.epub_processor_utils import _extract_translatable_segments
                    translatable_segments = _extract_translatable_segments(self, soup, item_id=item_id)
                    
                    # Apply translations to segments
                    for idx, seg_idx in enumerate(segment_indices):
                        if idx < len(translated_texts) and seg_idx < len(translatable_segments):
                            element, attribute, _ = translatable_segments[seg_idx]
                            from epub_translator.epub_processor_utils import _update_segment
                            _update_segment(self, element, attribute, translated_texts[idx])
                except Exception as e:
                    logger.error(f"Error applying translations from batch {batch_id} to {item_id}: {e}")
            
            # Create a new item with the translated content
            translated_content = str(soup)
            translated_item = epub.EpubHtml(
                uid=original_item.get_id(),
                file_name=original_item.get_name(),
                media_type="application/xhtml+xml",
                content=translated_content.encode('utf-8')
            )
            
            # Copy properties
            translated_item.properties = original_item.properties
            
            # Save to results
            results[item_id] = translated_item
            
            # Save chapter content
            if self.content_manager:
                self.content_manager.save_html_item(translated_item, is_translated=True)
                
                # Extract chapter title
                chapter_title = None
                try:
                    translated_soup = BeautifulSoup(translated_content, 'html.parser')
                    title_tag = translated_soup.find(['h1', 'h2', 'h3', 'title'])
                    if title_tag:
                        chapter_title = title_tag.get_text().strip()
                except Exception:
                    pass
                
                # Save chapter
                self.content_manager.save_chapter_content(
                    translated_item, 
                    chapter_title=chapter_title, 
                    is_translated=True
                )
        
        # Add translated items to the book
        for item in html_items:
            item_id = item.get_id()
            if item_id in results and results[item_id]:
                translated_book.add_item(results[item_id])
        
        # Mark translation phase as completed
        if self.progress_tracker:
            self.progress_tracker.update_translation_progress(
                translated_segments=self.translated_segments,
                total_segments=self.total_segments,
                translated_chars=self.translated_chars,
                total_chars=self.total_chars,
                is_completed=True
            )
        
        if self.checkpoint_manager:
            self.checkpoint_manager.update_translation_phase(
                completed=True,
                translated_segments=self.translated_segments,
                total_segments=self.total_segments,
                translated_chars=self.translated_chars,
                total_chars=self.total_chars
            )
        
        # Start postprocessing phase
        if self.progress_tracker:
            self.progress_tracker.start_phase("postprocessing", "Applying final processing to translated content")
        
        # Set metadata in translated book
        from epub_translator.epub_processor_utils import _set_metadata
        _set_metadata(self, translated_book, metadata)
        
        # Save translated metadata
        if self.content_manager:
            self.content_manager.save_metadata(metadata, is_translated=True)
        
        # Write the translated book
        logger.info(f"Writing translated EPUB to: {output_path}")
        epub.write_epub(output_path, translated_book)
        
        # Mark postprocessing as completed
        if self.progress_tracker:
            self.progress_tracker.update_postprocessing_progress(is_completed=True)
        
        if self.checkpoint_manager:
            self.checkpoint_manager.update_postprocessing_phase(completed=True)
        
        # Create HTML report
        if self.progress_tracker:
            self.progress_tracker.create_html_report(self.checkpoint_manager.workdir)
        
        # Create content index
        if self.content_manager:
            self.content_manager.create_html_index()
        
        # Save translation cache
        from epub_translator.epub_processor_utils import _save_translation_cache
        _save_translation_cache(self)
        
        # Return statistics
        end_time = time.time()
        processing_time = end_time - start_time
        chars_per_second = self.translated_chars / processing_time if processing_time > 0 else 0
        
        stats = {
            'total_chars': self.total_chars,
            'total_segments': self.total_segments,
            'translated_chars': self.translated_chars,
            'translated_segments': self.translated_segments,
            'processing_time': processing_time,
            'chars_per_second': chars_per_second,
            'total_time': processing_time
        }
        
        logger.info(f"Translation complete in {processing_time:.2f} seconds")
        logger.info(f"Processing speed: {chars_per_second:.2f} characters per second")
        
        return stats
        
    except Exception as e:
        logger.error(f"Error during translation: {str(e)}", exc_info=True)
        # Save checkpoint before exiting
        if self.checkpoint_manager:
            self.checkpoint_manager.save_checkpoint()
        raise

def _translate_prepared_batch(self, item_id, batch_id, batch_key):
    """Translate a prepared batch from workdir.
    
    Args:
        item_id: HTML item ID
        batch_id: Batch ID
        batch_key: Unique batch identifier
        
    Returns:
        Boolean indicating success
    """
    try:
        # Load batch content
        batch_dir = f"{self.checkpoint_manager.workdir}/html_items/{item_id.replace('/', '_')}/batches/batch_{batch_id:03d}"
        
        # Check if we have original text
        original_file = f"{batch_dir}/original.txt"
        if not os.path.exists(original_file):
            logger.error(f"Original text file not found for batch {batch_key}")
            return False
        
        # Load original texts
        with open(original_file, 'r', encoding='utf-8') as f:
            original_texts = f.read().split('\n---\n')
        
        # Skip if no texts to translate
        if not original_texts:
            logger.warning(f"No texts to translate in batch {batch_key}")
            return False
        
        # Check cache for translations
        translations_to_do = []
        indices_to_translate = []
        cached_translations = []
        
        for i, text in enumerate(original_texts):
            cache_key = text
            if cache_key in self.translation_cache:
                cached_translations.append((i, self.translation_cache[cache_key]))
            else:
                translations_to_do.append(text)
                indices_to_translate.append(i)
        
        # Skip checking for protected texts since we no longer use terminology protection
        protected_texts = None
        
        # Translate the texts
        translated_texts = None
        if translations_to_do:
            if protected_texts:
                # Use protected texts for translation
                texts_to_translate = protected_texts
            else:
                # Use original texts
                texts_to_translate = translations_to_do
            
            # 在线程池环境中使用异步可能导致问题
            # 直接使用同步批量翻译方法，避免"Timeout context manager should be used inside a task"错误
            try:
                # 尝试使用标准的同步翻译方法
                translated_texts = self.translator.translate_batch(texts_to_translate)
            except Exception as e:
                logger.error(f"标准翻译方法失败: {e}")
                # 如果失败，尝试逐个翻译文本（最慢但最安全的方法）
                translated_texts = []
                for text in texts_to_translate:
                    try:
                        # 单个文本翻译通常更可靠
                        result = self.translator.translate_text(text)
                        translated_texts.append(result)
                    except Exception as text_e:
                        logger.error(f"单个文本翻译失败: {text_e}")
                        # 如果翻译失败，返回原文
                        translated_texts.append(text)
            
            # Restore terminology
            if protected_texts and self.term_extractor:
                translated_texts = [
                    self.term_extractor.restore_terminology(text) for text in translated_texts
                ]
            
            # Cache translations
            for i, text in enumerate(translations_to_do):
                if i < len(translated_texts):
                    self.translation_cache[text] = translated_texts[i]
        
        # Combine cached and new translations
        all_translated_texts = [None] * len(original_texts)
        
        # Fill in cached translations
        for idx, translation in cached_translations:
            all_translated_texts[idx] = translation
        
        # Fill in new translations
        for i, orig_idx in enumerate(indices_to_translate):
            if i < len(translated_texts):
                all_translated_texts[orig_idx] = translated_texts[i]
        
        # Save translated texts
        translated_file = f"{batch_dir}/translated.txt"
        with open(translated_file, 'w', encoding='utf-8') as f:
            f.write('\n---\n'.join(all_translated_texts))
        
        # Also create parallel text file
        parallel_file = f"{batch_dir}/parallel.txt"
        with open(parallel_file, 'w', encoding='utf-8') as f:
            for i, (orig, trans) in enumerate(zip(original_texts, all_translated_texts)):
                f.write(f"=== Segment {i+1} ===\n")
                f.write(f"Original: {orig}\n")
                f.write(f"Translated: {trans}\n\n")
        
        # Save batch status
        batch_status = {
            "batch_id": batch_key,
            "item_id": item_id,
            "batch_number": batch_id,
            "segments_count": len(original_texts),
            "chars_count": sum(len(text) for text in original_texts),
            "translated_chars": sum(len(text) for text in all_translated_texts if text),
            "extraction_completed": True,
            "protection_applied": True if protected_texts else False,
            "translation_completed": True
        }
        
        if self.checkpoint_manager:
            self.checkpoint_manager.save_batch_status(batch_key, batch_status)
        
        # Update translated segment count
        with self.lock:
            self.translated_segments += len(original_texts)
            self.translated_chars += sum(len(text) for text in all_translated_texts if text)
        
        # Also save to standalone batch file
        if self.content_manager:
            self.content_manager.save_batch_standalone(
                item_id, batch_id, original_texts, all_translated_texts
            )
        
        logger.debug(f"Successfully translated batch {batch_key}")
        return True
        
    except Exception as e:
        logger.error(f"Error translating batch {batch_key}: {str(e)}")
        return False

def translate_epub(self, input_path, output_path, force_restart=False, local_only=False):
    """Translate an EPUB file from input_path and save to output_path.
    
    Args:
        input_path: Path to input EPUB file
        output_path: Path to save translated EPUB file
        force_restart: Whether to force restart translation (ignore checkpoints)
    
    Returns:
        Dictionary with translation statistics
    """
    self.force_restart = force_restart
    start_time = time.time()
    
    # Initialize checkpoint and progress tracking if supported
    if CHECKPOINT_SUPPORT:
        self.checkpoint_manager = CheckpointManager(input_path, output_path, self.config)
        self.progress_tracker = ProgressTracker(self.checkpoint_manager)
        self.content_manager = ContentManager(self.checkpoint_manager.workdir)
        
        # Set up progress tracker
        self.progress_tracker.setup(self.checkpoint_manager.workdir)
        
        # Check for existing checkpoint
        if not force_restart:
            checkpoint_exists, valid = self.checkpoint_manager.check_existing_checkpoint()
            if checkpoint_exists and valid:
                logger.info("Found valid checkpoint, resuming translation")
                self.progress_tracker._print_progress(
                    f"Resuming translation from {self.checkpoint_manager.state['total_progress']:.1f}% completion", 
                    newline=True
                )
                # Restore translation cache if available
                if os.path.exists(f"{self.checkpoint_manager.workdir}/translation_cache.json"):
                    try:
                        with open(f"{self.checkpoint_manager.workdir}/translation_cache.json", 'r', encoding='utf-8') as f:
                            self.translation_cache = json.load(f)
                        logger.info(f"Restored {len(self.translation_cache)} cached translations")
                    except Exception as e:
                        logger.error(f"Error restoring translation cache: {e}")
            elif checkpoint_exists and not valid:
                logger.warning("Found invalid checkpoint, starting fresh translation")
                self.checkpoint_manager.clear_checkpoint()
    
    logger.info(f"Loading EPUB file: {input_path}")
    if self.progress_tracker:
        self.progress_tracker.start_phase("preprocessing", f"Loading EPUB file: {input_path}")
    try:
        book = epub.read_epub(input_path)
        
        # Create a deep copy to avoid modifying the original
        translated_book = copy.deepcopy(book)
        
        # Extract metadata we want to preserve
        from epub_translator.epub_processor_utils import _extract_metadata
        metadata = _extract_metadata(self, book)
        
        # Save original metadata if we have content manager
        if self.content_manager:
            self.content_manager.save_metadata(metadata)
        
        # Get all HTML content items
        html_items = []
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                html_items.append(item)
        
        # Update preprocessing progress
        if self.progress_tracker:
            self.progress_tracker.update_preprocessing_progress(
                items_processed=0,
                items_total=len(html_items)
            )
            
        # Update checkpoint with HTML items count
        if self.checkpoint_manager:
            self.checkpoint_manager.update_translation_phase(
                items_total=len(html_items)
            )
    
        # Process terminology if auto-extraction is enabled
        # Check if we've already completed terminology extraction from checkpoint
        terminology_completed = False
        if (self.checkpoint_manager and not self.force_restart and 
            self.checkpoint_manager.state["phases"]["terminology"]["completed"]):
            terminology_completed = True
            terms_count = self.checkpoint_manager.state["phases"]["terminology"]["terms_count"]
            logger.info(f"Skipping terminology extraction (already completed with {terms_count} terms)")
            if self.progress_tracker:
                self.progress_tracker.update_terminology_progress(
                    terms_count=terms_count,
                    is_completed=True
                )
        
        if self.auto_extract_terms and not terminology_completed:
            if self.progress_tracker:
                self.progress_tracker.start_phase("terminology", "Auto-extracting terminology from EPUB content")
            
            logger.info("Auto-extracting terminology from EPUB content")
            from epub_translator.epub_processor_utils import _dummy_extract_terminology
            term_count = _dummy_extract_terminology(self, html_items)
            
            # Save terminology to file if we have content manager
            if self.content_manager and hasattr(self.term_extractor, 'terminology'):
                terms_file = self.content_manager.save_terminology(
                    self.term_extractor.terminology,
                    filename="terms.csv"
                )
                # Update checkpoint with terminology information
                if self.checkpoint_manager:
                    self.checkpoint_manager.update_terminology_phase(
                        completed=True,
                        terms_file=terms_file,
                        terms_count=len(self.term_extractor.terminology)
                    )
            
            if self.progress_tracker:
                self.progress_tracker.update_terminology_progress(
                    terms_count=term_count if term_count else 0,
                    is_completed=True
                )
    
        # Mark preprocessing phase as completed
        if self.checkpoint_manager:
            self.checkpoint_manager.update_preprocessing_phase(
                completed=True,
                items_total=len(html_items),
                items_processed=len(html_items)
            )
        
        if self.progress_tracker:
            self.progress_tracker.update_preprocessing_progress(
                items_processed=len(html_items),
                items_total=len(html_items),
                is_completed=True
            )
            self.progress_tracker.start_phase("translation", f"Translating EPUB content using {self.max_workers} parallel workers")
            
        # NOW it's safe to use DeepSeek API - enable it after all preparation is complete
        if self.translator and hasattr(self.translator, 'enable_api'):
            logger.info("Enabling DeepSeek API now that all preprocessing is complete")
            self.translator.enable_api()
        
        # Check if we need to restart from a specific point based on checkpoint
        completed_items = []
        if (self.checkpoint_manager and not self.force_restart and 
            self.checkpoint_manager.state["phases"]["translation"].get("completed_items")):
            completed_items = self.checkpoint_manager.state["phases"]["translation"]["completed_items"]
            logger.info(f"Resuming translation: {len(completed_items)}/{len(html_items)} items already completed")
        
        # Translate content with progress reporting
        logger.info(f"Translating EPUB content using {self.max_workers} parallel workers")
        
        # Use ThreadPoolExecutor to parallelize translation
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            results = {}
            
            # Submit translation tasks for non-completed items
            for item in html_items:
                item_id = item.get_id()
                if item_id not in completed_items:
                    future = executor.submit(
                        _translate_item_parallel, 
                        self, 
                        item, 
                        workdir=self.checkpoint_manager.workdir if self.checkpoint_manager else None
                    )
                    futures[future] = item_id
                else:
                    # For completed items, try to load from workdir
                    if self.checkpoint_manager:
                        item_dir = f"{self.checkpoint_manager.workdir}/html_items/{item_id.replace('/', '_')}"
                        translated_path = f"{item_dir}/translated.html"
                        if os.path.exists(translated_path):
                            try:
                                with open(translated_path, 'rb') as f:
                                    content = f.read()
                                
                                # Create a new item for the translated book
                                translated_item = epub.EpubHtml(
                                    uid=item.get_id(),
                                    file_name=item.get_name(),
                                    media_type="application/xhtml+xml",
                                    content=content
                                )
                                # Copy properties
                                translated_item.properties = item.properties
                                results[item_id] = translated_item
                                logger.info(f"Loaded translated item {item_id} from checkpoint")
                            except Exception as e:
                                logger.error(f"Error loading translated item {item_id}: {e}")
                                # If error loading, translate it again
                                future = executor.submit(
                                    _translate_item_parallel, 
                                    self, 
                                    item, 
                                    workdir=self.checkpoint_manager.workdir if self.checkpoint_manager else None
                                )
                                futures[future] = item_id
            
            # Initialize progress tracking
            if self.progress_tracker:
                self.progress_tracker.update_translation_progress(
                    translated_segments=self.translated_segments,
                    total_segments=self.total_segments,
                    translated_chars=self.translated_chars,
                    total_chars=self.total_chars,
                )
            
            # Monitor progress
            if futures:
                # Use tqdm progress bar or our custom progress tracker
                with tqdm(total=len(futures), desc="Translating chapters") as pbar:
                    for future in as_completed(futures):
                        item_id = futures[future]
                        try:
                            results[item_id] = future.result()
                            pbar.update(1)
                            
                            # Update list of completed items in checkpoint
                            if self.checkpoint_manager:
                                completed_list = self.checkpoint_manager.state["phases"]["translation"].get("completed_items", [])
                                if item_id not in completed_list:
                                    completed_list.append(item_id)
                                    self.checkpoint_manager.update_translation_phase(
                                        completed_items=completed_list,
                                        current_item=None,
                                        item_progress=0.0
                                    )
                            
                            # Save translation cache periodically
                            if self.checkpoint_manager and self.translation_cache:
                                if len(self.translation_cache) % 100 == 0:
                                    from epub_translator.epub_processor_utils import _save_translation_cache
                                    _save_translation_cache(self)
                            
                        except Exception as e:
                            logger.error(f"Error translating item {item_id}: {str(e)}")
                            pbar.update(1)
            
            # Add translated items to the book
            for item in html_items:
                item_id = item.get_id()
                if item_id in results and results[item_id]:
                    translated_book.add_item(results[item_id])
            
            # Mark translation phase as completed
            if self.progress_tracker:
                self.progress_tracker.update_translation_progress(
                    translated_segments=self.translated_segments,
                    total_segments=self.total_segments,
                    translated_chars=self.translated_chars,
                    total_chars=self.total_chars,
                    is_completed=True
                )
            
            if self.checkpoint_manager:
                self.checkpoint_manager.update_translation_phase(
                    completed=True,
                    translated_segments=self.translated_segments,
                    total_segments=self.total_segments,
                    translated_chars=self.translated_chars,
                    total_chars=self.total_chars
                )
    
        # Start postprocessing phase
        if self.progress_tracker:
            self.progress_tracker.start_phase("postprocessing", "Applying final processing to translated content")
        
        # Set metadata in translated book
        from epub_translator.epub_processor_utils import _set_metadata
        _set_metadata(self, translated_book, metadata)
        
        # Save translated metadata if we have content manager
        if self.content_manager:
            self.content_manager.save_metadata(metadata, is_translated=True)
        
        # Write the translated book
        logger.info(f"Writing translated EPUB to: {output_path}")
        epub.write_epub(output_path, translated_book)
        
        # Mark postprocessing as completed
        if self.progress_tracker:
            self.progress_tracker.update_postprocessing_progress(is_completed=True)
        
        if self.checkpoint_manager:
            self.checkpoint_manager.update_postprocessing_phase(completed=True)
    
        # Create HTML report
        if self.progress_tracker:
            self.progress_tracker.create_html_report(self.checkpoint_manager.workdir)
        
        # Create content index
        if self.content_manager:
            self.content_manager.create_html_index()
        
        # Save final translation cache
        from epub_translator.epub_processor_utils import _save_translation_cache
        _save_translation_cache(self)
        
        # Return statistics
        end_time = time.time()
        processing_time = end_time - start_time
        chars_per_second = self.translated_chars / processing_time if processing_time > 0 else 0
        
        stats = {
            'total_chars': self.total_chars,
            'total_segments': self.total_segments,
            'translated_chars': self.translated_chars,
            'translated_segments': self.translated_segments,
            'processing_time': processing_time,
            'chars_per_second': chars_per_second
        }
        
        logger.info(f"Translation complete in {processing_time:.2f} seconds")
        logger.info(f"Processing speed: {chars_per_second:.2f} characters per second")
        logger.info(f"Statistics: {stats}")
        
        if self.progress_tracker:
            self.progress_tracker._print_progress(f"Translation complete!", newline=True)
            
            if self.checkpoint_manager:
                self.progress_tracker._print_progress(
                    f"Content and reports available in: {self.checkpoint_manager.workdir}",
                    newline=True
                )
        
        return stats
        
    except Exception as e:
        logger.error(f"Error during translation: {str(e)}", exc_info=True)
        # Save checkpoint before exiting
        if self.checkpoint_manager:
            self.checkpoint_manager.save_checkpoint()
        raise

def _translate_item_parallel(self, item, workdir=None):
    """Translate an EPUB HTML item in parallel.
    
    Args:
        item: ebooklib.epub.EpubHtml item to translate
        workdir: Working directory for content files (optional)
    
    Returns:
        Translated EpubHtml item
    """
    if self.checkpoint_manager and not self.force_restart:
        # Check if we have a checkpoint for this item
        batch_info = self.checkpoint_manager.load_batch_info(item.get_id())
        if batch_info and batch_info.get("completed", False):
            logger.info(f"Skipping item {item.get_id()} (already completed)")
            
            # Try to load the translated item from file
            if workdir:
                item_dir = f"{workdir}/html_items/{item.get_id().replace('/', '_')}"
                translated_path = f"{item_dir}/translated.html"
                if os.path.exists(translated_path):
                    try:
                        with open(translated_path, 'rb') as f:
                            content = f.read()
                        
                        # Create a new item for the translated book
                        translated_item = epub.EpubHtml(
                            uid=item.get_id(),
                            file_name=item.get_name(),
                            media_type="application/xhtml+xml",
                            content=content
                        )
                        # Copy properties
                        translated_item.properties = item.properties
                        return translated_item
                    except Exception as e:
                        logger.error(f"Error loading translated item {item.get_id()}: {e}")
                        # Continue with normal translation
    
    item_id = item.get_id()
    logger.debug(f"Translating item: {item_id}")
    
    # Update checkpoint and progress if available
    if self.checkpoint_manager:
        self.checkpoint_manager.update_translation_phase(
            current_item=item_id,
            item_progress=0.0
        )
    
    try:
        # Get content and create BeautifulSoup object
        content = item.get_content().decode('utf-8')
        soup = BeautifulSoup(content, 'html.parser')
        
        # Save original HTML and chapter content if we have a content manager
        item_dir = None
        if self.content_manager:
            item_dir = self.content_manager.save_html_item(item)
            # Extract chapter title from content for better organization
            chapter_title = None
            try:
                title_tag = soup.find(['h1', 'h2', 'h3', 'title'])
                if title_tag:
                    chapter_title = title_tag.get_text().strip()
            except Exception:
                pass
            # Save original chapter content for easy access
            self.content_manager.save_chapter_content(item, chapter_title=chapter_title, is_translated=False)
        
        # Find all text nodes that need translation
        from epub_translator.epub_processor_utils import _extract_translatable_segments
        translatable_segments = _extract_translatable_segments(self, soup)
        
        # 使用段落分割器来优化翻译批次
        optimized_segments = self.text_divider.optimize_segments(
            translatable_segments, 
            batch_size=self.batch_size,
            max_segment_length=self.chunk_size
        )
        
        # 创建段落感知的批次
        batches = self.text_divider.group_into_content_aware_batches(
            optimized_segments,
            batch_size=self.batch_size
        )
        
        # Save batch information for checkpointing
        batch_info = {
            "item_id": item_id,
            "total_segments": len(translatable_segments),
            "batch_size": self.batch_size,
            "batches_count": len(batches),
            "batches": [],
            "completed": False
        }
        
        for i, batch in enumerate(batches):
            batch_info["batches"].append({
                "batch_id": i,
                "segment_indices": list(range(i * self.batch_size, min((i + 1) * self.batch_size, len(translatable_segments)))),
                "completed": False
            })
        
        # Save initial batch info
        if self.checkpoint_manager:
            self.checkpoint_manager.save_batch_info(item_id, batch_info)
        
        # Process batches - either in parallel or sequentially
        if len(batches) > 5:
            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(batches))) as executor:
                # Submit all batch translation tasks
                futures = []
                for i, batch in enumerate(batches):
                    futures.append(executor.submit(
                        _translate_batch, 
                        self,
                        batch,
                        item_dir=item_dir,
                        item_id=item_id,
                        batch_id=i
                    ))
                
                # Track completion
                completed_count = 0
                
                # Wait for all to complete
                for i, future in enumerate(as_completed(futures)):
                    try:
                        future.result()
                        completed_count += 1
                        
                        # Update batch info
                        if self.checkpoint_manager:
                            batch_info["batches"][i]["completed"] = True
                            self.checkpoint_manager.save_batch_info(item_id, batch_info)
                        
                        # Update progress
                        if self.progress_tracker:
                            # Calculate item progress
                            item_progress = (completed_count / len(batches)) * 100
                            
                            # Update translation progress
                            self.progress_tracker.update_translation_progress(
                                translated_segments=self.translated_segments,
                                total_segments=self.total_segments,
                                translated_chars=self.translated_chars,
                                total_chars=self.total_chars,
                                current_item=item_id,
                                item_progress=item_progress
                            )
                        
                        # Update checkpoint
                        if self.checkpoint_manager:
                            self.checkpoint_manager.update_translation_phase(
                                translated_segments=self.translated_segments,
                                total_segments=self.total_segments,
                                translated_chars=self.translated_chars,
                                total_chars=self.total_chars,
                                current_item=item_id,
                                item_progress=item_progress
                            )
                            
                    except Exception as e:
                        logger.error(f"Error in batch translation: {str(e)}")
        else:
            # For small documents, process sequentially
            for i, batch in enumerate(batches):
                _translate_batch(
                    self,
                    batch,
                    item_dir=item_dir,
                    item_id=item_id,
                    batch_id=i
                )
                
                # Update batch info
                if self.checkpoint_manager:
                    batch_info["batches"][i]["completed"] = True
                    self.checkpoint_manager.save_batch_info(item_id, batch_info)
                
                # Update progress
                if self.progress_tracker:
                    # Calculate item progress
                    item_progress = ((i + 1) / len(batches)) * 100
                    
                    # Update translation progress
                    self.progress_tracker.update_translation_progress(
                        translated_segments=self.translated_segments,
                        total_segments=self.total_segments,
                        translated_chars=self.translated_chars,
                        total_chars=self.total_chars,
                        current_item=item_id,
                        item_progress=item_progress
                    )
                
                # Update checkpoint
                if self.checkpoint_manager:
                    self.checkpoint_manager.update_translation_phase(
                        translated_segments=self.translated_segments,
                        total_segments=self.total_segments,
                        translated_chars=self.translated_chars,
                        total_chars=self.total_chars,
                        current_item=item_id,
                        item_progress=item_progress
                    )
        
        # Update the content with translated text
        translated_content = str(soup)
        
        # Create a new item for the translated book
        translated_item = epub.EpubHtml(
            uid=item.get_id(),
            file_name=item.get_name(),
            media_type="application/xhtml+xml",
            content=translated_content.encode('utf-8')
        )
        
        # Copy properties
        translated_item.properties = item.properties
        
        # Save translated HTML and chapter content if we have a content manager
        if self.content_manager:
            self.content_manager.save_html_item(translated_item, is_translated=True)
            
            # Extract chapter title from content for better organization
            chapter_title = None
            try:
                translated_soup = BeautifulSoup(translated_content, 'html.parser')
                title_tag = translated_soup.find(['h1', 'h2', 'h3', 'title'])
                if title_tag:
                    chapter_title = title_tag.get_text().strip()
            except Exception:
                pass
            
            # Save translated chapter content for easy access
            self.content_manager.save_chapter_content(translated_item, chapter_title=chapter_title, is_translated=True)
        
        # Mark item as completed in batch info
        if self.checkpoint_manager:
            batch_info["completed"] = True
            self.checkpoint_manager.save_batch_info(item_id, batch_info)
        
        return translated_item
    
    except Exception as e:
        logger.error(f"Error translating item {item_id}: {str(e)}", exc_info=True)
        return None

def _translate_batch(self, segments, item_dir=None, item_id=None, batch_id=None):
    """Translate a batch of segments.
    
    Args:
        segments: List of tuples (element, attribute, text)
        item_dir: Directory for HTML item content (optional)
        item_id: HTML item ID (optional)
        batch_id: Batch ID (optional)
    """
    try:
        # Extract text for translation
        texts = [segment[2] for segment in segments]
        
        # Skip if no texts to translate
        if not texts:
            return
        
        # Check cache for translations
        translations_to_do = []
        indices_to_translate = []
        cached_translations = []
        
        for i, text in enumerate(texts):
            cache_key = text
            if cache_key in self.translation_cache:
                cached_translations.append((i, self.translation_cache[cache_key]))
            else:
                translations_to_do.append(text)
                indices_to_translate.append(i)
        
        # Save original batch content if we have a content manager
        if self.content_manager and item_dir and item_id is not None and batch_id is not None:
            self.content_manager.save_batch(item_id, batch_id, segments)
        
        # Directly translate the original texts without terminology protection
        protected_texts = None
        if translations_to_do:
            # 在线程池环境中使用异步可能导致问题
            # 直接使用同步批量翻译方法，避免"Timeout context manager should be used inside a task"错误
            try:
                # 尝试使用标准的同步翻译方法
                translated_texts = self.translator.translate_batch(translations_to_do)
            except Exception as e:
                logger.error(f"标准翻译方法失败: {e}")
                # 如果失败，尝试逐个翻译文本（最慢但最安全的方法）
                translated_texts = []
                for text in translations_to_do:
                    try:
                        # 单个文本翻译通常更可靠
                        result = self.translator.translate_text(text)
                        translated_texts.append(result)
                    except Exception as text_e:
                        logger.error(f"单个文本翻译失败: {text_e}")
                        # 如果翻译失败，返回原文
                        translated_texts.append(text)
            
            # Cache translations
            for i, text in enumerate(translations_to_do):
                if i < len(translated_texts):
                    self.translation_cache[text] = translated_texts[i]
        else:
            translated_texts = []
        
        # Update segments with translations
        # First, handle cached translations
        for idx, translation in cached_translations:
            if idx < len(segments):
                element, attribute, original_text = segments[idx]
                from epub_translator.epub_processor_utils import _update_segment
                _update_segment(self, element, attribute, translation)
        
        # Then, handle new translations
        for i, orig_idx in enumerate(indices_to_translate):
            if i < len(translated_texts) and orig_idx < len(segments):
                element, attribute, original_text = segments[orig_idx]
                from epub_translator.epub_processor_utils import _update_segment
                _update_segment(self, element, attribute, translated_texts[i])
        
        # Save translated batch content if we have a content manager
        if self.content_manager and item_dir and item_id is not None and batch_id is not None:
            # Collect all translated texts (both cached and new)
            all_translated_texts = [None] * len(texts)
            
            # Fill in cached translations
            for idx, translation in cached_translations:
                all_translated_texts[idx] = translation
            
            # Fill in new translations
            for i, orig_idx in enumerate(indices_to_translate):
                if i < len(translated_texts):
                    all_translated_texts[orig_idx] = translated_texts[i]
            
            # Save batch to detailed location
            self.content_manager.save_batch(
                item_id, batch_id, segments, 
                translated_texts=all_translated_texts,
                protected_texts=protected_texts
            )
            
            # Also save to standalone location for easier access
            self.content_manager.save_batch_standalone(
                item_id, batch_id, texts, all_translated_texts
            )
    
    except Exception as e:
        logger.error(f"Error translating batch: {str(e)}", exc_info=True)
        if item_id is not None and batch_id is not None:
            logger.error(f"Failed batch: item_id={item_id}, batch_id={batch_id}")
        raise
