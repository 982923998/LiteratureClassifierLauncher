from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml

from config.config_loader import load_config
from src.category_suggester import CategorySuggester
from src.gemini_analyzer import GeminiAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class SuggestSession:
    session_id: str
    project: str
    suggestions: dict[str, Any]
    draft_categories: dict[str, str]
    messages: list[dict[str, str]] = field(default_factory=list)


class SuggestSessionManager:
    """Manage per-project chat sessions for category confirmation."""

    def __init__(self, scripts_root: Path):
        self.scripts_root = scripts_root
        self.projects_yaml = scripts_root / "config" / "projects.yaml"
        self.sessions: dict[str, SuggestSession] = {}

    def load_session(self, project: str) -> SuggestSession:
        cfg = load_config(project)
        suggestions_path = cfg.staging_dir / CategorySuggester.SUGGESTIONS_FILENAME
        suggestions = self._load_or_build_suggestions(cfg, suggestions_path)

        if cfg.categories:
            draft = self._normalize_categories(cfg.categories)
        else:
            draft = self._normalize_categories(suggestions.get("suggested_categories", {}))

        session = self.sessions.get(project)
        if session is None:
            session = SuggestSession(
                session_id=f"{project}-session",
                project=project,
                suggestions=suggestions,
                draft_categories=draft,
                messages=[],
            )
            self.sessions[project] = session
        else:
            session.suggestions = suggestions
            if not session.draft_categories:
                session.draft_categories = draft

        return session

    def chat(self, project: str, user_message: str) -> dict[str, Any]:
        session = self.load_session(project)
        cfg = load_config(project)

        analyzer = GeminiAnalyzer(
            model_name=cfg.gemini_model,
            temperature=min(max(cfg.gemini_temperature, 0.1), 0.4),
        )

        prompt = self._build_chat_prompt(session, user_message)
        raw_response = analyzer.call_with_text_prompt(prompt)
        parsed = self._parse_chat_response(raw_response)

        assistant_reply = parsed.get("assistant_reply", "已根据你的要求调整分类草案。")
        draft_categories = parsed.get("draft_categories", session.draft_categories)
        normalized = self._normalize_categories(draft_categories)

        session.messages.append({"role": "user", "content": user_message})
        session.messages.append({"role": "assistant", "content": assistant_reply})
        session.draft_categories = normalized

        return {
            "assistant_reply": assistant_reply,
            "draft_categories": session.draft_categories,
            "messages": session.messages,
        }

    def _load_or_build_suggestions(self, cfg, suggestions_path: Path) -> dict[str, Any]:
        summaries = self._build_paper_summaries(cfg.staging_dir)
        if not summaries:
            raise FileNotFoundError(
                f"未找到可用文献分析结果：{cfg.staging_dir}。请先运行 analyze 阶段。"
            )

        if suggestions_path.exists():
            with open(suggestions_path, "r", encoding="utf-8") as f:
                suggestions = json.load(f)
        else:
            # 支持“只做了 analyze，还没跑 suggest”的场景，先进入可聊天状态。
            suggestions = {
                "suggested_categories": {},
                "paper_classifications": [
                    {
                        "id": item["id"],
                        "source_pdf": item["source_pdf"],
                        "suggested_category": None,
                        "reasoning": "",
                    }
                    for item in summaries
                ],
                "overall_reasoning": "尚未生成自动分类建议，请通过对话生成分类草案。",
            }

        suggestions["paper_summaries"] = summaries
        return suggestions

    def _build_paper_summaries(self, staging_dir: Path) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        json_files = sorted(staging_dir.glob("*.json"))
        idx = 0
        for path in json_files:
            if path.name == CategorySuggester.SUGGESTIONS_FILENAME:
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    item = json.load(f)
            except Exception as exc:
                logger.warning("读取 staging 文件失败，跳过 %s: %s", path.name, exc)
                continue

            analysis = item.get("analysis", {}) if isinstance(item, dict) else {}
            if not isinstance(analysis, dict):
                analysis = {}

            summaries.append(
                {
                    "id": idx,
                    "source_pdf": str(item.get("source_pdf", path.with_suffix(".pdf").name)),
                    "title": self._truncate(str(analysis.get("title", "N/A")), 220),
                    "research_question": self._truncate(
                        str(analysis.get("research_question", "N/A")), 380
                    ),
                    "main_conclusion": self._truncate(
                        str(analysis.get("main_conclusion", "N/A")), 380
                    ),
                }
            )
            idx += 1

        return summaries

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        text = text.strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "..."

    def apply_categories(
        self,
        project: str,
        categories: Optional[Union[Dict[str, str], Dict[int, str]]] = None,
    ) -> dict[str, Any]:
        session = self.load_session(project)

        if categories is None:
            to_apply = session.draft_categories
        else:
            to_apply = self._normalize_categories(categories)
            session.draft_categories = to_apply

        with open(self.projects_yaml, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        projects = data.setdefault("projects", {})
        if project not in projects:
            raise KeyError(f"projects.yaml 中不存在项目: {project}")

        target = projects[project]
        classification = target.setdefault("classification", {})
        classification["enabled"] = True

        int_keyed = {int(k): str(v) for k, v in sorted(to_apply.items(), key=lambda kv: int(kv[0]))}
        classification["categories"] = int_keyed

        with open(self.projects_yaml, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

        return {
            "project": project,
            "categories": self._normalize_categories(int_keyed),
            "projects_yaml": str(self.projects_yaml),
        }

    def update_draft(
        self,
        project: str,
        draft_categories: Union[Dict[str, str], Dict[int, str]],
    ) -> dict[str, str]:
        session = self.load_session(project)
        session.draft_categories = self._normalize_categories(draft_categories)
        return session.draft_categories

    def _build_chat_prompt(self, session: SuggestSession, user_message: str) -> str:
        recent_messages = session.messages[-8:]
        recent_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in recent_messages
        )
        paper_summaries = session.suggestions.get("paper_summaries", [])

        return (
            "你是科研文献分类助手。请根据用户要求更新分类草案。\n"
            "你必须输出 JSON（只输出 JSON，不要 markdown，不要解释）。\n"
            "格式：\n"
            "{\n"
            '  "assistant_reply": "给用户的简短中文回复",\n'
            '  "draft_categories": {"1": "类别名称", "2": "类别名称"}\n'
            "}\n\n"
            "约束：\n"
            "1. draft_categories 的 key 必须是正整数字符串（1,2,3...）。\n"
            "2. value 必须是非空中文分类名。\n"
            "3. 若用户要求合并分类，请给出合并后的完整草案。\n"
            "4. 若用户要求重命名/新增/删除，也返回更新后的完整草案。\n"
            "5. 尽量保持编号稳定；若必须重排，保持连续编号。\n\n"
            f"文献摘要（用于本轮分类讨论）：\n{json.dumps(paper_summaries, ensure_ascii=False, indent=2)}\n\n"
            f"当前建议（suggested_categories）：\n{json.dumps(session.suggestions.get('suggested_categories', {}), ensure_ascii=False, indent=2)}\n\n"
            f"当前草案（draft_categories）：\n{json.dumps(session.draft_categories, ensure_ascii=False, indent=2)}\n\n"
            f"历史对话（最近若干轮）：\n{recent_text if recent_text else 'N/A'}\n\n"
            f"用户最新消息：{user_message}\n"
        )

    def _parse_chat_response(self, response_text: str) -> dict[str, Any]:
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("suggest chat JSON 解析失败: %s", exc)
            logger.error("原始响应: %s", text[:400])
            raise ValueError("AI 返回格式异常，无法解析为 JSON")

        if not isinstance(result, dict):
            raise ValueError("AI 返回格式错误：应为 JSON 对象")

        return result

    def _normalize_categories(self, categories: dict[Any, Any]) -> dict[str, str]:
        normalized: list[tuple[int, str]] = []

        for key, value in categories.items():
            key_str = str(key).strip()
            val_str = str(value).strip()
            if not key_str or not val_str:
                continue
            try:
                key_int = int(key_str)
            except ValueError:
                continue
            if key_int <= 0:
                continue
            normalized.append((key_int, val_str))

        normalized.sort(key=lambda item: item[0])

        # 重新连续编号，避免出现 1,3,7 这种稀疏键
        compact = {str(idx + 1): label for idx, (_, label) in enumerate(normalized)}
        return compact
