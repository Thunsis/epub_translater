#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
EPUB extraction module for the EPUBProcessor class.
Handles extracting content from EPUB files, organizing into chapters,
dividing into batches, and preparing for translation.
"""

import os
import logging
import time
import re
import os
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub

# Configure logger
logger = logging.getLogger("epub_translator.epub_processor")

# Import cost estimator
try:
    from epub_translator.cost_estimator import estimate_api_cost, format_cost_estimate, DEBUG_COST_ESTIMATOR
    COST_ESTIMATOR_SUPPORT = True
    if DEBUG_COST_ESTIMATOR:
        logger.info("Cost estimator module loaded successfully")
except ImportError as e:
    logger.warning(f"Cost estimator module not found, cost estimation will be disabled: {e}")
    COST_ESTIMATOR_SUPPORT = False

def extract_and_prepare_content(self, input_path, output_path=None, force_restart=False):
    """Extract and prepare content for translation without actually translating.
    
    This method performs all local processing steps:
    1. Parse the EPUB file
    2. Extract content and structure
    3. Organize into chapters
    4. Divide into batches
    5. Prepare for translation
    
    Args:
        input_path: Path to input EPUB file
        output_path: Path to save translated EPUB file (optional, used for tracking)
        force_restart: Whether to force restart processing (ignore checkpoints)
        
    Returns:
        Dictionary with processing statistics
    """
    self.force_restart = force_restart
    start_time = time.time()
    
    # Initialize checkpoint and progress tracking if supported
    if hasattr(self, 'checkpoint_manager') and self.checkpoint_manager is None and CHECKPOINT_SUPPORT:
        self.checkpoint_manager = CheckpointManager(input_path, output_path, self.config)
        self.progress_tracker = ProgressTracker(self.checkpoint_manager)
        self.content_manager = ContentManager(self.checkpoint_manager.workdir)
        
        # Set up progress tracker
        self.progress_tracker.setup(self.checkpoint_manager.workdir)
        
        # Check for existing checkpoint
        if not force_restart:
            checkpoint_exists, valid = self.checkpoint_manager.check_existing_checkpoint()
            if checkpoint_exists and valid:
                logger.info("Found valid checkpoint, resuming preparation")
                
                # Load statistics from checkpoint
                try:
                    translation_phase = self.checkpoint_manager.state["phases"]["translation"]
                    self.total_segments = translation_phase.get("total_segments", 0)
                    self.total_chars = translation_phase.get("total_chars", 0)
                    self.translated_segments = translation_phase.get("translated_segments", 0)
                    self.translated_chars = translation_phase.get("translated_chars", 0)
                    logger.info(f"Loaded statistics from checkpoint: {self.total_segments} segments, {self.total_chars} characters")
                except Exception as e:
                    logger.error(f"Error loading statistics from checkpoint: {e}")
                
                self.progress_tracker._print_progress(
                    f"Resuming content preparation from checkpoint",
                    newline=True
                )
            elif checkpoint_exists and not valid:
                logger.warning("Found invalid checkpoint, starting fresh preparation")
                self.checkpoint_manager.clear_checkpoint()
    
    try:
        # Step 1: Parse the EPUB file
        if not self.checkpoint_manager or not self.checkpoint_manager.is_local_processing_step_completed("parsing_completed"):
            logger.info(f"Parsing EPUB file: {input_path}")
            if self.progress_tracker:
                self.progress_tracker._print_progress("Parsing EPUB file...", newline=True)
            
            book = epub.read_epub(input_path)
            
            # Mark parsing as completed
            if self.checkpoint_manager:
                self.checkpoint_manager.update_local_processing_phase("parsing_completed", True)
        else:
            logger.info("EPUB parsing already completed, skipping")
            book = epub.read_epub(input_path)
        
        # Step 2: Extract content
        if not self.checkpoint_manager or not self.checkpoint_manager.is_local_processing_step_completed("content_extraction_completed"):
            logger.info("Extracting content from EPUB")
            if self.progress_tracker:
                self.progress_tracker._print_progress("Extracting EPUB content...", newline=True)
            
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
            
            # Mark content extraction as completed
            if self.checkpoint_manager:
                self.checkpoint_manager.update_local_processing_phase("content_extraction_completed", True, 
                                                                     items_count=len(html_items))
        else:
            logger.info("Content extraction already completed, skipping")
            
            # Get saved HTML items count
            html_items_info = self.checkpoint_manager.get_local_processing_details("content_extraction_completed")
            html_items_count = html_items_info.get("items_count", 0)
            
            # Get HTML items anyway for further processing
            html_items = []
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    html_items.append(item)
            
            logger.info(f"Found {len(html_items)} HTML items (checkpoint reported {html_items_count})")
        
        # Step 3: Organize chapters
        if not self.checkpoint_manager or not self.checkpoint_manager.is_local_processing_step_completed("chapter_organization_completed"):
            logger.info("Organizing content into chapters")
            if self.progress_tracker:
                self.progress_tracker._print_progress("Organizing chapters...", newline=True)
            
            chapter_count = 0
            # Save each item as a chapter
            for item in html_items:
                if self.content_manager:
                    # Extract chapter title from content for better organization
                    content = item.get_content().decode('utf-8')
                    soup = BeautifulSoup(content, 'html.parser')
                    chapter_title = None
                    try:
                        title_tag = soup.find(['h1', 'h2', 'h3', 'title'])
                        if title_tag:
                            chapter_title = title_tag.get_text().strip()
                    except Exception:
                        pass
                    
                    # Save chapter content
                    self.content_manager.save_chapter_content(item, chapter_title=chapter_title, is_translated=False)
                    chapter_count += 1
            
            # Mark chapter organization as completed
            if self.checkpoint_manager:
                self.checkpoint_manager.update_local_processing_phase("chapter_organization_completed", True,
                                                                    chapter_count=chapter_count)
                
                # Create a done file in the chapters directory
                done_file_path = f"{self.checkpoint_manager.workdir}/chapters_original/chapters_completed.done"
                try:
                    with open(done_file_path, 'w', encoding='utf-8') as done_file:
                        done_file.write(f"Chapters organization successfully completed at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                        done_file.write(f"Total chapters: {chapter_count}\n")
                    logger.info(f"Created chapters completion marker: {done_file_path}")
                except Exception as e:
                    logger.error(f"Error creating chapters completion marker file: {e}")
        else:
            logger.info("Chapter organization already completed, skipping")
        
        # Step 4: Prepare batches for translation
        if not self.checkpoint_manager or not self.checkpoint_manager.is_local_processing_step_completed("batch_division_completed"):
            logger.info("Dividing content into batches for translation")
            if self.progress_tracker:
                self.progress_tracker._print_progress("Preparing translation batches...", newline=True)
            
            total_segments = 0
            total_batches = 0
            batch_details = {}
            
            # Process each HTML item to extract translatable segments and divide into batches
            for item in html_items:
                item_id = item.get_id()
                
                # Get content and create BeautifulSoup object
                content = item.get_content().decode('utf-8')
                soup = BeautifulSoup(content, 'html.parser')
                
                # Save HTML item
                if self.content_manager:
                    self.content_manager.save_html_item(item)
                
                # Extract translatable segments
                from epub_translator.epub_processor_utils import _extract_translatable_segments
                translatable_segments = _extract_translatable_segments(self, soup, item_id=item_id)
                total_segments += len(translatable_segments)
                
                # Calculate total characters in these segments
                segment_chars = sum(len(segment[2]) for segment in translatable_segments)
                self.total_chars += segment_chars
                
                # 使用段落优化的批处理方式
                # 首先优化分段以尊重段落边界
                optimized_segments = self.text_divider.optimize_segments(
                    translatable_segments, 
                    batch_size=self.batch_size,
                    max_segment_length=self.chunk_size
                )
                
                # 然后将优化后的段落分成批次
                batches = self.text_divider.group_into_content_aware_batches(
                    optimized_segments,
                    batch_size=self.batch_size
                )
                total_batches += len(batches)
                
                # Save batch information for later use
                batch_info = {
                    "item_id": item_id,
                    "total_segments": len(translatable_segments),
                    "batch_size": self.batch_size,
                    "batches_count": len(batches),
                    "batches": [],
                    "completed": False
                }
                
                # Process and save each batch's details
                for i, batch in enumerate(batches):
                    # Extract batch text
                    texts = [segment[2] for segment in batch]
                    
                    # Create unique batch identifier
                    batch_key = f"{item_id.replace('/', '_')}_{i:03d}"
                    
                    # Save batch texts
                    if self.content_manager:
                        self.content_manager.save_batch(item_id, i, batch)
                        self.content_manager.save_batch_standalone(item_id, i, texts)
                    
                        # Save batch details
                        if self.content_manager:
                            self.content_manager.save_batch(
                                item_id, i, batch
                            )
                    
                    # Save batch status
                    if self.checkpoint_manager:
                        batch_status = {
                            "batch_id": batch_key,
                            "item_id": item_id,
                            "batch_number": i,
                            "segments_count": len(batch),
                            "chars_count": sum(len(text) for text in texts),
                            "extraction_completed": True,
                            "protection_applied": True if self.term_extractor else False,
                            "translation_completed": False
                        }
                        self.checkpoint_manager.save_batch_status(batch_key, batch_status)
                    
                    # Update batch info
                    batch_info["batches"].append({
                        "batch_id": i,
                        "segment_indices": list(range(i * self.batch_size, min((i + 1) * self.batch_size, len(translatable_segments)))),
                        "completed": False,
                        "batch_key": batch_key
                    })
                
                # Save batch info
                if self.checkpoint_manager:
                    self.checkpoint_manager.save_batch_info(item_id, batch_info)
                
                # Add to batch details
                batch_details[item_id] = {
                    "batches_count": len(batches),
                    "segments_count": len(translatable_segments)
                }
            
            # Mark batch division as completed
            if self.checkpoint_manager:
                self.checkpoint_manager.update_local_processing_phase("batch_division_completed", True,
                                                                     total_segments=total_segments,
                                                                     total_batches=total_batches,
                                                                     batch_details=batch_details)
                
                # Update translation phase with segment statistics
                self.checkpoint_manager.update_translation_phase(
                    total_segments=total_segments,
                    translated_segments=0,
                    total_chars=self.total_chars,
                    translated_chars=0,
                    batches_total=total_batches,
                    batches_completed=0
                )
                
                # Create a done file in the batches directory
                done_file_path = f"{self.checkpoint_manager.workdir}/batches/batches_completed.done"
                try:
                    with open(done_file_path, 'w', encoding='utf-8') as done_file:
                        done_file.write(f"Batch division successfully completed at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                        done_file.write(f"Total segments: {total_segments}\n")
                        done_file.write(f"Total batches: {total_batches}\n")
                        done_file.write(f"Characters: {self.total_chars}\n")
                    logger.info(f"Created batch division completion marker: {done_file_path}")
                except Exception as e:
                    logger.error(f"Error creating batch division completion marker file: {e}")
        else:
            logger.info("Batch division already completed, skipping")
        
        # Mark translation preparation as completed
        if self.checkpoint_manager:
            self.checkpoint_manager.update_local_processing_phase("translation_preparation_completed", True)
        
        # Create content index
        if self.content_manager:
            self.content_manager.create_html_index()
            
        # 现在可以安全地启用DeepSeek API，但只在非local_only模式下
        if not self.local_only and self.translator and hasattr(self.translator, 'enable_api'):
            logger.info("启用DeepSeek API - 文件准备工作已完成")
            self.translator.enable_api()
        
        # 阶段2 (DeepSeek术语优化) 已从这里移除
        # 术语优化将在翻译阶段之前单独进行，不再在第一阶段执行
        
        # Return statistics
        end_time = time.time()
        preparation_time = end_time - start_time
        
        stats = {
            'total_segments': self.total_segments,
            'total_chars': self.total_chars,
            'preparation_time': preparation_time,
            'workdir': self.checkpoint_manager.workdir if self.checkpoint_manager else None
        }
        
        logger.info(f"Content preparation complete in {preparation_time:.2f} seconds")
        logger.info(f"Total segments: {self.total_segments}, Total characters: {self.total_chars}")
        
        if self.progress_tracker:
            # Force set total progress to 100% directly
            self.progress_tracker.total_progress = 100.0
            self.progress_tracker.phase_progresses["preprocessing"] = 100.0
            
            # Now print the completion message
            self.progress_tracker._print_progress(f"Content preparation complete!", newline=True)
            
            if self.checkpoint_manager:
                self.progress_tracker._print_progress(
                    f"Content and reports available in: {self.checkpoint_manager.workdir}",
                    newline=True
                )
        
        # Create a "done" file to explicitly mark successful completion
        if self.checkpoint_manager and self.checkpoint_manager.workdir:
            done_file_path = os.path.join(self.checkpoint_manager.workdir, "preparation_completed.done")
            try:
                with open(done_file_path, 'w', encoding='utf-8') as done_file:
                    done_file.write(f"EPUB Preparation successfully completed at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    done_file.write(f"Processing time: {preparation_time:.2f} seconds\n")
                    done_file.write(f"Total segments: {self.total_segments}\n")
                    done_file.write(f"Total characters: {self.total_chars}\n")
                    done_file.write(f"All processing steps completed without errors.\n")
                logger.info(f"Created preparation completion marker: {done_file_path}")
            except Exception as e:
                logger.error(f"Error creating completion marker file: {e}")
        
        # Estimate DeepSeek API costs for phases 2 and 3
        if COST_ESTIMATOR_SUPPORT and self.total_chars > 0:
            try:
                # Get DeepSeek model name from config or use default
                model = "deepseek-chat"
                if hasattr(self, 'config') and self.config:
                    model = self.config.get('deepseek', 'model', fallback="deepseek-chat")
                
                # Estimate API costs
                cost_estimate = estimate_api_cost(self.total_chars, model=model)
                cost_report = format_cost_estimate(cost_estimate)
                
                # Print cost estimate
                print("\n--- DeepSeek API Cost Estimate for Phases 2 & 3 ---")
                print(cost_report)
                
                # Save cost estimate to file
                if self.checkpoint_manager and self.checkpoint_manager.workdir:
                    cost_file_path = os.path.join(self.checkpoint_manager.workdir, "api_cost_estimate.txt")
                    try:
                        with open(cost_file_path, 'w', encoding='utf-8') as cost_file:
                            cost_file.write(f"DeepSeek API Cost Estimate generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                            cost_file.write(f"Total characters: {self.total_chars:,}\n")
                            cost_file.write(f"Model: {model}\n\n")
                            cost_file.write(cost_report)
                        logger.info(f"Saved API cost estimate to: {cost_file_path}")
                    except Exception as e:
                        logger.error(f"Error saving API cost estimate: {e}")
            except Exception as e:
                logger.error(f"Error estimating API costs: {e}", exc_info=True)
                print("\nFailed to estimate API costs. See log for details.")
        
        return stats
        
    except Exception as e:
        logger.error(f"Error during content preparation: {str(e)}", exc_info=True)
        # Save checkpoint before exiting
        if self.checkpoint_manager:
            self.checkpoint_manager.save_checkpoint()
        raise

# Add the missing import for CHECKPOINT_SUPPORT
try:
    from epub_translator.checkpoint_manager import CheckpointManager
    from epub_translator.progress_tracker import ProgressTracker
    from epub_translator.content_manager import ContentManager
    CHECKPOINT_SUPPORT = True
except ImportError:
    logger.warning("Checkpoint support modules not found, running without checkpoint capabilities")
    CHECKPOINT_SUPPORT = False
