from __future__ import annotations

import asyncio
import json
import shutil
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent.parent
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
WEB_RUNTIME_ROOT = PROJECT_ROOT / "web" / "runtime"

# 复用现有脚本工程模块
sys.path.insert(0, str(SCRIPTS_ROOT))

from config.config_loader import (  # noqa: E402
    list_projects,
    load_config,
    load_config_from_pdf_dir,
)

from suggest_session import SuggestSessionManager  # noqa: E402
from task_manager import TaskManager  # noqa: E402


app = FastAPI(title="Literature Classifier Web", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

task_manager = TaskManager()
suggest_manager = SuggestSessionManager(SCRIPTS_ROOT)


class AnalyzeStartRequest(BaseModel):
    project: Optional[str] = None
    pdf_dir: Optional[str] = None
    limit: Optional[int] = None
    single: Optional[str] = None
    workers: int = Field(default=3, ge=1, le=16)


class ClassifyStartRequest(BaseModel):
    project: str


class SuggestApplyRequest(BaseModel):
    project: str
    categories: Optional[dict[str, str]] = None
    run_classify: bool = False


class OpenPdfRequest(BaseModel):
    path: str
    project: Optional[str] = None
    pdf_dir: Optional[str] = None


class OpenCodexRequest(BaseModel):
    project: str


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/projects")
def get_projects() -> dict[str, list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    for project in list_projects():
        cfg = load_config(project)
        items.append(
            {
                "id": project,
                "name": cfg.name,
                "pdf_dir": str(cfg.pdf_input_dir),
                "staging_dir": str(cfg.staging_dir),
                "md_output_root": str(cfg.md_output_root),
            }
        )
    return {"projects": items}


@app.get("/api/projects/{project}/papers")
def get_project_papers(project: str) -> dict[str, Any]:
    cfg = _get_config_or_404(project)
    papers = _build_paper_index(cfg)
    return {"project": project, "papers": papers}


@app.get("/api/analyze/papers")
def get_analyze_papers(pdf_dir: str) -> dict[str, Any]:
    cfg = _get_adhoc_config_or_400(pdf_dir)
    papers = _build_paper_index(cfg)
    return {"pdf_dir": str(cfg.pdf_input_dir), "papers": papers}


@app.get("/api/suggest/{project}")
def get_suggest_snapshot(project: str) -> dict[str, Any]:
    _ensure_project_exists(project)
    try:
        session = suggest_manager.load_session(project)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "project": project,
        "suggestions": session.suggestions,
        "draft_categories": session.draft_categories,
        "messages": session.messages,
    }


@app.post("/api/analyze/start")
async def start_analyze(req: AnalyzeStartRequest) -> dict[str, Any]:
    if req.pdf_dir and req.pdf_dir.strip():
        cfg_token = _build_path_config_token(req.pdf_dir)
    elif req.project and req.project.strip():
        _ensure_project_exists(req.project)
        cfg_token = req.project
    else:
        raise HTTPException(status_code=400, detail="analyze 需要提供 project 或 pdf_dir")

    command = [
        sys.executable,
        "src/main.py",
        "--config",
        cfg_token,
        "--mode",
        "analyze",
        "--workers",
        str(req.workers),
    ]
    if req.limit is not None and req.limit > 0:
        command.extend(["--limit", str(req.limit)])
    if req.single:
        command.extend(["--single", req.single])

    task = await task_manager.start_task(stage="analyze", command=command, cwd=str(SCRIPTS_ROOT))
    return {"task": task_manager.serialize(task)}


@app.post("/api/classify/start")
async def start_classify(req: ClassifyStartRequest) -> dict[str, Any]:
    task = await _start_classify_task(req.project)
    return {"task": task_manager.serialize(task)}


@app.post("/api/suggest/apply")
async def apply_suggest(req: SuggestApplyRequest) -> dict[str, Any]:
    _ensure_project_exists(req.project)

    try:
        result = await asyncio.to_thread(
            suggest_manager.apply_categories,
            req.project,
            req.categories,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if req.run_classify:
        task = await _start_classify_task(req.project)
        result["classify_task"] = task_manager.serialize(task)

    return result


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task 不存在: {task_id}")
    return {"task": task_manager.serialize(task), "logs": task.logs[-500:]}


@app.get("/api/pdf")
def get_pdf(path: str, project: Optional[str] = None, pdf_dir: Optional[str] = None) -> FileResponse:
    cfg = _resolve_content_config(project=project, pdf_dir=pdf_dir)
    roots = [cfg.pdf_input_dir, cfg.pdf_processed_dir]
    resolved = _resolve_safe_path(path, roots)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"PDF 不存在: {resolved}")
    # Inline preview for iframe; avoid forced browser download.
    return FileResponse(
        resolved,
        media_type="application/pdf",
        filename=resolved.name,
        content_disposition_type="inline",
    )


@app.post("/api/pdf/open")
def open_pdf(req: OpenPdfRequest) -> dict[str, str]:
    cfg = _resolve_content_config(project=req.project, pdf_dir=req.pdf_dir)
    roots = [cfg.pdf_input_dir, cfg.pdf_processed_dir]
    resolved = _resolve_safe_path(req.path, roots)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"PDF 不存在: {resolved}")

    try:
        subprocess.run(
            ["/usr/bin/open", "-a", "PDF Expert", str(resolved)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = "调用 PDF Expert 打开文件失败"
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        if stderr:
            detail = f"{detail}: {stderr}"
        elif stdout:
            detail = f"{detail}: {stdout}"
        raise HTTPException(status_code=500, detail=detail) from exc

    return {"status": "ok", "opened": str(resolved)}


@app.post("/api/codex/open")
def open_codex_terminal(req: OpenCodexRequest) -> dict[str, str]:
    project = req.project.strip()
    if not project:
        raise HTTPException(status_code=400, detail="project 不能为空")
    if shutil.which("codex") is None:
        raise HTTPException(status_code=400, detail="未找到 codex 命令，请先安装并登录 Codex CLI")

    cfg = _get_config_or_404(project)
    prompt = _build_codex_default_prompt(project, cfg)
    script_path = _write_codex_launcher_script(project, prompt)
    terminal_cmd = f"/bin/zsh {shlex.quote(str(script_path))}"

    try:
        subprocess.run(
            [
                "/usr/bin/osascript",
                "-e",
                'tell application "Terminal" to activate',
                "-e",
                f'tell application "Terminal" to do script {json.dumps(terminal_cmd, ensure_ascii=False)}',
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = "打开 Terminal 并启动 Codex 失败"
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        if stderr:
            detail = f"{detail}: {stderr}"
        elif stdout:
            detail = f"{detail}: {stdout}"
        raise HTTPException(status_code=500, detail=detail) from exc

    return {
        "status": "ok",
        "project": project,
        "launcher_script": str(script_path),
        "staging_dir": str(cfg.staging_dir),
    }


@app.get("/api/md")
def get_markdown(path: str, project: Optional[str] = None, pdf_dir: Optional[str] = None) -> PlainTextResponse:
    cfg = _resolve_content_config(project=project, pdf_dir=pdf_dir)
    roots = [cfg.md_output_root]
    resolved = _resolve_safe_path(path, roots)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"Markdown 不存在: {resolved}")

    with open(resolved, "r", encoding="utf-8") as f:
        content = f.read()
    return PlainTextResponse(content, media_type="text/markdown")


@app.websocket("/ws/tasks/{task_id}")
async def ws_task_events(websocket: WebSocket, task_id: str):
    await websocket.accept()

    record, queue = task_manager.subscribe(task_id)
    if record is None:
        await websocket.send_json({"type": "error", "message": f"task 不存在: {task_id}"})
        await websocket.close(code=4404)
        return

    try:
        await websocket.send_json(
            {
                "type": "snapshot",
                "task": task_manager.serialize(record),
                "logs": record.logs[-300:],
            }
        )

        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
    finally:
        task_manager.unsubscribe(record, queue)


@app.websocket("/ws/suggest/{project}")
async def ws_suggest_chat(websocket: WebSocket, project: str):
    await websocket.accept()

    if project not in list_projects():
        await websocket.send_json({"type": "error", "message": f"项目不存在: {project}"})
        await websocket.close(code=4404)
        return

    try:
        session = await asyncio.to_thread(suggest_manager.load_session, project)
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close(code=1011)
        return

    await websocket.send_json(
        {
            "type": "snapshot",
            "project": project,
            "suggestions": session.suggestions,
            "draft_categories": session.draft_categories,
            "messages": session.messages,
        }
    )

    while True:
        try:
            payload = await websocket.receive_json()
        except WebSocketDisconnect:
            return
        except Exception:
            await websocket.send_json({"type": "error", "message": "消息格式错误，应为 JSON"})
            continue

        msg_type = str(payload.get("type", "")).strip()

        if msg_type == "chat":
            user_message = str(payload.get("message", "")).strip()
            if not user_message:
                await websocket.send_json({"type": "error", "message": "消息不能为空"})
                continue

            await websocket.send_json({"type": "thinking", "value": True})
            try:
                result = await asyncio.to_thread(suggest_manager.chat, project, user_message)
            except Exception as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
            else:
                await websocket.send_json(
                    {
                        "type": "assistant",
                        "message": result["assistant_reply"],
                        "draft_categories": result["draft_categories"],
                        "messages": result["messages"],
                    }
                )
            finally:
                await websocket.send_json({"type": "thinking", "value": False})

        elif msg_type == "set_draft":
            draft = payload.get("draft_categories", {})
            try:
                new_draft = await asyncio.to_thread(suggest_manager.update_draft, project, draft)
            except Exception as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
            else:
                await websocket.send_json({"type": "draft_updated", "draft_categories": new_draft})

        elif msg_type == "apply":
            draft = payload.get("draft_categories")
            run_classify = bool(payload.get("run_classify", False))

            try:
                applied = await asyncio.to_thread(suggest_manager.apply_categories, project, draft)
            except Exception as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
                continue

            await websocket.send_json({"type": "applied", **applied})

            if run_classify:
                try:
                    task = await _start_classify_task(project)
                except Exception as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)})
                else:
                    await websocket.send_json(
                        {
                            "type": "classify_started",
                            "task": task_manager.serialize(task),
                        }
                    )

        else:
            await websocket.send_json({"type": "error", "message": f"未知消息类型: {msg_type}"})


