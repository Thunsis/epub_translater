#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Content Manager for EPUB Translator.
Handles saving and managing intermediate content files for inspection and debugging.
"""

import os
import json
import logging
import hashlib
from bs4 import BeautifulSoup

logger = logging.getLogger("epub_translator.content_manager")

class ContentManager:
    """Manages intermediate content files for inspection."""
    
    def __init__(self, workdir):
        """Initialize content manager.
        
        Args:
            workdir: Working directory for content files
        """
        self.workdir = workdir
        
        # Create directories
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Create necessary directories for content files."""
        directories = [
            f"{self.workdir}/html_items",
            f"{self.workdir}/metadata",
            f"{self.workdir}/chapters_original",
            f"{self.workdir}/chapters_translated",
            f"{self.workdir}/batches"
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
    
    def save_html_item(self, item, is_translated=False):
        """Save HTML item content.
        
        Args:
            item: ebooklib.epub.EpubHtml item
            is_translated: Whether content is translated
            
        Returns:
            Path to saved HTML file
        """
        item_id = item.get_id()
        safe_id = item_id.replace('/', '_')
        
        # Create directory for this item
        item_dir = f"{self.workdir}/html_items/{safe_id}"
        os.makedirs(item_dir, exist_ok=True)
        
        # Create directory for batches
        os.makedirs(f"{item_dir}/batches", exist_ok=True)
        
        # Get content
        content = item.get_content().decode('utf-8')
        
        # Save HTML file
        file_name = "translated.html" if is_translated else "original.html"
        file_path = f"{item_dir}/{file_name}"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Also save as text for easier inspection
        text_content = self._extract_text_from_html(content)
        text_file_path = f"{item_dir}/{file_name.replace('.html', '.txt')}"
        
        with open(text_file_path, 'w', encoding='utf-8') as f:
            f.write(text_content)
        
        logger.debug(f"Saved HTML item {item_id} to {file_path}")
        return item_dir
    
    def save_batch(self, item_id, batch_id, segments, translated_texts=None, protected_texts=None):
        """Save batch content.
        
        Args:
            item_id: HTML item ID
            batch_id: Batch ID
            segments: List of tuples (element, attribute, text)
            translated_texts: List of translated texts (optional)
            protected_texts: List of texts with protected terminology (optional)
            
        Returns:
            Path to batch directory
        """
        safe_id = item_id.replace('/', '_')
        batch_dir = f"{self.workdir}/html_items/{safe_id}/batches/batch_{batch_id:03d}"
        os.makedirs(batch_dir, exist_ok=True)
        
        # Extract original texts
        original_texts = [segment[2] for segment in segments]
        
        # Save original texts
        with open(f"{batch_dir}/original.txt", 'w', encoding='utf-8') as f:
            f.write('\n---\n'.join(original_texts))
        
        # Save protected texts if provided
        if protected_texts:
            with open(f"{batch_dir}/protected.txt", 'w', encoding='utf-8') as f:
                f.write('\n---\n'.join(protected_texts))
        
        # Save translated texts if provided
        if translated_texts:
            with open(f"{batch_dir}/translated.txt", 'w', encoding='utf-8') as f:
                f.write('\n---\n'.join(translated_texts))
            
            # Also save parallel text for comparison
            with open(f"{batch_dir}/parallel.txt", 'w', encoding='utf-8') as f:
                for i, (orig, trans) in enumerate(zip(original_texts, translated_texts)):
                    f.write(f"=== Segment {i+1} ===\n")
                    f.write(f"原文: {orig}\n")
                    f.write(f"译文: {trans}\n\n")
        
        # Save batch details as JSON for more technical inspection
        batch_info = {
            "batch_id": batch_id,
            "segments_count": len(segments),
            "segments": [
                {
                    "index": i,
                    "element_type": type(segment[0]).__name__ if segment[0] else None,
                    "attribute": segment[1],
                    "text_length": len(segment[2]),
                    "text_hash": hashlib.md5(segment[2].encode()).hexdigest()
                } for i, segment in enumerate(segments)
            ]
        }
        
        with open(f"{batch_dir}/batch_info.json", 'w', encoding='utf-8') as f:
            json.dump(batch_info, f, indent=2, ensure_ascii=False)
        
        logger.debug(f"Saved batch {batch_id} for item {item_id} to {batch_dir}")
        return batch_dir
    
    def save_terminology(self, terms, filename="terms.csv"):
        """Save terminology to CSV file.
        
        Args:
            terms: Dictionary of terms and their frequencies
            filename: Output filename
            
        Returns:
            Path to terminology file
        """
        file_path = f"{self.workdir}/terminology/{filename}"
        
        # Create the terms directory if it doesn't exist
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        try:
            import csv
            with open(file_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Term', 'Frequency', 'Custom Translation'])
                
                for term, freq in sorted(terms.items(), key=lambda x: x[1], reverse=True):
                    writer.writerow([term, freq, ''])
            
            logger.info(f"Saved {len(terms)} terms to {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Error saving terminology to {file_path}: {e}")
            return None
    
    def save_chapter_content(self, item, chapter_title=None, is_translated=False):
        """Save chapter content to a separate directory for easy access.
        
        Args:
            item: ebooklib.epub.EpubHtml item
            chapter_title: Title of the chapter (optional)
            is_translated: Whether content is translated
            
        Returns:
            Path to saved chapter file
        """
        item_id = item.get_id()
        safe_id = item_id.replace('/', '_')
        
        # Get content
        content = item.get_content().decode('utf-8')
        
        # Extract title if not provided
        if not chapter_title:
            try:
                soup = BeautifulSoup(content, 'html.parser')
                title_tag = soup.find(['h1', 'h2', 'h3', 'h4', 'title'])
                if title_tag:
                    chapter_title = title_tag.get_text().strip()
                else:
                    chapter_title = f"Chapter {safe_id}"
            except Exception as e:
                logger.error(f"Error extracting chapter title: {e}")
                chapter_title = f"Chapter {safe_id}"
        
        # Create sanitized filename from title
        filename = f"{safe_id}_{self._sanitize_filename(chapter_title)}.html"
        
        # Determine directory based on translation state
        target_dir = f"{self.workdir}/chapters_translated" if is_translated else f"{self.workdir}/chapters_original"
        os.makedirs(target_dir, exist_ok=True)
        
        # Save HTML file
        file_path = f"{target_dir}/{filename}"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Also save as text for easier reading
        text_content = self._extract_text_from_html(content)
        text_file_path = f"{target_dir}/{filename.replace('.html', '.txt')}"
        with open(text_file_path, 'w', encoding='utf-8') as f:
            f.write(text_content)
        
        logger.debug(f"Saved chapter {chapter_title} to {file_path}")
        return file_path
    
    def save_batch_standalone(self, item_id, batch_id, original_texts, translated_texts=None):
        """Save batch content to the standalone batches directory for easier tracking.
        
        Args:
            item_id: HTML item ID
            batch_id: Batch ID 
            original_texts: List of original texts
            translated_texts: List of translated texts (optional)
            
        Returns:
            Path to batch file
        """
        safe_id = item_id.replace('/', '_')
        batches_dir = f"{self.workdir}/batches"
        os.makedirs(batches_dir, exist_ok=True)
        
        # Create batch filename
        filename = f"{safe_id}_batch_{batch_id:03d}.txt"
        file_path = f"{batches_dir}/{filename}"
        
        # Create content with parallel text
        content = f"Chapter ID: {item_id}\nBatch: {batch_id}\n"
        content += "=" * 50 + "\n\n"
        
        if translated_texts:
            # Save parallel text
            for i, (orig, trans) in enumerate(zip(original_texts, translated_texts)):
                content += f"=== Segment {i+1} ===\n"
                content += f"Original: {orig}\n"
                content += f"Translated: {trans}\n\n"
        else:
            # Save just original texts
            for i, text in enumerate(original_texts):
                content += f"=== Segment {i+1} ===\n"
                content += f"{text}\n\n"
                
        # Write to file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        logger.debug(f"Saved standalone batch file for {item_id}, batch {batch_id} to {file_path}")
        return file_path
    
    def _sanitize_filename(self, filename):
        """Sanitize a string to be used as a filename.
        
        Args:
            filename: Input string
            
        Returns:
            Sanitized filename
        """
        # Replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
            
        # Limit length
        if len(filename) > 50:
            filename = filename[:47] + '...'
            
        return filename
    
    def save_metadata(self, metadata, is_translated=False):
        """Save book metadata.
        
        Args:
            metadata: Dictionary with metadata
            is_translated: Whether metadata is translated
            
        Returns:
            Path to metadata file
        """
        file_name = "metadata_translated.json" if is_translated else "metadata_original.json"
        file_path = f"{self.workdir}/metadata/{file_name}"
        
        # Convert metadata to serializable format
        serializable_metadata = {}
        for key, value in metadata.items():
            if isinstance(value, list):
                # Handle lists of tuples or complex objects
                serializable_metadata[key] = [
                    item[0] if isinstance(item, tuple) and len(item) > 0 else str(item)
                    for item in value
                ]
            else:
                serializable_metadata[key] = str(value)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_metadata, f, indent=2, ensure_ascii=False)
        
        logger.debug(f"Saved metadata to {file_path}")
        return file_path
    
    def create_html_index(self):
        """Create HTML index for all saved content.
        
        Returns:
            Path to index file
        """
        index_path = f"{self.workdir}/content_index.html"
        
        # Get list of HTML items
        html_items_dir = f"{self.workdir}/html_items"
        if not os.path.exists(html_items_dir):
            return None
            
        html_items = [d for d in os.listdir(html_items_dir) 
                     if os.path.isdir(os.path.join(html_items_dir, d))]
        
        # Get terminology files
        terminology_dir = f"{self.workdir}/terminology"
        terminology_files = []
        if os.path.exists(terminology_dir):
            terminology_files = [f for f in os.listdir(terminology_dir) 
                                if f.endswith('.csv')]
        
        # Create HTML content
        html_content = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>EPUB翻译内容索引</title>
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
                    max-width: 1200px;
                    margin: 0 auto;
                }}
                .card {{
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    padding: 20px;
                    margin-bottom: 20px;
                    background-color: #fff;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                }}
                table, th, td {{
                    border: 1px solid #ddd;
                }}
                th, td {{
                    padding: 12px;
                    text-align: left;
                }}
                th {{
                    background-color: #f2f2f2;
                }}
                tr:nth-child(even) {{
                    background-color: #f9f9f9;
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
                <a href="../index.html">主页</a>
                <a href="content_index.html">内容索引</a>
                <a href="status/progress_log.txt">进度日志</a>
                <a href="epub_structure/toc.txt">目录</a>
            </div>
            <div class="container">
                <h1>EPUB翻译内容索引</h1>
                
                <div class="card">
                    <h2>术语表</h2>
                    <table>
                        <tr>
                            <th>文件名</th>
                            <th>链接</th>
                        </tr>
        """
        
        # Add terminology files
        for file in terminology_files:
            html_content += f"""
                        <tr>
                            <td>{file}</td>
                            <td><a href="terminology/{file}" target="_blank">查看</a></td>
                        </tr>
            """
        
        html_content += f"""
                    </table>
                </div>
                
                <div class="card">
                    <h2>章节内容</h2>
                    <p>这里提供原始章节和翻译后的章节内容，方便直接查看</p>
                    <table>
                        <tr>
                            <th>原始章节</th>
                            <th>翻译后章节</th>
                        </tr>
                        <tr>
                            <td><a href="chapters_original/" target="_blank">查看原始章节文件</a></td>
                            <td><a href="chapters_translated/" target="_blank">查看翻译后章节文件</a></td>
                        </tr>
                    </table>
                </div>
                
                <div class="card">
                    <h2>处理批次</h2>
                    <p>这里提供按批次存储的处理数据，方便查看翻译进度和比对</p>
                    <table>
                        <tr>
                            <th>批次文件</th>
                        </tr>
                        <tr>
                            <td><a href="batches/" target="_blank">查看批次文件</a></td>
                        </tr>
                    </table>
                </div>
                
                <div class="card">
                    <h2>HTML项目 ({len(html_items)}个)</h2>
                    <table>
                        <tr>
                            <th>项目ID</th>
                            <th>原始HTML</th>
                            <th>翻译后HTML</th>
                            <th>原始文本</th>
                            <th>翻译后文本</th>
                            <th>批次</th>
                        </tr>
        """
        
        # Add HTML items
        for item in html_items:
            item_dir = os.path.join(html_items_dir, item)
            
            # Check if original and translated files exist
            original_html = os.path.join(item_dir, "original.html")
            translated_html = os.path.join(item_dir, "translated.html")
            original_txt = os.path.join(item_dir, "original.txt")
            translated_txt = os.path.join(item_dir, "translated.txt")
            
            # Count batches
            batches_dir = os.path.join(item_dir, "batches")
            batch_count = 0
            if os.path.exists(batches_dir):
                batch_count = len([d for d in os.listdir(batches_dir) 
                                  if os.path.isdir(os.path.join(batches_dir, d)) and d.startswith("batch_")])
            
            html_content += f"""
                        <tr>
                            <td>{item}</td>
                            <td>{"<a href='html_items/"+item+"/original.html' target='_blank'>查看</a>" if os.path.exists(original_html) else "N/A"}</td>
                            <td>{"<a href='html_items/"+item+"/translated.html' target='_blank'>查看</a>" if os.path.exists(translated_html) else "N/A"}</td>
                            <td>{"<a href='html_items/"+item+"/original.txt' target='_blank'>查看</a>" if os.path.exists(original_txt) else "N/A"}</td>
                            <td>{"<a href='html_items/"+item+"/translated.txt' target='_blank'>查看</a>" if os.path.exists(translated_txt) else "N/A"}</td>
                            <td>{"<a href='#"+item+"_batches'>"+str(batch_count)+"个批次</a>" if batch_count > 0 else "无批次"}</td>
                        </tr>
            """
        
        html_content += f"""
                    </table>
                </div>
        """
        
        # Add sections for each HTML item's batches
        for item in html_items:
            item_dir = os.path.join(html_items_dir, item)
            batches_dir = os.path.join(item_dir, "batches")
            
            if not os.path.exists(batches_dir):
                continue
                
            batches = [d for d in os.listdir(batches_dir) 
                      if os.path.isdir(os.path.join(batches_dir, d)) and d.startswith("batch_")]
            
            if not batches:
                continue
                
            html_content += f"""
                <div class="card" id="{item}_batches">
                    <h2>项目 {item} 的批次 ({len(batches)}个)</h2>
                    <table>
                        <tr>
                            <th>批次ID</th>
                            <th>原始文本</th>
                            <th>术语保护后</th>
                            <th>翻译后文本</th>
                            <th>对照文本</th>
                            <th>技术信息</th>
                        </tr>
            """
            
            # Sort batches by ID
            batches.sort()
            
            for batch in batches:
                batch_dir = os.path.join(batches_dir, batch)
                
                # Check for files
                original_txt = os.path.join(batch_dir, "original.txt")
                protected_txt = os.path.join(batch_dir, "protected.txt")
                translated_txt = os.path.join(batch_dir, "translated.txt")
                parallel_txt = os.path.join(batch_dir, "parallel.txt")
                batch_info = os.path.join(batch_dir, "batch_info.json")
                
                html_content += f"""
                        <tr>
                            <td>{batch}</td>
                            <td>{"<a href='html_items/"+item+"/batches/"+batch+"/original.txt' target='_blank'>查看</a>" if os.path.exists(original_txt) else "N/A"}</td>
                            <td>{"<a href='html_items/"+item+"/batches/"+batch+"/protected.txt' target='_blank'>查看</a>" if os.path.exists(protected_txt) else "N/A"}</td>
                            <td>{"<a href='html_items/"+item+"/batches/"+batch+"/translated.txt' target='_blank'>查看</a>" if os.path.exists(translated_txt) else "N/A"}</td>
                            <td>{"<a href='html_items/"+item+"/batches/"+batch+"/parallel.txt' target='_blank'>查看</a>" if os.path.exists(parallel_txt) else "N/A"}</td>
                            <td>{"<a href='html_items/"+item+"/batches/"+batch+"/batch_info.json' target='_blank'>查看</a>" if os.path.exists(batch_info) else "N/A"}</td>
                        </tr>
                """
            
            html_content += f"""
                    </table>
                </div>
            """
        
        html_content += f"""
            </div>
        </body>
        </html>
        """
        
        # Write HTML file
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.debug(f"Created HTML index at {index_path}")
        return index_path
    
    def _extract_text_from_html(self, html_content):
        """Extract text content from HTML.
        
        Args:
            html_content: HTML content
            
        Returns:
            Extracted text content
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.extract()
            
            # Get text
            text = soup.get_text()
            
            # Break into lines and remove leading and trailing space on each
            lines = (line.strip() for line in text.splitlines())
            
            # Break multi-headlines into a line each
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            
            # Drop blank lines
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return text
        except Exception as e:
            logger.error(f"Error extracting text from HTML: {e}")
            return "Error extracting text"
