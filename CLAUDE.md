# Reading-Paper — AI 助手指南

你在这里只需要做一件事：**帮用户完成 suggest 阶段的分类讨论**。

## 你的任务

当用户说"帮我看分类建议"或类似表述时：

1. 读取 `staging/category_suggestions.json`
2. 向用户展示 AI 建议的分类方案
3. 与用户讨论，直到确认最终分类
4. 将确认的分类写入 `config/projects.yaml` 对应项目的 `categories` 字段：

```yaml
classification:
  categories:
    1: "类别名称"
    2: "类别名称"
```

## 工作目录

```
/Users/chenmayao/Desktop/文献归类/literature-classifier/scripts/
```

## 参考

- [suggest 阶段详情](../references/suggest.md)
- [classify 阶段详情](../references/classify.md)