async def _start_classify_task(project: str):
    _ensure_project_exists(project)
    command = [
        sys.executable,
        "src/main.py",
        "--config",
        project,
        "--mode",
        "classify",
    ]
    return await task_manager.start_task(stage="classify", command=command, cwd=str(SCRIPTS_ROOT))


def _get_config_or_404(project: str):
    try:
        return load_config(project)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _get_adhoc_config_or_400(pdf_dir: str):
    try:
        return load_config_from_pdf_dir(pdf_dir)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"无效路径: {pdf_dir} ({exc})") from exc


def _build_path_config_token(pdf_dir: str) -> str:
    return f"path:{Path(pdf_dir).expanduser().resolve()}"


def _resolve_content_config(project: Optional[str], pdf_dir: Optional[str]):
    if project and project.strip():
        return _get_config_or_404(project)
    if pdf_dir and pdf_dir.strip():
        return _get_adhoc_config_or_400(pdf_dir)
    raise HTTPException(status_code=400, detail="读取文件需要提供 project 或 pdf_dir")


def _ensure_project_exists(project: str) -> None:
    if project not in list_projects():
        raise HTTPException(status_code=404, detail=f"项目不存在: {project}")


def _build_paper_index(cfg) -> list[dict[str, Any]]:
    staging_map: dict[str, dict[str, Any]] = {}

    for json_path in sorted(cfg.staging_dir.glob("*.json")):
        if json_path.name == "category_suggestions.json":
            continue
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                item = json.load(f)
            source_pdf = str(item.get("source_pdf", "")).strip()
            if source_pdf:
                staging_map[source_pdf] = item
        except Exception:
            continue

    source_names = {p.name for p in cfg.pdf_input_dir.glob("*.pdf")}
    source_names.update({p.name for p in cfg.pdf_processed_dir.glob("*.pdf")})
    source_names.update(staging_map.keys())

    papers: list[dict[str, Any]] = []

    for source_pdf in sorted(source_names):
        pending_pdf = cfg.pdf_input_dir / source_pdf
        processed_pdf = cfg.pdf_processed_dir / source_pdf
        staging = staging_map.get(source_pdf)

        processed_from_staging: Optional[Path] = None
        if staging and staging.get("processed_pdf_path"):
            candidate = Path(str(staging["processed_pdf_path"]))
            if candidate.exists():
                processed_from_staging = candidate

        display_pdf = None
        if pending_pdf.exists():
            display_pdf = pending_pdf
        elif processed_pdf.exists():
            display_pdf = processed_pdf
        elif processed_from_staging is not None:
            display_pdf = processed_from_staging

        md_path = None
        md_filename = None
        title = None
        category_name = None
        if staging:
            md_filename = staging.get("md_filename")
            analysis = staging.get("analysis", {}) if isinstance(staging, dict) else {}
            if isinstance(analysis, dict):
                title = analysis.get("title")

            category_name = staging.get("final_category_name")
            if md_filename:
                candidate_paths: list[Path] = []
                if category_name:
                    candidate_paths.append(cfg.md_output_root / category_name / md_filename)
                candidate_paths.append(cfg.md_output_root / cfg.unclassified_dir_name / md_filename)

                for candidate in candidate_paths:
                    if candidate.exists():
                        md_path = candidate
                        break

        if pending_pdf.exists() and staging is None:
            status = "pending"
        elif staging and staging.get("final_category_name"):
            status = "classified"
        elif staging:
            status = "analyzed"
        else:
            status = "unknown"

        papers.append(
            {
                "source_pdf": source_pdf,
                "title": title,
                "status": status,
                "pdf_path": str(display_pdf) if display_pdf else None,
                "processed_pdf_path": str(processed_from_staging or processed_pdf)
                if (processed_from_staging or processed_pdf.exists())
                else None,
                "md_filename": md_filename,
                "md_path": str(md_path) if md_path else None,
                "category_name": category_name,
            }
        )

    return papers


