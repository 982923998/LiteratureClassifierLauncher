# 本地 Web 三阶段文献分类界面设计

日期：2026-02-24

## 目标

将当前命令行流程改造为本地 Web 工具，明确隔离三阶段：

1. `analyze`：脚本驱动分析，结果可视化（左 PDF、右 Markdown）。
2. `suggest`：保留人机交互，使用聊天式终端窗口确认最终分类。
3. `classify`：脚本驱动批量分类，并可视化分类结果。

## 约束

1. 复用现有 `scripts/src/main.py` 工作流，不重写分析/分类核心逻辑。
2. 前端使用 React + Vite。
3. 后端使用 FastAPI。
4. 实时通信使用 WebSocket（任务日志、阶段 2 聊天）。
5. 运行形态为本地 `localhost` Web。

## 架构

### 后端

1. `TaskManager`：统一管理 `analyze/classify` 子进程任务。
2. `SuggestSessionManager`：加载建议文件、维护草稿分类、调用 Gemini 聊天修订分类、写回 `projects.yaml`。
3. REST API：项目列表、文献索引、文件读取、任务启动、任务状态查询。
4. WebSocket：
   - `/ws/tasks/{task_id}`：推送任务日志和状态。
   - `/ws/suggest/{project}`：阶段 2 聊天会话与草稿同步。

### 前端

1. 路由：`/analyze`、`/suggest`、`/classify`。
2. `AnalyzePage`：项目参数、任务启动、实时日志、PDF/Markdown 双栏。
3. `SuggestPage`：终端式聊天窗口、建议分类可视化、草稿分类编辑、写入与一键分类。
4. `ClassifyPage`：实时分类日志、分类统计、按类浏览文献并回看 Markdown。

## 数据流

1. Analyze：前端发起任务 -> 后端启动子进程 -> WS 推日志 -> 前端刷新文献索引 -> PDF/MD 联动浏览。
2. Suggest：前端连接会话 -> 后端加载 `category_suggestions.json` -> 用户聊天调整 -> 后端更新草稿 -> 确认后写 `projects.yaml` -> 可直接触发 classify。
3. Classify：前端发起任务 -> 后端启动 `--mode classify` -> WS 推送结果 -> 前端展示分布统计与文献列表。

## 错误处理

1. 任务失败：状态置 `failed`，保留完整日志。
2. 会话失败：返回结构化错误消息（缺少建议文件、API Key 未配置、JSON 解析失败）。
3. 文件访问：路径白名单校验，仅允许访问当前项目的 PDF/MD 目录。

## 验收标准

1. 三个阶段分别可独立操作，互不干扰。
2. `analyze/classify` 在 Web 中能完整触发并查看实时日志。
3. 阶段 2 能通过聊天多轮确认分类，并成功写入 `projects.yaml`。
4. 阶段 1 和阶段 3 均可查看 Markdown，阶段 1 支持 PDF 对照阅读。
