# Literature Classifier Web UI

本目录包含本地 Web 版本：

- `backend/`：FastAPI + WebSocket，复用 `scripts/src/main.py` 执行 analyze/classify。
- `frontend/`：React + Vite 三阶段界面。

## 1. 启动后端

```bash
cd web/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

## 2. 启动前端

```bash
cd web/frontend
npm install
npm run dev
```

浏览器访问：`http://127.0.0.1:5173`

## 页面说明

1. `/analyze`：输入或选择 PDF 目录路径后启动 analyze；左侧文献列表、右侧实时日志。
2. `/suggest`：点击打开本地 Codex 终端，先确认分类标签，再由 Codex 直接写 staging JSON 分类字段并移动 Markdown；页面内可直接编辑并写入分类草案。
3. `/classify`：启动 classify，查看分类统计、分类分组和实时日志。

## 说明

- 阶段 2 依赖 staging 目录下的 analyze 结果（`*.json`）。
- 阶段 2 的终端交互改为调用本地 `codex` 命令，不再依赖 Gemini 聊天接口。

## 桌面启动器（.app）

- 默认启动器路径：`~/Desktop/LiteratureClassifierLauncher.app`
- 指定目录安装：`./web/install_app_to_desktop.sh /Users/chenmayao/Desktop/AI`
- 双击后会执行 `web/launch_web_app.sh`，自动安装依赖并启动前后端。
- 停止服务：`./web/stop_web_app.sh`
- 日志目录：`web/runtime/`
