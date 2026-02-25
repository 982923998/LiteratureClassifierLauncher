# Literature Classifier

本项目是一个本地运行的文献处理工作台，支持三阶段流程：

1. `Analyze`：批量分析 PDF，生成 `staging/*.json` 与 Markdown。
2. `Codex 标签确认`：在本地 Terminal 打开 Codex，对分类标签进行确认，并直接完成分类落盘。
3. `Classify 可视化`：查看分类后的分组结果与文献详情。

## 当前流程说明

- 阶段 1 使用脚本分析 PDF（会用到 Gemini/OpenAI 兼容接口配置）。
- 阶段 2 不再通过后端聊天 API 分类，而是由 Codex 在本地执行：
  - 确认标签
  - 写入 `projects.yaml`
  - 更新每篇 `staging` JSON 的分类字段
  - 移动 Markdown 到对应分类目录
- 阶段 3 只做结果展示，不提供“启动 classify”按钮。

## 目录结构

- `scripts/`：核心处理脚本与配置
  - `scripts/src/main.py`：analyze/suggest/classify 主入口
  - `scripts/config/projects.yaml`：项目路径与分类配置
  - `scripts/.env`：模型接口配置
- `web/`：本地 Web 前后端
  - `web/backend/`：FastAPI + WebSocket
  - `web/frontend/`：React + Vite
  - `web/launch_web_app.sh`：一键启动
  - `web/stop_web_app.sh`：停止服务
  - `web/install_app_to_desktop.sh`：安装桌面启动器

## 依赖要求

- macOS
- Python 3.9+
- Node.js + npm
- Codex CLI（已登录）
- `jq`（已安装）
- 可选：PDF Expert（用于从页面一键打开本地 PDF）

## 一次性初始化

```bash
./web/setup_web_app.sh
```

该步骤会安装：
- `web/backend/.venv`
- `web/frontend/node_modules`

## 启动与停止

```bash
./web/launch_web_app.sh
./web/stop_web_app.sh
```

默认地址：`http://127.0.0.1:5173`

## 桌面启动器

```bash
./web/install_app_to_desktop.sh
# 或指定安装目录（例如：Desktop/AI）
./web/install_app_to_desktop.sh /Users/chenmayao/Desktop/AI
```

默认安装到 `~/Desktop`。安装后可双击 `.app` 启动前后端。

### 桌面图标部署（自定义图标）

安装脚本生成的是 AppleScript `.app`，图标文件路径是：

- `LiteratureClassifierLauncher.app/Contents/Resources/applet.icns`

如果需要部署自定义桌面图标：

```bash
APP=~/Desktop/LiteratureClassifierLauncher.app
cp /path/to/your-icon.icns "$APP/Contents/Resources/applet.icns"
touch "$APP"
killall Finder
```

说明：
- `your-icon.icns` 建议包含完整尺寸（含 1024x1024）。
- 每次重新运行 `./web/install_app_to_desktop.sh` 后，`.app` 会被重建；如需自定义图标，请再次覆盖 `applet.icns`。

## 配置要点

### 1) 项目配置

编辑：`scripts/config/projects.yaml`

首次使用请先复制模板：

```bash
cp scripts/config/projects.example.yaml scripts/config/projects.yaml
```

每个项目至少需要：
- `paths.pdf_input_dir`
- `paths.staging_dir`
- `paths.md_output_root`

### 2) 模型接口配置（用于 Analyze 阶段）

编辑：`scripts/.env`

首次使用请先复制模板：

```bash
cp scripts/.env.example scripts/.env
```

常见变量：
- `GEMINI_API_KEY`
- `GEMINI_BASE_URL`（中转服务时必填）

## 可安全清理的生成文件

以下内容都可删除，会自动再生成：
- `__pycache__/`
- `web/frontend/dist/`
- `scripts/logs/*.log`
- `web/runtime/*`

注意：
- `web/backend/.venv`
- `web/frontend/node_modules`

这两项会影响一键启动，不建议在日常使用中删除。
