"""
Markdown 文件生成器
"""
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import logging
import re
from config import active_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MarkdownGenerator:
    """Markdown 报告生成器"""

    def __init__(self):
        self.logger = logger

    def generate_markdown(self, analysis_result: Dict[str, Any]) -> str:
        """
        根据分析结果生成 Markdown 文档（analyze 阶段，不含分类信息）

        Args:
            analysis_result: Gemini 分析结果

        Returns:
            str: Markdown 格式的文档内容
        """
        cfg = active_config.get()
        template_string = cfg.markdown_template

        # analyze 阶段不注入分类段
        template_string = template_string.replace("{{classification_section}}", "")
        template_string = self._strip_figures_section(template_string)

        # 自定义关注点段落注入
        if cfg.custom_areas:
            parts = ["## 用户自定义关注点\n\n"]
            for key, title in cfg.custom_areas.items():
                parts.append(f"### {title}\n{{{{{key}}}}}\n\n")
            custom_areas_section = "".join(parts)
        else:
            custom_areas_section = ""
        template_string = template_string.replace("{{custom_areas_section}}", custom_areas_section)

        return self._render_template(template_string, analysis_result)

    @staticmethod
    def _strip_figures_section(template: str) -> str:
        """移除图表解析段，避免输出图片解析内容。"""
        if not template:
            return template
        cleaned = template
        cleaned = re.sub(r"\n##\s*图表解析\s*\n\s*\{\{figures\}\}\s*\n", "\n\n", cleaned)
        cleaned = cleaned.replace("{{figures}}", "")
        return cleaned

    def sanitize_filename(self, title: str) -> str:
        """
        清理文件名，移除非法字符

        Args:
            title: 原始标题

        Returns:
            str: 清理后的文件名（含 .md 后缀）
        """
        illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        filename = title
        for char in illegal_chars:
            filename = filename.replace(char, '_')

        max_length = 100
        if len(filename) > max_length:
            filename = filename[:max_length]

        if not filename.strip():
            filename = "untitled"

        return filename.strip() + ".md"

    def move_to_category(self, md_filename: str, category_name: str) -> bool:
        """
        将 Markdown 文件从 0.未分类/ 移动到 category_name/ 目录。

        Args:
            md_filename: Markdown 文件名（如 "paper_title.md"）
            category_name: 目标分类目录名

        Returns:
            bool: 是否移动成功
        """
        cfg = active_config.get()
        src = cfg.md_output_root / cfg.unclassified_dir_name / md_filename

        if not src.exists():
            self.logger.warning(f"文件不存在，跳过移动: {src}")
            return False

        dest_dir = cfg.md_output_root / category_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest = dest_dir / md_filename
        if dest.exists():
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            stem = md_filename[:-3] if md_filename.endswith(".md") else md_filename
            dest = dest_dir / f"{stem}_{timestamp}.md"

        shutil.move(str(src), str(dest))
        self.logger.info(f"✓ 已移动: {md_filename} → {category_name}/")
        return True

    def _render_template(self, template: str, data: Dict[str, Any]) -> str:
        pattern = re.compile(r"\{\{([^}]+)\}\}")

        def replace_placeholder(match: re.Match) -> str:
            key_path = match.group(1).strip()
            return self._get_nested_value(data, key_path)

        return pattern.sub(replace_placeholder, template)

    def _get_nested_value(self, data: Dict[str, Any], key_path: str) -> str:
        keys = [k.strip() for k in key_path.split('.') if k.strip()]
        current: Any = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current.get(key)
            else:
                return 'N/A'
        if current is None:
            return 'N/A'
        return str(current)