def _resolve_safe_path(raw_path: str, roots: list[Path]) -> Path:
    path = Path(raw_path).expanduser().resolve()

    for root in roots:
        root_resolved = root.expanduser().resolve()
        if path == root_resolved or root_resolved in path.parents:
            return path

    raise HTTPException(status_code=403, detail="路径不在允许范围内")


def _build_codex_default_prompt(project: str, cfg) -> str:
    return (
        "你是科研文献分类助手。"
        f"当前项目ID是 {project}，文献分析结果目录是 {cfg.staging_dir}。"
        "请先阅读 staging 里的 JSON，提出 3-8 个分类标签并等待我确认。"
        "在我明确回复“确认标签”之前，不要执行分类。"
        "我回复“确认标签”后，请直接完成分类，不要调用任何远程 API，也不要运行 main.py 的 classify 模式。"
        "具体要求："
        "1) 把标签写入 config/projects.yaml 中该项目的 classification.categories（并确保 classification.enabled=true）。"
        "2) 遍历 staging 下每篇文献 JSON，为每篇写入 final_category、final_category_name、category_reasoning。"
        f"3) 将 Markdown 从 {cfg.md_output_root / cfg.unclassified_dir_name} 移动到 {cfg.md_output_root}/<分类名>/。"
        "4) 若目标 md 已存在，自动加时间戳后缀避免覆盖。"
        "5) 最后用中文汇总每类数量与总计。"
    )


def _write_codex_launcher_script(project: str, prompt: str) -> Path:
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in project).strip("_")
    if not safe_name:
        safe_name = "project"

    WEB_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    script_path = WEB_RUNTIME_ROOT / f"launch_codex_{safe_name}.sh"

    codex_cmd = " ".join(
        [
            "codex",
            "--no-alt-screen",
            "--ask-for-approval",
            "never",
            "--sandbox",
            "danger-full-access",
            "-C",
            shlex.quote(str(SCRIPTS_ROOT)),
            shlex.quote(prompt),
        ]
    )

    script_content = "\n".join(
        [
            "#!/bin/zsh",
            "set -euo pipefail",
            f'cd {shlex.quote(str(SCRIPTS_ROOT))}',
            'echo "已启动 Codex 分类终端（项目: ' + safe_name + '）"',
            'echo "提示：先和 Codex 确认标签；确认后由 Codex 直接写 JSON 并移动 Markdown。"',
            codex_cmd,
            "",
        ]
    )

    script_path.write_text(script_content, encoding="utf-8")
    script_path.chmod(0o755)
    return script_path


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
