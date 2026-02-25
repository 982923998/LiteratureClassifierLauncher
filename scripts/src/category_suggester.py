"""
分类建议模块
读取 staging 目录中的所有文献分析 JSON，
调用 Gemini 给出分类方案建议和初步分类结果，
保存为 staging/category_suggestions.json 并打印可读摘要。
"""
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from config import active_config

if TYPE_CHECKING:
    from src.gemini_analyzer import GeminiAnalyzer

logger = logging.getLogger(__name__)


class CategorySuggester:
    """基于已分析文献，建议分类方案"""

    SUGGESTIONS_FILENAME = "category_suggestions.json"

    def __init__(self, gemini_analyzer: "GeminiAnalyzer"):
        self.analyzer = gemini_analyzer
        self.logger = logger

    def suggest(self) -> dict:
        """
        读取所有 staging JSON → 调用 Gemini 建议分类 → 保存并打印。

        Returns:
            建议结果 dict，含 suggested_categories, paper_classifications, overall_reasoning
        """
        cfg = active_config.get()
        staging_dir = cfg.staging_dir
        staging_jsons = self._load_staging_jsons(staging_dir)

        if not staging_jsons:
            raise RuntimeError(
                f"staging 目录为空：{staging_dir}\n"
                "请先运行 --mode analyze 分析文献。"
            )

        self.logger.info(f"从 staging 读取 {len(staging_jsons)} 篇文献，发送给 Gemini...")

        prompt = self._build_suggest_prompt(staging_jsons)
        response_text = self.analyzer.call_with_text_prompt(prompt)
        suggestions = self._parse_suggest_response(response_text, staging_jsons)

        # 保存
        output_path = staging_dir / self.SUGGESTIONS_FILENAME
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(suggestions, f, ensure_ascii=False, indent=2)

        self._print_summary(suggestions, output_path)
        return suggestions

    def _load_staging_jsons(self, staging_dir: Path) -> list[dict]:
        """读取 staging 目录下所有 JSON（排除 category_suggestions.json）"""
        jsons = []
        for p in sorted(staging_dir.glob("*.json")):
            if p.name == self.SUGGESTIONS_FILENAME:
                continue
            try:
                with open(p, "r", encoding="utf-8") as f:
                    jsons.append(json.load(f))
            except Exception as e:
                self.logger.warning(f"读取 {p.name} 失败，跳过: {e}")
        return jsons

    def _build_suggest_prompt(self, staging_jsons: list[dict]) -> str:
        """构建分类建议 prompt"""
        paper_summaries = []
        for i, item in enumerate(staging_jsons):
            analysis = item.get("analysis", {})
            paper_summaries.append({
                "id": i,
                "source_pdf": item.get("source_pdf", ""),
                "title": analysis.get("title", "N/A"),
                "research_question": analysis.get("research_question", "N/A"),
                "main_conclusion": analysis.get("main_conclusion", "N/A"),
            })

        return (
            "你是一个专业的科研文献分类专家。\n"
            f"以下是 {len(paper_summaries)} 篇科研文献的摘要信息。\n"
            "请根据这些文献的内容，建议 3-6 个有意义的分类类别，\n"
            "并对每篇文献给出初步分类建议。\n\n"
            "文献列表（JSON 格式）：\n"
            f"{json.dumps(paper_summaries, ensure_ascii=False, indent=2)}\n\n"
            "请返回如下 JSON 格式（只返回 JSON，不要有其他文字）：\n"
            "{\n"
            '  "suggested_categories": {\n'
            '    "1": "类别名称（含简要说明）",\n'
            '    "2": "类别名称（含简要说明）"\n'
            "  },\n"
            '  "paper_classifications": [\n'
            '    {"id": 0, "source_pdf": "文件名.pdf", "suggested_category": 1, "reasoning": "理由"}\n'
            "  ],\n"
            '  "overall_reasoning": "为什么建议这样的分类方案"\n'
            "}"
        )

    def _parse_suggest_response(
        self, response_text: str, staging_jsons: list[dict]
    ) -> dict:
        """解析建议响应，做基本校验"""
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
        except json.JSONDecodeError as e:
            self.logger.error(f"分类建议响应解析失败: {e}\n响应内容: {text[:500]}")
            raise ValueError("无法解析分类建议响应为 JSON")

        # 用 id 补齐 source_pdf（防止 LLM 写错文件名）
        id_to_pdf = {i: item.get("source_pdf", "") for i, item in enumerate(staging_jsons)}
        for item in result.get("paper_classifications", []):
            idx = item.get("id")
            if isinstance(idx, int) and idx in id_to_pdf:
                item["source_pdf"] = id_to_pdf[idx]

        return result

    def _print_summary(self, suggestions: dict, output_path: Path) -> None:
        """打印人类可读的分类建议摘要"""
        cats = suggestions.get("suggested_categories", {})
        classifications = suggestions.get("paper_classifications", [])
        reasoning = suggestions.get("overall_reasoning", "")

        # 统计每个类别的文献数
        cat_counts: dict[str, int] = {}
        cat_papers: dict[str, list[str]] = {}
        for item in classifications:
            cat = str(item.get("suggested_category", "?"))
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
            cat_papers.setdefault(cat, []).append(item.get("source_pdf", ""))

        print("\n" + "=" * 60)
        print(f"文献分类建议")
        print("=" * 60)
        print(f"共分析 {len(classifications)} 篇文献，建议以下 {len(cats)} 个类别：\n")

        for cat_id, cat_name in sorted(cats.items(), key=lambda x: str(x[0])):
            count = cat_counts.get(str(cat_id), 0)
            print(f"类别 {cat_id}: {cat_name}（建议归入 {count} 篇）")
            for pdf in cat_papers.get(str(cat_id), [])[:5]:  # 最多显示5篇
                print(f"  - {pdf}")
            if len(cat_papers.get(str(cat_id), [])) > 5:
                print(f"  ... 等共 {count} 篇")
            print()

        if reasoning:
            print(f"建议理由：\n{reasoning}\n")

        print(f"详细结果已保存至: {output_path}")
        print(
            "\n下一步：\n"
            "  1. 在 scripts/config/projects.yaml 中更新对应项目的 categories\n"
            "  2. 运行 --mode classify 完成分类"
        )
        print("=" * 60 + "\n")
