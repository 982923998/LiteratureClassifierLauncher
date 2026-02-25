"""
配置加载器
从 projects.yaml 加载项目配置，返回类型化的 ProjectConfig 对象
projects.yaml 只需填写项目差异，其余使用以下默认值
"""
from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_YAML_PATH = Path(__file__).parent / "projects.yaml"

# -----------------------------------------------------------------------
# 默认模板（所有项目共用，可在 projects.yaml 中 prompt 节点下覆盖）
# -----------------------------------------------------------------------

_DEFAULT_PREAMBLE = (
    "你是一个专业的科研文献分析助手。请仔细阅读这篇 PDF 文献，"
    "提取关键信息并用中文回答。"
)

_DEFAULT_JSON_SCHEMA = """\
{
    "entry_id": "唯一标识符",
    "year": "发表年份",
    "authors": "作者",
    "journal": "期刊",
    "title": "文献标题",
    "research_question": "科学问题",
    "methodology": {
        "dataset": "数据集",
        "data_modality": "数据模态",
        "core_model": "核心模型/算法",
        "analysis_pipeline": "分析流程"
    },
    "main_conclusion": "主要结论",
    "discussion_summary": "逐段概括讨论部分的核心内容（markdown列表格式，每段一个列表项，保留段落顺序）"{{CLASSIFICATION_FIELDS}}
}"""

_DEFAULT_MARKDOWN_TEMPLATE = """\
# {{title}}

## 基本信息

- **Entry ID**: {{entry_id}}
- **发表年份**: {{year}}
- **作者**: {{authors}}
- **期刊**: {{journal}}
- **来源PDF**: {{source_pdf}}

## 科学问题

{{research_question}}

## 研究方法

### 数据集
{{methodology.dataset}}

### 数据模态
{{methodology.data_modality}}

### 核心模型/算法
{{methodology.core_model}}

### 分析流程
{{methodology.analysis_pipeline}}

## 主要结论

{{main_conclusion}}

## 讨论概括

{{discussion_summary}}

{{custom_areas_section}}{{classification_section}}---
*本文档由 Gemini API 自动生成*
"""


# -----------------------------------------------------------------------
# 数据类
# -----------------------------------------------------------------------

@dataclass
class ProjectConfig:
    name: str
    pdf_input_dir: Path
    pdf_processed_dir: Path
    md_output_root: Path
    staging_dir: Path
    log_dir: Path
    gemini_model: str
    gemini_temperature: float
    classification_enabled: bool
    unclassified_dir_name: str
    categories: dict[int, str]
    prompt_preamble: str
    json_schema_template: str
    markdown_template: str
    custom_areas: dict[str, str] = field(default_factory=dict)


# -----------------------------------------------------------------------
# 加载函数
# -----------------------------------------------------------------------

def load_config(project_name: str) -> ProjectConfig:
    """
    从 projects.yaml 加载指定项目配置。
    未填写的字段使用默认值，所有路径解析为绝对路径并自动创建目录。
    """
    # 支持临时路径配置：--config "path:/absolute/or/relative/path"
    if project_name.startswith("path:"):
        raw_path = project_name[len("path:") :].strip()
        if not raw_path:
            raise KeyError("path 配置为空，请使用 --config 'path:/你的PDF目录'")
        return load_config_from_pdf_dir(raw_path)

    with open(_YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    projects = data.get("projects", {})
    if project_name not in projects:
        available = ", ".join(projects.keys())
        raise KeyError(
            f"项目 '{project_name}' 不存在于 projects.yaml。可用项目：{available}"
        )

    raw = projects[project_name]
    config = _build_config(
        name=raw.get("name", project_name),
        pdf_dir=Path(raw["pdf_dir"]).expanduser(),
        raw=raw,
    )
    _ensure_dirs(config)
    return config


def load_config_from_pdf_dir(pdf_dir: str | Path, ensure_dirs: bool = True) -> ProjectConfig:
    """
    构造临时配置（不依赖 projects.yaml），用于 Analyze 阶段路径直选。
    """
    path = Path(pdf_dir).expanduser().resolve()
    raw: dict[str, Any] = {"pdf_dir": str(path)}
    config = _build_config(
        name=f"Path: {path.name or 'ad_hoc'}",
        pdf_dir=path,
        raw=raw,
    )
    if ensure_dirs:
        _ensure_dirs(config)
    return config


def list_projects() -> list[str]:
    """返回 projects.yaml 中所有项目名"""
    with open(_YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return list(data.get("projects", {}).keys())


def _build_config(name: str, pdf_dir: Path, raw: dict[str, Any]) -> ProjectConfig:
    classification = raw.get("classification", {})
    raw_categories = classification.get("categories") or {}
    categories: dict[int, str] = {int(k): str(v) for k, v in raw_categories.items()}

    prompt = raw.get("prompt", {})
    scripts_root = Path(__file__).parent.parent

    return ProjectConfig(
        name=name,
        pdf_input_dir=pdf_dir,
        pdf_processed_dir=pdf_dir / "processed_papers",
        md_output_root=pdf_dir / "Classification",
        staging_dir=pdf_dir / "staging",
        log_dir=scripts_root / "logs",
        gemini_model=raw.get("model", {}).get("name", "gemini-2.5-flash"),
        gemini_temperature=float(raw.get("model", {}).get("temperature", 0.1)),
        classification_enabled=bool(classification.get("enabled", False)),
        unclassified_dir_name=classification.get("unclassified_dir", "0. 未分类"),
        categories=categories,
        prompt_preamble=prompt.get("preamble", _DEFAULT_PREAMBLE),
        json_schema_template=prompt.get("json_schema_template", _DEFAULT_JSON_SCHEMA),
        markdown_template=prompt.get("markdown_template", _DEFAULT_MARKDOWN_TEMPLATE),
        custom_areas=raw.get("custom_areas") or {},
    )


def _ensure_dirs(config: ProjectConfig) -> None:
    config.pdf_input_dir.mkdir(parents=True, exist_ok=True)
    config.pdf_processed_dir.mkdir(parents=True, exist_ok=True)
    config.md_output_root.mkdir(parents=True, exist_ok=True)
    config.staging_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)
    (config.md_output_root / config.unclassified_dir_name).mkdir(parents=True, exist_ok=True)
    if config.classification_enabled:
        for category_name in config.categories.values():
            (config.md_output_root / category_name).mkdir(parents=True, exist_ok=True)
