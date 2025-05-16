# EPUB Translator using Deepseek API

这个工具能够利用Deepseek API翻译EPUB电子书文件，同时保留原格式、图片和专业术语。适用于各类电子书的翻译需求，特别是包含专业术语的技术类书籍。

## 特点

- 保留原EPUB文件的所有格式元素和图片
- 自动识别并保留专业术语（不翻译专业术语）
- 支持自定义术语表
- 保留原文件的排版和布局
- 高质量的翻译（利用Deepseek强大的翻译能力）
- 缓存翻译结果，提高效率
- 完整的进度显示
- 详细的日志记录

## 安装

1. 克隆仓库:

```bash
git clone https://github.com/yourusername/epub_translater.git
cd epub_translater
```

2. 安装依赖:

```bash
pip install -r requirements.txt
```

3. 下载NLTK资源(如果自动下载失败):

```bash
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
```

## 配置

在使用前，您需要获取Deepseek API密钥并配置工具。

1. 在[Deepseek官网](https://www.deepseek.com/)注册并获取API密钥

2. 配置API密钥:
   - 在`config.ini`中填入API密钥
   - 或者在运行时使用`-k`参数提供API密钥

配置文件`config.ini`包含以下部分:

```ini
[deepseek]
api_key = 您的API密钥
model = deepseek-chat
api_endpoint = https://api.deepseek.com/v1/chat/completions
timeout = 30
max_retries = 3
rate_limit = 10

[translation]
preserve_formatting = True
preserve_line_breaks = True
translate_titles = True
translate_captions = True
translate_alt_text = True
translate_metadata = True

[terminology]
enable_auto_extraction = True
min_term_frequency = 3
max_term_length = 5
ignore_case = True

[processing]
batch_size = 10
max_parallel_requests = 3
cache_translations = True
cache_dir = .translation_cache
```

## 使用方法

基本用法:

```bash
python main.py input.epub -o translated_output.epub
```

完整选项:

```bash
python main.py input.epub \
    -o output.epub \
    -s en \
    -t zh-CN \
    -k YOUR_API_KEY \
    --terminology terms.csv \
    --auto-terms \
    --min-term-freq 3 \
    --batch-size 10 \
    --log-level info
```

## 参数说明

- `input_file`: 输入的EPUB文件路径
- `-o, --output`: 输出的EPUB文件路径（默认为translated_[input_filename]）
- `-s, --source-lang`: 源语言（默认为auto自动检测）
- `-t, --target-lang`: 目标语言（默认为zh-CN中文）
- `-c, --config`: 配置文件路径（默认为config.ini）
- `-k, --api-key`: Deepseek API密钥（覆盖配置文件）
- `--terminology`: 自定义术语文件路径（CSV格式：术语,翻译）
- `--auto-terms`: 自动提取领域特定术语
- `--min-term-freq`: 自动检测术语的最小频率（默认为3）
- `--batch-size`: 一次翻译的段落数（默认为10）
- `--log-level`: 日志级别（默认为info）

## 术语管理

此工具能够自动识别和保护专业术语，防止它们被翻译。

### 自定义术语表

您可以创建CSV格式的自定义术语表:

```csv
Python,Python
Django,Django
machine learning,机器学习
deep learning,深度学习
```

使用`--terminology`参数指定术语表文件:

```bash
python main.py input.epub --terminology terms.csv
```

### 自动术语提取

启用自动术语提取功能:

```bash
python main.py input.epub --auto-terms --min-term-freq 3
```

这将分析EPUB内容，识别频繁出现的专业术语，并在翻译过程中保留它们。

## 示例

翻译英文EPUB到中文:

```bash
python main.py english_book.epub -o chinese_book.epub
```

翻译英文EPUB到中文，使用自定义术语表:

```bash
python main.py technical_book.epub -o translated_book.epub --terminology tech_terms.csv
```

翻译英文EPUB到中文，自动提取术语:

```bash
python main.py science_book.epub --auto-terms --min-term-freq 5
```

## 高级用法

### 批处理多个文件

```bash
for file in *.epub; do
    python main.py "$file" -o "translated_$file"
done
```

### 导出提取的术语

翻译后，您可以将自动提取的术语导出为CSV文件，用于后续翻译:

```python
from term_extractor import TerminologyExtractor

extractor = TerminologyExtractor()
# ... 翻译过程 ...
extractor.save_terminology("extracted_terms.csv")
```

## 常见问题

1. **NLTK资源下载失败**: 如果自动下载NLTK资源失败，请手动下载:
   ```bash
   python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
   ```

2. **API限制**: Deepseek API可能有使用限制，请查看您的账户配额。

3. **内存问题**: 处理大型EPUB文件时可能需要更多内存。

4. **翻译质量**: 翻译质量取决于Deepseek API。对于特定领域的内容，建议使用自定义术语表。

## 许可证

MIT

## 贡献

欢迎提交问题和拉取请求!

## 致谢

- [Deepseek](https://www.deepseek.com/) 提供强大的翻译API
- [EbookLib](https://github.com/aerkalov/ebooklib) 用于EPUB处理
- [NLTK](https://www.nltk.org/) 用于文本处理和术语提取
