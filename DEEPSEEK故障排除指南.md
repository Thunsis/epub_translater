# DeepSeek API 故障排除指南

本指南帮助解决 EPUB 翻译器中的 DeepSeek API 超时和连接问题。

## 常见问题

1. **API 超时**：处理大型请求时，DeepSeek API 超时，尤其是在术语提取阶段
2. **SSL 证书验证**：某些系统在 SSL 证书验证方面存在问题
3. **速率限制**：发出过多请求时触发 API 速率限制

## 解决方案一：测试连接

首先，使用包含的诊断工具测试与 DeepSeek API 的连接：

```bash
python fix_deepseek_api.py --api-key 你的API密钥 --timeout 60
```

如果遇到 SSL 问题，请尝试：

```bash
python fix_deepseek_api.py --api-key 你的API密钥 --timeout 60 --no-verify-ssl
```

如果测试通过，可以使用成功的设置更新 config.ini：

```bash
python fix_deepseek_api.py --api-key 你的API密钥 --timeout 60 --no-verify-ssl --update-config
```

## 解决方案二：使用优化的术语提取器

主要问题发生在术语提取阶段，因为它在一个请求中发送整个书籍结构。我们创建了一个优化的提取器，将内容分成较小的块：

1. 首先运行准备阶段（如果尚未运行）：

```bash
python main.py input.epub --phase prepare
```

2. 然后使用优化的术语提取器：

```bash
python run_optimized_terminology.py input.epub --timeout 60 --chunk-size 3000
```

如果遇到 SSL 问题：

```bash
python run_optimized_terminology.py input.epub --timeout 60 --chunk-size 3000 --no-verify-ssl
```

3. 术语提取成功后，继续翻译：

```bash
python main.py input.epub --phase translate
```

## 故障排除技巧

### 如果持续遇到超时：

1. **增加超时值**：
   ```bash
   python run_optimized_terminology.py input.epub --timeout 120
   ```

2. **减小块大小**：
   ```bash
   python run_optimized_terminology.py input.epub --chunk-size 1500
   ```

3. **结合两种方法**：
   ```bash
   python run_optimized_terminology.py input.epub --timeout 120 --chunk-size 1500
   ```

### SSL 证书问题：

如果看到包含"certificate verify failed"或类似 SSL 相关错误，请使用 `--no-verify-ssl` 标志：

```bash
python run_optimized_terminology.py input.epub --no-verify-ssl
```

### API 密钥问题：

1. 确保在 config.ini 文件中正确设置了 API 密钥
2. 或者，使用 `--api-key` 参数直接提供：
   ```bash
   python run_optimized_terminology.py input.epub --api-key 你的API密钥
   ```

### 网络连接：

确保有稳定的互联网连接。如果使用 VPN，请尝试禁用它，因为它可能会干扰 API 连接。

## 修复原理

原始实现在一个大型请求中将整个书籍结构（目录和索引）发送到 DeepSeek。这通常超过了 API 的超时限制。

我们的解决方案：

1. **分块**：我们将内容分成较小、可管理的块
2. **渐进式处理**：我们单独处理每个块并合并结果
3. **改进的错误处理**：更好的重试逻辑和错误报告
4. **SSL 灵活性**：需要时可以禁用 SSL 验证

这种方法更具弹性，更有可能成功，尤其是对于较大的书籍。
