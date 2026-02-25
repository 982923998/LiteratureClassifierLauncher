from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Tuple


_ANALYZE_SUMMARY_RE = re.compile(r"分析完成：成功\s*(\d+)\s*篇，失败\s*(\d+)\s*篇")
_CLASSIFY_SUMMARY_RE = re.compile(r"分类完成：移动\s*(\d+)\s*篇，跳过\s*(\d+)\s*篇")
_CLASSIFY_STAT_RE = re.compile(r"^\s{2,}(.+?):\s*(\d+)\s*篇$")


@dataclass
class TaskRecord:
    task_id: str
    stage: str
    command: list[str]
    cwd: str
    status: str = "pending"
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    return_code: Optional[int] = None
    logs: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    subscribers: set[asyncio.Queue] = field(default_factory=set, repr=False)


class TaskManager:
    """Track subprocess tasks and stream their logs to websocket subscribers."""

    MAX_LOG_LINES = 4000

    def __init__(self):
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = asyncio.Lock()

    async def start_task(self, stage: str, command: list[str], cwd: str) -> TaskRecord:
        task_id = uuid.uuid4().hex[:12]
        record = TaskRecord(task_id=task_id, stage=stage, command=command, cwd=cwd)

        async with self._lock:
            self._tasks[task_id] = record

        asyncio.create_task(self._run_task(record))
        return record

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        return self._tasks.get(task_id)

    def serialize(self, record: TaskRecord) -> dict[str, Any]:
        return {
            "task_id": record.task_id,
            "stage": record.stage,
            "command": record.command,
            "cwd": record.cwd,
            "status": record.status,
            "started_at": record.started_at,
            "ended_at": record.ended_at,
            "return_code": record.return_code,
            "summary": record.summary,
            "log_lines": len(record.logs),
        }

    def subscribe(self, task_id: str) -> Tuple[Optional[TaskRecord], asyncio.Queue]:
        record = self._tasks.get(task_id)
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        if record is not None:
            record.subscribers.add(queue)
        return record, queue

    def unsubscribe(self, record: TaskRecord, queue: asyncio.Queue) -> None:
        record.subscribers.discard(queue)

    async def _run_task(self, record: TaskRecord) -> None:
        record.status = "running"
        record.started_at = self._iso_now()
        self._broadcast(record, {"type": "status", "task": self.serialize(record)})

        process = await asyncio.create_subprocess_exec(
            *record.command,
            cwd=record.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        assert process.stdout is not None
        while True:
            raw_line = await process.stdout.readline()
            if not raw_line:
                break

            line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            if not line:
                continue

            record.logs.append(line)
            if len(record.logs) > self.MAX_LOG_LINES:
                record.logs = record.logs[-self.MAX_LOG_LINES :]

            self._update_summary(record, line)
            self._broadcast(record, {"type": "log", "line": line})

        record.return_code = await process.wait()
        record.status = "success" if record.return_code == 0 else "failed"
        record.ended_at = self._iso_now()
        self._broadcast(record, {"type": "status", "task": self.serialize(record)})

    def _update_summary(self, record: TaskRecord, line: str) -> None:
        analyze_match = _ANALYZE_SUMMARY_RE.search(line)
        if analyze_match:
            record.summary["success"] = int(analyze_match.group(1))
            record.summary["failed"] = int(analyze_match.group(2))
            return

        classify_match = _CLASSIFY_SUMMARY_RE.search(line)
        if classify_match:
            record.summary["moved"] = int(classify_match.group(1))
            record.summary["skipped"] = int(classify_match.group(2))
            return

        # logging 包会在前面加时间戳，提取 "  类别: X 篇" 这段
        if " - INFO -   " in line:
            candidate = line.split(" - INFO -   ", 1)[1]
        else:
            candidate = line

        stat_match = _CLASSIFY_STAT_RE.match(candidate)
        if stat_match:
            stats = record.summary.setdefault("category_counts", {})
            stats[stat_match.group(1)] = int(stat_match.group(2))

    def _broadcast(self, record: TaskRecord, event: dict[str, Any]) -> None:
        for queue in tuple(record.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # 慢消费者场景下丢弃该条事件，避免阻塞任务执行
                continue

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()
