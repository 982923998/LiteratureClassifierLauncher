# 阶段 2：获取分类建议（suggest）

读取所有 staging JSON，让 Gemini 分析文献集合并建议分类方案。

## 命令

```bash
python src/main.py --config <项目名> --mode suggest
```

**前提**：`staging/` 目录不为空（先运行 analyze）。

## 做了什么

1. 读取 `staging/` 下所有 JSON（提取 title、research_question、main_conclusion）
2. 一次性发送给 Gemini，请求建议 3-6 个分类类别
3. 将建议保存至 `staging/category_suggestions.json`
4. 打印人类可读的分类摘要

## 输出示例

```
============================
文献分类建议
============================
共分析 15 篇文献，建议以下 4 个类别：

类别 1: 综述与理论框架（建议归入 3 篇）
  - Smith_2023.pdf
  - Jones_2022.pdf

类别 2: 神经影像方法研究（建议归入 7 篇）
  ...

建议理由：
  这批文献主要围绕…

详细结果已保存至: /path/to/staging/category_suggestions.json
```

## 与 Claude 讨论

拿到建议后，直接在对话中和 Claude 讨论：

- "把类别 2 和 3 合并吧"
- "类别 1 改名为'方法综述'"
- "增加一个'临床应用'类别"

Claude 会帮你整理出最终的分类方案，并直接更新 `projects.yaml`：

```yaml
classification:
  enabled: true
  categories:
    1: "1. 综述与理论框架"
    2: "2. 神经影像方法"
    3: "3. 临床应用"
```

## 完成后

分类方案确认后，运行 [阶段 3：classify](classify.md) 应用分类。
