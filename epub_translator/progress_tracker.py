#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Progress Tracker for EPUB Translator.
Provides detailed, multi-layered progress reporting for translation process.
"""

import os
import sys
import time
import logging
import shutil
import json
from datetime import datetime, timedelta

logger = logging.getLogger("epub_translator.progress_tracker")

class ProgressTracker:
    """Multi-layered progress tracker for translation process."""
    
    def __init__(self, checkpoint_manager=None):
        """Initialize progress tracker.
        
        Args:
            checkpoint_manager: CheckpointManager instance (optional)
        """
        self.checkpoint_manager = checkpoint_manager
        self.start_time = time.time()
        self.last_update_time = time.time()
        self.update_interval = 1.0  # Minimum seconds between progress updates
        
        # Progress state
        self.total_progress = 0.0
        self.phase_progresses = {
            "terminology": 0.0,
            "preprocessing": 0.0,
            "translation": 0.0,
            "postprocessing": 0.0
        }
        
        # Translation specific metrics
        self.translation_metrics = {
            "total_chars": 0,
            "translated_chars": 0,
            "total_segments": 0,
            "translated_segments": 0,
            "chars_per_second": 0.0,
            "estimated_remaining": None,
            "current_chapter": None,
            "chapter_progress": 0.0
        }
        
        # Terminal size
        self.terminal_width = self._get_terminal_width()
        
        # Progress log file
        self.log_file = None
        
    def _get_terminal_width(self):
        """Get terminal width.
        
        Returns:
            Terminal width
        """
        try:
            return shutil.get_terminal_size().columns
        except (AttributeError, ValueError, OSError):
            return 80  # Default width
    
    def setup(self, workdir=None):
        """Set up progress tracker.
        
        Args:
            workdir: Working directory (optional)
        """
        if workdir:
            os.makedirs(f"{workdir}/status", exist_ok=True)
            self.log_file = f"{workdir}/status/progress_log.txt"
            
            # Initialize log file
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write(f"EPUB Translation Progress Log\n")
                f.write(f"Started at: {datetime.now().isoformat()}\n")
                f.write("-" * 80 + "\n\n")
    
    def start_phase(self, phase, message=None):
        """Start a new processing phase.
        
        Args:
            phase: Phase name
            message: Message to display (optional)
        """
        if message:
            logger.info(message)
            self._log_progress(f"{message}")
            
        self._print_progress(f"Starting {phase} phase...", newline=True)
    
    def complete_phase(self, phase, message=None):
        """Complete a processing phase.
        
        Args:
            phase: Phase name
            message: Message to display (optional)
        """
        self.phase_progresses[phase] = 100.0
        
        if message:
            logger.info(message)
            self._log_progress(f"{message}")
            
        self._print_progress(f"Completed {phase} phase", newline=True)
    
    def update_terminology_progress(self, terms_count, is_completed=False):
        """Update terminology extraction progress.
        
        Args:
            terms_count: Number of terms extracted
            is_completed: Whether extraction is completed
        """
        # Update phase progress
        if is_completed:
            self.phase_progresses["terminology"] = 100.0
        else:
            # Terminology progress is difficult to measure, so we use a simple approach
            self.phase_progresses["terminology"] = min(90.0, terms_count / 5.0)
        
        # Update checkpoint
        if self.checkpoint_manager:
            self.checkpoint_manager.update_terminology_phase(
                completed=is_completed,
                terms_count=terms_count
            )
        
        # Display progress
        self._update_total_progress()
        
        if is_completed:
            self._print_progress(f"Terminology extraction complete: {terms_count} terms extracted", newline=True)
        else:
            self._print_progress(f"Terminology extraction: {terms_count} terms found so far...")
    
    def update_preprocessing_progress(self, items_processed, items_total, is_completed=False):
        """Update preprocessing progress.
        
        Args:
            items_processed: Number of items processed
            items_total: Total number of items
            is_completed: Whether preprocessing is completed
        """
        # Update phase progress
        if is_completed:
            self.phase_progresses["preprocessing"] = 100.0
        else:
            self.phase_progresses["preprocessing"] = (items_processed / max(1, items_total)) * 100.0
        
        # Update checkpoint
        if self.checkpoint_manager:
            self.checkpoint_manager.update_preprocessing_phase(
                completed=is_completed,
                items_total=items_total,
                items_processed=items_processed
            )
        
        # Display progress
        self._update_total_progress()
        
        if is_completed:
            self._print_progress(f"Preprocessing complete: {items_processed}/{items_total} items processed", newline=True)
        else:
            self._print_progress(f"Preprocessing: {items_processed}/{items_total} items processed...")
    
    def update_translation_progress(self, translated_segments, total_segments,
                                   translated_chars, total_chars,
                                   current_item=None, item_progress=0.0,
                                   is_completed=False):
        """Update translation progress.
        
        Args:
            translated_segments: Number of translated segments
            total_segments: Total number of segments
            translated_chars: Number of translated characters
            total_chars: Total number of characters
            current_item: Current item being translated (optional)
            item_progress: Progress of current item (0-100) (optional)
            is_completed: Whether translation is completed
        """
        # Update metrics
        self.translation_metrics["translated_segments"] = translated_segments
        self.translation_metrics["total_segments"] = total_segments
        self.translation_metrics["translated_chars"] = translated_chars
        self.translation_metrics["total_chars"] = total_chars
        self.translation_metrics["current_chapter"] = current_item
        self.translation_metrics["chapter_progress"] = item_progress
        
        # Calculate chars per second
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            self.translation_metrics["chars_per_second"] = translated_chars / elapsed
        
        # Estimate remaining time
        if translated_chars > 0 and translated_chars < total_chars:
            chars_remaining = total_chars - translated_chars
            seconds_per_char = elapsed / translated_chars
            seconds_remaining = chars_remaining * seconds_per_char
            self.translation_metrics["estimated_remaining"] = seconds_remaining
        else:
            self.translation_metrics["estimated_remaining"] = None
        
        # Update phase progress
        if is_completed:
            self.phase_progresses["translation"] = 100.0
        else:
            self.phase_progresses["translation"] = (translated_chars / max(1, total_chars)) * 100.0
        
        # Update checkpoint
        if self.checkpoint_manager:
            self.checkpoint_manager.update_translation_phase(
                completed=is_completed,
                translated_segments=translated_segments,
                total_segments=total_segments,
                translated_chars=translated_chars,
                total_chars=total_chars,
                current_item=current_item,
                item_progress=item_progress
            )
        
        # Display progress
        self._update_total_progress()
        
        # Only display if enough time has passed since last update
        if is_completed or time.time() - self.last_update_time >= self.update_interval:
            self.last_update_time = time.time()
            
            # Format progress message
            if is_completed:
                self._print_progress(f"Translation complete", newline=True)
                self._print_details()
            else:
                self._print_progress(f"Translating: {translated_chars:,}/{total_chars:,} chars ({self.phase_progresses['translation']:.1f}%)")
                self._print_details()
    
    def update_postprocessing_progress(self, progress=0.0, is_completed=False):
        """Update postprocessing progress.
        
        Args:
            progress: Progress percentage (0-100)
            is_completed: Whether postprocessing is completed
        """
        # Update phase progress
        if is_completed:
            self.phase_progresses["postprocessing"] = 100.0
        else:
            self.phase_progresses["postprocessing"] = progress
        
        # Update checkpoint
        if self.checkpoint_manager:
            self.checkpoint_manager.update_postprocessing_phase(completed=is_completed)
        
        # Display progress
        self._update_total_progress()
        
        if is_completed:
            self._print_progress(f"Postprocessing complete", newline=True)
        else:
            self._print_progress(f"Postprocessing: {progress:.1f}%...")
    
    def _update_total_progress(self):
        """Update total progress based on phase progress."""
        # Weight for each phase
        weights = {
            "terminology": 0.05,
            "preprocessing": 0.05,
            "translation": 0.85,
            "postprocessing": 0.05
        }
        
        # Calculate weighted progress
        weighted_progress = sum(
            self.phase_progresses[phase] * weights[phase] / 100.0
            for phase in self.phase_progresses
        )
        
        self.total_progress = weighted_progress * 100.0
    
    def _format_time(self, seconds):
        """Format time in seconds to human-readable string.
        
        Args:
            seconds: Time in seconds
            
        Returns:
            Formatted time string
        """
        if seconds is None:
            return "unknown"
            
        if seconds < 60:
            return f"{seconds:.1f}秒"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}分钟"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}小时"
    
    def _print_progress(self, message, newline=False):
        """Print progress message with progress bar.
        
        Args:
            message: Message to display
            newline: Whether to add a newline after the message
        """
        # Update terminal width
        self.terminal_width = self._get_terminal_width()
        
        # Force progress value for preparation phase
        if "Content preparation complete" in message:
            # Force 100% completion for everything
            self.phase_progresses["preprocessing"] = 100.0
            self.total_progress = 100.0  # Direct override of total progress
        elif "Parsing EPUB file" in message:
            self.phase_progresses["preprocessing"] = 25.0
            self.total_progress = 25.0  # Direct override
        elif "Extracting EPUB content" in message:
            self.phase_progresses["preprocessing"] = 50.0
            self.total_progress = 50.0  # Direct override
        elif "Organizing chapters" in message:
            self.phase_progresses["preprocessing"] = 75.0
            self.total_progress = 75.0  # Direct override
        elif "Preparing translation batches" in message:
            self.phase_progresses["preprocessing"] = 90.0
            self.total_progress = 90.0  # Direct override
        
        # Create progress bar
        bar_width = min(50, max(10, self.terminal_width - 30))
        filled_width = int(self.total_progress / 100.0 * bar_width)
        bar = f"[{'=' * filled_width}{'-' * (bar_width - filled_width)}] {self.total_progress:.1f}%"
        
        # Format output with phase-appropriate prefix
        if self.phase_progresses["terminology"] < 100.0 or self.phase_progresses["preprocessing"] < 100.0:
            prefix = "EPUB处理进度"  # Processing progress
        else:
            prefix = "EPUB翻译进度"  # Translation progress
            
        output = f"{prefix} {bar} | {message}"
        
        # Clear line and print progress
        if newline:
            print(output)
        else:
            print(f"\r{output}", end="")
            sys.stdout.flush()
        
        # Log progress
        self._log_progress(output)
    
    def _print_details(self):
        """Print detailed translation metrics."""
        # Only print details if we're in translation phase
        if self.phase_progresses["terminology"] == 100.0 and self.phase_progresses["preprocessing"] == 100.0:
            # Get metrics
            translated_chars = self.translation_metrics["translated_chars"]
            total_chars = self.translation_metrics["total_chars"]
            translated_segments = self.translation_metrics["translated_segments"]
            total_segments = self.translation_metrics["total_segments"]
            chars_per_second = self.translation_metrics["chars_per_second"]
            estimated_remaining = self.translation_metrics["estimated_remaining"]
            current_chapter = self.translation_metrics["current_chapter"]
            chapter_progress = self.translation_metrics["chapter_progress"]
            
            # Calculate words per second (approximate)
            words_per_second = chars_per_second / 5.0
            
            # Format details
            details = [
                f"  已翻译: {translated_chars:,}/{total_chars:,} 字符 | {translated_segments:,}/{total_segments:,} 段落",
                f"  翻译速度: {chars_per_second:.1f} 字符/秒 | ~{words_per_second:.1f} 词/秒",
                f"  预计剩余时间: {self._format_time(estimated_remaining)}"
            ]
            
            if current_chapter:
                details.insert(0, f"  当前章节: {current_chapter} [{chapter_progress:.1f}%]")
            
            # Print details
            for line in details:
                print(f"\r{' ' * self.terminal_width}\r{line}")
            
            # Move cursor back to progress line
            print(f"\r", end="")
            sys.stdout.flush()
            
            # Log details
            for line in details:
                self._log_progress(line)
    
    def _log_progress(self, message):
        """Log progress message to file.
        
        Args:
            message: Message to log
        """
        if self.log_file:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(f"[{datetime.now().isoformat()}] {message}\n")
            except Exception as e:
                logger.error(f"Error logging progress: {e}")
    
    def create_html_report(self, workdir):
        """Create HTML report of translation progress.
        
        Args:
            workdir: Working directory
        """
        if not workdir:
            return
        
        html_file = f"{workdir}/index.html"
        
        # Get progress information
        progress_info = {
            "total_progress": self.total_progress,
            "phase_progresses": self.phase_progresses,
            "translation_metrics": self.translation_metrics,
            "elapsed_time": time.time() - self.start_time,
            "generated_at": datetime.now().isoformat()
        }
        
        # Create HTML content
        html_content = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>EPUB翻译报告</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    margin: 0;
                    padding: 20px;
                    color: #333;
                }}
                h1, h2, h3 {{
                    color: #2c3e50;
                }}
                .container {{
                    max-width: 1000px;
                    margin: 0 auto;
                }}
                .progress-bar {{
                    height: 20px;
                    background-color: #ecf0f1;
                    border-radius: 4px;
                    margin-bottom: 10px;
                    overflow: hidden;
                }}
                .progress-bar-fill {{
                    height: 100%;
                    background-color: #3498db;
                    transition: width 0.5s;
                }}
                .card {{
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    padding: 20px;
                    margin-bottom: 20px;
                    background-color: #fff;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .phase {{
                    margin-bottom: 30px;
                }}
                .metrics {{
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                    gap: 10px;
                    margin: 20px 0;
                }}
                .metric-card {{
                    background-color: #f8f9fa;
                    border-radius: 4px;
                    padding: 15px;
                    text-align: center;
                }}
                .metric-value {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #2980b9;
                    margin: 10px 0;
                }}
                .metric-label {{
                    font-size: 14px;
                    color: #7f8c8d;
                }}
                .navbar {{
                    background-color: #2c3e50;
                    padding: 15px 20px;
                    margin-bottom: 20px;
                    border-radius: 4px;
                }}
                .navbar a {{
                    color: white;
                    margin-right: 15px;
                    text-decoration: none;
                }}
                .navbar a:hover {{
                    text-decoration: underline;
                }}
            </style>
        </head>
        <body>
            <div class="navbar">
                <a href="index.html">概览</a>
                <a href="status/progress_log.txt">进度日志</a>
                <a href="terminology/terms.csv">术语表</a>
                <a href="epub_structure/toc.txt">目录</a>
            </div>
            <div class="container">
                <h1>EPUB翻译报告</h1>
                <div class="card">
                    <h2>总体进度: {self.total_progress:.1f}%</h2>
                    <div class="progress-bar">
                        <div class="progress-bar-fill" style="width: {self.total_progress}%"></div>
                    </div>
                    <p>已用时间: {self._format_time(time.time() - self.start_time)}</p>
                    <p>更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                
                <div class="phase">
                    <h2>术语提取</h2>
                    <div class="card">
                        <div class="progress-bar">
                            <div class="progress-bar-fill" style="width: {self.phase_progresses['terminology']}%"></div>
                        </div>
                        <p>进度: {self.phase_progresses['terminology']:.1f}%</p>
                        <p>术语数量: {self.translation_metrics.get('terms_count', 0)}</p>
                    </div>
                </div>
                
                <div class="phase">
                    <h2>翻译进度</h2>
                    <div class="card">
                        <div class="progress-bar">
                            <div class="progress-bar-fill" style="width: {self.phase_progresses['translation']}%"></div>
                        </div>
                        <p>进度: {self.phase_progresses['translation']:.1f}%</p>
                        
                        <div class="metrics">
                            <div class="metric-card">
                                <div class="metric-label">已翻译字符</div>
                                <div class="metric-value">{self.translation_metrics['translated_chars']:,} / {self.translation_metrics['total_chars']:,}</div>
                                <div class="metric-label">字符</div>
                            </div>
                            
                            <div class="metric-card">
                                <div class="metric-label">已翻译段落</div>
                                <div class="metric-value">{self.translation_metrics['translated_segments']:,} / {self.translation_metrics['total_segments']:,}</div>
                                <div class="metric-label">段落</div>
                            </div>
                            
                            <div class="metric-card">
                                <div class="metric-label">翻译速度</div>
                                <div class="metric-value">{self.translation_metrics['chars_per_second']:.1f}</div>
                                <div class="metric-label">字符/秒</div>
                            </div>
                            
                            <div class="metric-card">
                                <div class="metric-label">预计剩余时间</div>
                                <div class="metric-value">{self._format_time(self.translation_metrics['estimated_remaining'])}</div>
                                <div class="metric-label"></div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="phase">
                    <h2>文件结构</h2>
                    <div class="card">
                        <ul>
                            <li><a href="status/progress_log.txt">进度日志</a> - 详细的翻译进度记录</li>
                            <li><a href="terminology/terms.csv">术语表</a> - 提取的专业术语</li>
                            <li><a href="chapters_original/">原始章节</a> - 原始章节内容</li>
                            <li><a href="chapters_translated/">翻译章节</a> - 翻译后的章节内容</li>
                            <li><a href="batches/">处理批次</a> - 按批次存储的原文与译文比对</li>
                            <li><a href="html_items/">HTML文件</a> - 原始与翻译后的完整HTML文件</li>
                        </ul>
                    </div>
                </div>
                
                <div class="card">
                    <p>报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p>EPUB翻译工具</p>
                </div>
            </div>
            
            <script>
                // Auto refresh every 30 seconds when translation is in progress
                if ({self.total_progress} < 100) {{
                    setTimeout(function() {{
                        location.reload();
                    }}, 30000);
                }}
            </script>
        </body>
        </html>
        """
        
        # Write HTML file
        try:
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.debug(f"HTML report saved to {html_file}")
        except Exception as e:
            logger.error(f"Error creating HTML report: {e}")
