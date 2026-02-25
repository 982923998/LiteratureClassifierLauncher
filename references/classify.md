# 阶段 3：应用分类（classify）

根据 `projects.yaml` 中确认的分类方案，对所有文献进行分类并移动文件。

## 命令

```bash
python src/main.py --config <项目名> --mode classify
```

**前提**：
- `staging/` 目录不为空（先运行 analyze）
- `projects.yaml` 中 `categories` 不为空（先运行 suggest 并确认分类）

## 做了什么

1. 读取所有 `staging/*.json` 中的文献摘要
2. **一次 API 调用**将所有文献摘要发给 Gemini 分类（不重读 PDF）
3. 将每篇文献的 Markdown 从 `0. 未分类/` 移动到对应分类目录
4. 更新 staging JSON，记录最终分类结果

## 文件移动规则

- Gemini 返回有效分类 → 移入对应目录（如 `1. 综述与理论框架/`）
- 分类无效或返回 None → 保留在 `0. 未分类/`
- 目标文件已存在 → 自动加时间戳（不覆盖）

## 完成后的目录结构

```
Classification/
├── 0. 未分类/          # 无法分类的文献
├── 1. 综述与理论框架/
│   ├── Smith_2023.md
│   └── Jones_2022.md
├── 2. 神经影像方法/
│   └── ...
└── 3. 临床应用/
    └── ...
```

## 重新分类

如果对分类结果不满意，可以：

1. 修改 `projects.yaml` 中的 `categories`
2. 手动将 Markdown 文件移回 `0. 未分类/`
3. 重新运行 `--mode classify`

classify 只移动当前在 `0. 未分类/` 目录下的文件，不影响已在分类目录中的文件。
