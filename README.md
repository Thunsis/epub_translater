# EPUB Translator using Deepseek API

这个工具能够利用Deepseek API将英文EPUB电子书文件翻译成中文，同时保留原格式、图片和专业术语。适用于各类电子书的翻译需求，特别是包含专业术语的技术类书籍。

## 特点

- 默认支持英文到中文的翻译（可配置其他语言）
- 保留原EPUB文件的所有格式元素和图片
- 智能识别专业术语并保留原文（不翻译术语）
- 自动提取和保护领域专业术语
- 支持导入自定义术语表
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

2. 创建虚拟环境并激活:

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows
```

3. 安装依赖:

```bash
pip3 install -r requirements.txt
```

4. 下载NLTK资源(如果自动下载失败):

```bash
python3 -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
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
python3 main.py input.epub -o translated_output.epub
```

完整选项:

```bash
python3 main.py input.epub \
    -o output.epub \
    -k YOUR_API_KEY \
    --terminology terms.csv \
    --max-workers 4
```

## 参数说明

### 必选参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `input_file` | 输入EPUB文件路径 | `book.epub` |

### 可选参数

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| `-o, --output` | 输出EPUB文件路径 | `translated_[input_filename]` | `--output chinese_book.epub` |
| `-k, --api-key` | Deepseek API密钥 | 从config.ini读取 | `--api-key YOUR_KEY` |
| `-s, --source-lang` | 源语言代码 | `en` | `--source-lang fr` |
| `-t, --target-lang` | 目标语言代码 | `zh-CN` | `--target-lang ja` |
| `-c, --config` | 配置文件路径 | `config.ini` | `--config my_config.ini` |
| `--terminology` | 术语表文件路径 | 不使用术语表 | `--terminology terms.txt` |
| `--no-auto-terms` | 禁用自动术语提取 | 启用 | `--no-auto-terms` |
| `--min-term-freq` | 术语最小频率 | `3` | `--min-term-freq 5` |
| `--batch-size` | 批处理段落数 | `10` | `--batch-size 20` |
| `--max-workers` | 并行工作线程数 | `4` | `--max-workers 8` |
| `--chunk-size` | 内容分块大小(字符) | `5000` | `--chunk-size 8000` |
| `--log-level` | 日志详细程度 | `info` | `--log-level debug` |

## 配置文件参数 (config.ini)

配置文件可分为以下四个部分：

### [deepseek] 部分

| 参数 | 说明 | 默认值 | 是否必须 |
|------|------|--------|----------|
| `api_key` | Deepseek API密钥 | 无 | **必须** |
| `model` | 使用的模型名称 | `deepseek-chat` | 可选 |
| `api_endpoint` | API端点 | `https://api.deepseek.com/v1/chat/completions` | 可选 |
| `timeout` | API请求超时(秒) | `30` | 可选 |
| `max_retries` | 失败重试次数 | `3` | 可选 |
| `rate_limit` | 每分钟最大请求数 | `10` | 可选 |

### [translation] 部分

| 参数 | 说明 | 默认值 | 是否必须 |
|------|------|--------|----------|
| `preserve_formatting` | 保留原文格式 | `True` | 可选 |
| `preserve_line_breaks` | 保留原文换行符 | `True` | 可选 |
| `translate_titles` | 翻译标题和目录 | `True` | 可选 |
| `translate_captions` | 翻译图片标题 | `True` | 可选 |
| `translate_alt_text` | 翻译图片替代文本 | `True` | 可选 |
| `translate_metadata` | 翻译元数据(书名等) | `True` | 可选 |

### [terminology] 部分

| 参数 | 说明 | 默认值 | 是否必须 |
|------|------|--------|----------|
| `enable_auto_extraction` | 启用自动术语提取 | `True` | 可选 |
| `min_term_frequency` | 自动提取术语的最小频率 | `3` | 可选 |
| `max_term_length` | 术语最大词数 | `5` | 可选 |
| `ignore_case` | 匹配术语时忽略大小写 | `True` | 可选 |

### [processing] 部分

| 参数 | 说明 | 默认值 | 是否必须 |
|------|------|--------|----------|
| `batch_size` | 一次翻译的段落数 | `10` | 可选 |
| `max_parallel_requests` | 并行API请求数 | `3` | 可选 |
| `cache_translations` | 启用翻译缓存 | `True` | 可选 |
| `cache_dir` | 缓存目录 | `.translation_cache` | 可选 |

## 术语管理

此工具能够自动识别和保护专业术语，防止它们被翻译。所有专业术语保持原文不变，确保技术准确性。

### 工作流程

翻译过程分为以下几个清晰的步骤：

