# 本地桌面启动器（.app）设计

日期：2026-02-24

## 目标

提供一个可双击的 macOS `.app`，点击后自动完成：

1. 检查并安装后端依赖（Python venv + pip）
2. 检查并安装前端依赖（npm install）
3. 后台启动后端与前端
4. 打开浏览器访问 `http://127.0.0.1:5173`

## 方案

采用 `App Bundle + Shell Launcher`：

1. `web/launch_web_app.sh` 作为唯一启动入口。
2. `.app` 的可执行文件只调用该脚本。
3. `web/stop_web_app.sh` 用于停止两端服务。
4. 运行日志与 PID 存放到 `web/runtime/`。

## 关键细节

1. 启动脚本幂等：若 PID 进程仍存活则不重复拉起。
2. 兼容权限问题：将 npm/pip 缓存重定向到 `web/runtime`。
3. 失败可追踪：写入 `launcher.log/backend.log/frontend.log`。
4. 自动打开浏览器失败不影响服务启动。

## 交付物

1. `web/launch_web_app.sh`
2. `web/stop_web_app.sh`
3. `web/app/LiteratureClassifierLauncher.app`
