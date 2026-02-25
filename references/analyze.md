# 阶段 1：分析文献（analyze）

对输入目录中的 PDF 批量分析，提取结构化信息，**不做分类**。

## 命令

```bash
cd scripts
python src/main.py --config <项目名> --mode analyze

# 测试少量文献
python src/main.py --config asd --mode analyze --limit 3

# 处理单篇
python src/main.py --config asd --mode analyze --single "paper.pdf"

# 调整并发数（默认 3）
python src/main.py --config asd --mode analyze --workers 5
```

## 做了什么

1. 扫描 `pdf_input` 目录下的所有 PDF
2. 并发上传 PDF 给 Gemini API 分析
3. 将提取结果保存为 `staging/<文件名>.json`
4. 生成 Markdown 报告，放入 `md_output/0. 未分类/`
5. 将已处理 PDF 移至 `pdf_processed/`

**已处理的 PDF 会自动跳过**（staging JSON 已存在则不重复调用 API）。

## staging JSON 格式

每篇文献在 `staging/` 目录下保存一个 JSON：

```json
{
  "source_pdf": "paper_name.pdf",
  "processed_at": "2024-01-01T00:00:00",
  "analysis": {
    "title": "文献标题",
    "year": "2024",
    "authors": "作者",
    "journal": "期刊",
    "research_question": "科学问题",
    "methodology": {
      "dataset": "数据集",
      "data_modality": "数据模态",
      "core_model": "核心模型",
      "analysis_pipeline": "分析流程"
    },
    "main_conclusion": "主要结论",
    "custom_field": "自定义关注点内容"
  },
  "md_filename": "文献标题.md"
}
```

## 完成后

staging 目录有数据后，运行 [阶段 2：suggest](suggest.md) 获取分类建议。