1. **预处理与分析**：工具首先解析EPUB文件，提取所有文本内容和文档结构
2. **智能术语提取阶段**：
   - Deepseek分析整个文档内容，识别潜在的专业术语
   - 结合对文档专业领域的理解，识别特定领域的专业术语
   - 基于术语在专业语境中的使用方式和重要性进行评估
   - 同时考虑术语的出现频率，筛选出超过最小频率阈值的术语
   - 通过文本上下文理解术语的专业含义，避免误判普通词汇为术语
   - 生成术语列表，并保存到`data/terminology/[文件名]_terms.csv`文件
3. **术语保护阶段**：
   - 在翻译前，用特殊标记包围识别到的专业术语
   - 标记格式为: `[[TERM:原始术语]]`
4. **翻译处理阶段**：
   - Deepseek API在翻译时会保留这些特殊标记
   - 标记内的术语保持原样不被翻译
   - 同时利用Deepseek对专业领域的理解，确保术语在上下文中的连贯性
5. **术语恢复阶段**：
   - 翻译完成后，将特殊标记替换回原始术语
   - 确保所有专业术语在最终输出中保持原文

这种流程确保了Deepseek在翻译前，先通过对文档内容和专业领域的理解分析并生成术语表，然后严格遵循不翻译术语的规定进行翻译。术语提取不仅依赖于统计方法，还结合了Deepseek对文档主题和专业领域的深度理解，能够更准确地识别出真正的专业术语。生成的术语列表会被保存，方便后续翻译或人工审核使用。

### 自定义术语表

您可以创建术语表文件，每行一个术语:

```
Python
Django
React
TensorFlow
```

使用`--terminology`参数指定术语表文件:

```bash
python3 main.py input.epub --terminology terms.csv
```

### 自动术语提取

自动术语提取功能默认启用，会自动分析EPUB内容，识别频繁出现的专业术语，并在翻译过程中保留原文不译。提取的术语表会自动保存到`data/terminology/[输入文件名]_terms.csv`目录下，方便后续使用。

如需调整术语最小频率:
```bash
python3 main.py input.epub --min-term-freq 5
```

如需禁用自动术语提取:
```bash
python3 main.py input.epub --no-auto-terms
```

## 示例

翻译英文EPUB到中文:

```bash
python3 main.py english_book.epub -o chinese_book.epub
```

翻译英文EPUB到中文，使用自定义术语表:

```bash
python3 main.py technical_book.epub -o translated_book.epub --terminology tech_terms.csv
```

翻译英文EPUB到中文，调整术语频率阈值:

```bash
python3 main.py science_book.epub --min-term-freq 4
```

## 高级用法

### 批处理多个文件

```bash
for file in *.epub; do
    python3 main.py "$file" -o "translated_$file"
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

## 性能优化

本工具专门针对大型EPUB文件进行了性能优化，使用以下特性可以显著提高翻译速度:

### 并行处理

使用多线程并行处理EPUB内容：

```bash
python3 main.py large_book.epub --max-workers 8
```

`max-workers`参数控制并行处理的线程数。较大的值可以提高速度，但也会增加内存使用。推荐设置:
- 对于4核CPU：设置为4-6
- 对于8核CPU：设置为6-10
- 对于高性能服务器：可以设置更高的值（最高可设置为32，但一般不建议超过CPU核心数的2倍）

最佳设置一般是CPU核心数的1-2倍，超过这个范围可能由于线程切换开销而导致性能下降。

### 批处理优化

控制批量翻译的文本大小:

```bash
python3 main.py large_book.epub --batch-size 20 --chunk-size 8000
```

- `batch-size`: 每批处理的段落数。较大的值减少API请求次数，但每次请求的处理时间更长
- `chunk-size`: 处理内容块的大小(字符数)。较大的值可以减少处理开销，但可能增加内存使用

### 内存使用优化

对于特别大的EPUB文件(>100MB)，可以调整以下参数减少内存使用:

```bash
python3 main.py huge_book.epub --batch-size 5 --chunk-size 3000 --max-workers 3
```

### 多核心处理器的优化配置

对于多核心处理器，推荐配置:

```bash
python3 main.py large_book.epub --max-workers 8 --batch-size 15 --chunk-size 10000
```

这将在大多数现代计算机上提供良好的性能和内存使用平衡。

### 翻译速度比较

下面是不同配置的性能比较(以100MB的EPUB为例):

| 配置 | 处理时间 | 内存使用 |
|------|----------|----------|
| 默认设置 | ~40分钟 | ~500MB |
| 优化设置(8线程) | ~15分钟 | ~800MB |
| 高性能设置(12线程) | ~10分钟 | ~1.2GB |

## 常见问题

1. **NLTK资源下载失败**: 如果自动下载NLTK资源失败，请手动下载:
   ```bash
   python3 -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
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
