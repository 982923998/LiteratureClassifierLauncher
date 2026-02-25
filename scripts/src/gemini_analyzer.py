"""
Gemini API 集成模块
支持官方 Gemini API 和 OpenAI 兼容的中转服务
支持直接上传 PDF 文件给 Gemini 分析
"""
import asyncio
import os
import base64
import re
from pathlib import Path
from dotenv import load_dotenv
import logging
from typing import Dict, Any, Optional
import json
from config import active_config

# 始终以 scripts/.env 为准，避免被外部空环境变量覆盖。
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_FILE, override=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GeminiAnalyzer:
    """Gemini API 分析器"""

    def __init__(self, model_name: str = "gemini-2.5-flash", temperature: float = 0.1):
        self.logger = logger
        self.model_name = model_name
        self.temperature = temperature
        # 中转服务场景下，输出 token 偶发被截断，适当放宽上限降低 JSON 截断概率。
        self.max_output_tokens = int(os.getenv("LC_MAX_OUTPUT_TOKENS", "20000"))

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or api_key == "your_api_key_here":
            raise ValueError(
                "请在 .env 文件中设置 GEMINI_API_KEY\n"
                "获取 API Key: https://aistudio.google.com/app/apikey"
            )

        base_url = os.getenv("GEMINI_BASE_URL")
        self._api_key = api_key

        if not base_url and api_key.startswith("sk-"):
            raise ValueError(
                "检测到 GEMINI_API_KEY 为 'sk-' 格式且 GEMINI_BASE_URL 为空。\n"
                "这通常是中转服务密钥，请在 scripts/.env 设置 GEMINI_BASE_URL（例如 https://openkey.cloud）"
            )

        if base_url:
            self.logger.info(f"使用中转服务: {base_url}")
            self._init_openai_client(api_key, base_url)
        else:
            self.logger.info("使用官方 Gemini API")
            self._init_gemini_client(api_key)

        self.logger.info(f"Gemini 分析器已初始化，使用模型: {model_name}")

    def _init_openai_client(self, api_key: str, base_url: str):
        try:
            from openai import OpenAI, AsyncOpenAI
        except ImportError:
            raise ImportError("使用中转服务需要安装 openai 库: pip install openai")

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.async_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.use_openai = True

    def _init_gemini_client(self, api_key: str):
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "使用官方 Gemini API 需要安装 google-generativeai 库: "
                "pip install google-generativeai"
            )

        self.genai = genai
        genai.configure(api_key=api_key)

        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config={
                "temperature": self.temperature,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": self.max_output_tokens,
            }
        )
        self.use_openai = False

    # ------------------------------------------------------------------
    # 阶段 1：分析单篇文献（不含分类）
    # ------------------------------------------------------------------

    def analyze_paper_from_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        """同步：直接从 PDF 文件分析文献"""
        try:
            self.logger.info(f"正在上传并分析 PDF: {pdf_path.name}")
            if self.use_openai:
                result_text = self._call_openai_with_pdf(pdf_path)
            else:
                result_text = self._call_gemini_with_pdf(pdf_path)
            self.logger.info("API 调用成功，正在解析结果...")
            return self._parse_response(result_text)
        except Exception as e:
            safe_msg = self._sanitize_exception_message(str(e))
            self.logger.error(f"PDF 分析失败: {safe_msg}")
            raise RuntimeError(safe_msg) from None

    async def analyze_paper_async(self, pdf_path: Path) -> Dict[str, Any]:
        """异步：在 asyncio 事件循环中分析 PDF（供 asyncio.gather 使用）"""
        try:
            self.logger.info(f"[async] 正在分析 PDF: {pdf_path.name}")
            if self.use_openai:
                result_text = await self._call_openai_with_pdf_async(pdf_path)
            else:
                # 官方 SDK 无原生 async，用 run_in_executor 包装
                loop = asyncio.get_event_loop()
                result_text = await loop.run_in_executor(
                    None, self._call_gemini_with_pdf, pdf_path
                )
            self.logger.info(f"[async] 解析完成: {pdf_path.name}")
            return self._parse_response(result_text)
        except Exception as e:
            safe_msg = self._sanitize_exception_message(str(e))
            self.logger.error(f"[async] PDF 分析失败 {pdf_path.name}: {safe_msg}")
            raise RuntimeError(safe_msg) from None

    def _sanitize_exception_message(self, message: str) -> str:
        """避免将 API key 直接写入日志。"""
        safe = message
        if self._api_key:
            masked = f"{self._api_key[:4]}***{self._api_key[-4:]}" if len(self._api_key) > 8 else "***"
            safe = safe.replace(self._api_key, masked)

        # mask query-string style keys, e.g. ...?key=xxxxx
        safe = re.sub(r"([?&]key=)[^&\\s\"']+", r"\\1***", safe)
        return safe

    def _call_openai_with_pdf(self, pdf_path: Path) -> str:
        with open(pdf_path, 'rb') as f:
            pdf_data = base64.b64encode(f.read()).decode('utf-8')
        prompt = self._create_analysis_prompt()
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:application/pdf;base64,{pdf_data}"
                    }}
                ]
            }],
            temperature=self.temperature,
            max_tokens=self.max_output_tokens
        )
        return response.choices[0].message.content

    async def _call_openai_with_pdf_async(self, pdf_path: Path) -> str:
        with open(pdf_path, 'rb') as f:
            pdf_data = base64.b64encode(f.read()).decode('utf-8')
        prompt = self._create_analysis_prompt()
        response = await self.async_client.chat.completions.create(
            model=self.model_name,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:application/pdf;base64,{pdf_data}"
                    }}
                ]
            }],
            temperature=self.temperature,
            max_tokens=self.max_output_tokens
        )
        return response.choices[0].message.content

    def _call_gemini_with_pdf(self, pdf_path: Path) -> str:
        self.logger.info("正在上传 PDF 到 Gemini...")
        pdf_file = self.genai.upload_file(str(pdf_path))
        self.logger.info(f"PDF 上传成功，文件 URI: {pdf_file.uri}")
        prompt = self._create_analysis_prompt()
        response = self.model.generate_content([prompt, pdf_file])
        return response.text

    def _create_analysis_prompt(self) -> str:
        """根据 active_config 创建分析提示词（analyze 阶段不注入分类字段）"""
        cfg = active_config.get()
        preamble = cfg.prompt_preamble
        json_schema = cfg.json_schema_template.replace("{{CLASSIFICATION_FIELDS}}", "")
        json_schema = self._strip_figures_from_schema(json_schema)

        # 注入自定义字段
        if cfg.custom_areas:
            extra_parts = []
            for key in cfg.custom_areas:
                extra_parts.append(f'\n    "{key}": "{cfg.custom_areas[key]}（自由文本）"')
            extra_fields = ",".join(extra_parts)
            json_schema = json_schema.rstrip()
            if json_schema.endswith('}'):
                json_schema = json_schema[:-1] + "," + extra_fields + "\n}"

        custom_note = ""
        if cfg.custom_areas:
            keys_str = ", ".join([f'"{k}"' for k in cfg.custom_areas])
            custom_note = (
                f"\n请务必为以下自定义字段逐一给出内容（若无法从文献获取，请填 \"N/A\"）：{keys_str}\n"
            )

        return (
            f"{preamble}\n\n"
            f"请按照以下结构提取信息，并以 JSON 格式返回（只返回 JSON，不要有其他文字）：\n\n"
            f"{json_schema}\n"
            f"{custom_note}"
            f"请用中文回答，返回 JSON 格式的分析结果。"
        )

    @staticmethod
    def _strip_figures_from_schema(schema: str) -> str:
        """移除历史模板中的 figures 字段，避免触发图片解析。"""
        if not schema:
            return schema
        lines = [line for line in schema.splitlines() if '"figures"' not in line]
        cleaned = "\n".join(lines)
        # 清理对象/数组结束前的尾逗号。
        cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
        return cleaned

    # ------------------------------------------------------------------
    # 通用文本调用（供 CategorySuggester 使用）
    # ------------------------------------------------------------------

    def call_with_text_prompt(self, prompt: str) -> str:
        """发送纯文本 prompt 并返回原始响应文本"""
        if self.use_openai:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_output_tokens
            )
            return response.choices[0].message.content
        else:
            response = self.model.generate_content(prompt)
            return response.text

    # ------------------------------------------------------------------
    # 阶段 3：批量分类（一次 API 调用）
    # ------------------------------------------------------------------

    def classify_papers_batch(
        self,
        papers: list[dict],
        categories: dict[int, str]
    ) -> list[dict]:
        """
        批量分类：一次 API 调用对所有文献分类。

        Args:
            papers: staging JSON 列表，每项含 "source_pdf" 和 "analysis" 字段
            categories: {int: str} 分类映射

        Returns:
            list[dict]: 每项含 "source_pdf", "category"(int|None), "category_reasoning"(str)
        """
        categories_text = "\n".join(
            f"{k}. {v}" for k, v in sorted(categories.items())
        )

        paper_list = []
        for i, p in enumerate(papers):
            analysis = p.get("analysis", {})
            paper_list.append({
                "id": i,
                "source_pdf": p.get("source_pdf", ""),
                "title": analysis.get("title", "N/A"),
                "research_question": analysis.get("research_question", "N/A"),
                "main_conclusion": analysis.get("main_conclusion", "N/A"),
            })

        prompt = (
            "你是一个专业的科研文献分类专家。\n"
            "根据以下分类标准，对每篇文献进行分类：\n\n"
            f"分类标准：\n{categories_text}\n\n"
            "文献列表（JSON 格式）：\n"
            f"{json.dumps(paper_list, ensure_ascii=False, indent=2)}\n\n"
            "请返回 JSON 数组，格式如下（只返回 JSON，不要有其他文字）：\n"
            "[\n"
            '  {"id": 0, "source_pdf": "文件名.pdf", "category": 1, "category_reasoning": "分类理由"},\n'
            "  ...\n"
            "]\n\n"
            "注意：category 必须是整数，且必须是上方分类标准中的编号之一。"
        )

        self.logger.info(f"批量分类 {len(papers)} 篇文献...")
        result_text = self.call_with_text_prompt(prompt)
        return self._parse_classification_response(result_text, papers, categories)

    def _parse_classification_response(
        self,
        response_text: str,
        original_papers: list[dict],
        categories: dict[int, str]
    ) -> list[dict]:
        try:
            parsed = self._extract_json_payload_with_repair(
                response_text,
                expected_top_level="array",
            )
        except ValueError as e:
            self.logger.error(f"批量分类响应解析失败: {e}")
            self.logger.error(f"响应内容: {response_text[:500]}")
            raise ValueError("无法解析批量分类响应为 JSON")

        if isinstance(parsed, dict):
            if isinstance(parsed.get("items"), list):
                items = parsed["items"]
            elif isinstance(parsed.get("results"), list):
                items = parsed["results"]
            else:
                raise ValueError("批量分类 JSON 不是数组格式")
        elif isinstance(parsed, list):
            items = parsed
        else:
            raise ValueError("批量分类 JSON 类型无效")

        id_to_pdf = {i: p.get("source_pdf", "") for i, p in enumerate(original_papers)}

        results = []
        for item in items:
            idx = item.get("id", -1)
            source_pdf = id_to_pdf.get(idx, item.get("source_pdf", "unknown.pdf"))
            try:
                category = int(item.get("category"))
            except (TypeError, ValueError):
                category = None

            if category not in categories:
                self.logger.warning(
                    f"文献 '{source_pdf}' 返回无效分类 {item.get('category')}，将归入未分类"
                )
                category = None

            results.append({
                "source_pdf": source_pdf,
                "category": category,
                "category_reasoning": item.get("category_reasoning", ""),
            })

        return results

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """解析单篇文献分析响应"""
        try:
            parsed = self._extract_json_payload_with_repair(
                response_text,
                expected_top_level="object",
            )
        except ValueError as e:
            self.logger.error(f"JSON 解析失败: {e}")
            self.logger.error(f"响应内容: {response_text[:500]}")
            raise ValueError("无法解析 Gemini 响应为 JSON 格式")

        if not isinstance(parsed, dict):
            raise ValueError("Gemini 响应 JSON 不是对象格式")

        result = parsed
        if "title" not in result:
            raise ValueError("缺少必要字段: title")

        return result

    def _extract_json_payload_with_repair(
        self,
        raw_text: str,
        *,
        expected_top_level: str,
    ) -> Any:
        """先本地解析，失败后再让模型做一次 JSON 修复。"""
        try:
            return self._extract_json_payload(raw_text)
        except ValueError as first_error:
            self.logger.warning(f"首次 JSON 解析失败，尝试修复: {first_error}")

        repaired = self._repair_json_with_model(raw_text, expected_top_level=expected_top_level)
        if not repaired:
            raise ValueError("无法解析 JSON，且修复调用失败")

        try:
            return self._extract_json_payload(repaired)
        except ValueError as second_error:
            raise ValueError(f"修复后仍无法解析 JSON: {second_error}") from second_error

    def _repair_json_with_model(self, raw_text: str, *, expected_top_level: str) -> str:
        """将近似 JSON 文本交给模型修复为合法 JSON。"""
        raw = (raw_text or "").strip()
        if not raw:
            return ""

        expected_note = "顶层必须是 JSON 对象。" if expected_top_level == "object" else "顶层必须是 JSON 数组。"
        prompt = (
            "你是一个 JSON 修复器。下面是一段本应为 JSON 的文本，但可能包含格式错误。\n"
            "请把它修复成合法 JSON。\n"
            "- 只输出 JSON，本身不要使用 ```json 代码块，不要解释。\n"
            "- 尽量保留原有字段和值。\n"
            "- 如果文本被截断导致字段缺失，可补充为 \"N/A\"、[] 或 {}。\n"
            f"- {expected_note}\n\n"
            "原始文本如下：\n"
            f"{raw[:16000]}"
        )

        try:
            repaired = self.call_with_text_prompt(prompt)
            return repaired or ""
        except Exception as exc:
            self.logger.warning(f"JSON 修复调用失败: {exc}")
            return ""

    def _extract_json_payload(self, raw_text: str) -> Any:
        """从模型输出中提取 JSON（兼容前后噪声文本）。"""
        text = self._normalize_json_text(self._strip_code_fence((raw_text or "").strip()))
        if not text:
            raise ValueError("响应为空")

        candidates: list[str] = [text]

        balanced = self._find_first_balanced_json(text)
        if balanced:
            candidates.append(balanced)

        first_obj, last_obj = text.find("{"), text.rfind("}")
        if first_obj >= 0 and last_obj > first_obj:
            candidates.append(text[first_obj : last_obj + 1])

        first_arr, last_arr = text.find("["), text.rfind("]")
        if first_arr >= 0 and last_arr > first_arr:
            candidates.append(text[first_arr : last_arr + 1])

        seen: set[str] = set()
        last_error: Optional[json.JSONDecodeError] = None
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as exc:
                last_error = exc
                continue

        if last_error is not None:
            raise ValueError(
                f"JSONDecodeError: {last_error.msg} (line {last_error.lineno}, col {last_error.colno})"
            ) from last_error

        raise ValueError("无法从响应中提取有效 JSON")

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    @staticmethod
    def _normalize_json_text(text: str) -> str:
        if not text:
            return ""
        replacements = {
            "\ufeff": "",
            "\u201c": "\"",
            "\u201d": "\"",
            "\u2018": "'",
            "\u2019": "'",
            "\u00a0": " ",
        }
        normalized = text
        for src, dst in replacements.items():
            normalized = normalized.replace(src, dst)

        # 去掉非法控制字符（保留换行/回车/制表符）。
        cleaned_chars = []
        for ch in normalized:
            code = ord(ch)
            if code < 32 and ch not in ("\n", "\r", "\t"):
                continue
            cleaned_chars.append(ch)
        return "".join(cleaned_chars).strip()

    @staticmethod
    def _find_first_balanced_json(text: str) -> str:
        obj_start = text.find("{")
        arr_start = text.find("[")
        starts = [i for i in (obj_start, arr_start) if i >= 0]
        if not starts:
            return ""

        start = min(starts)
        stack: list[str] = []
        in_string = False
        escaped = False

        for idx in range(start, len(text)):
            ch = text[idx]

            if in_string:
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue

            if ch in "{[":
                stack.append(ch)
                continue

            if ch in "}]":
                if not stack:
                    return ""
                opener = stack.pop()
                if (opener == "{" and ch != "}") or (opener == "[" and ch != "]"):
                    return ""
                if not stack:
                    return text[start : idx + 1]

        return ""
