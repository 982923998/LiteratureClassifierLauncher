#!/usr/bin/env python3
"""
文献分类主程序
三阶段工作流：analyze → suggest → classify
"""
import asyncio
import json
import sys
import shutil
import logging
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_loader import load_config, list_projects
from config import active_config
from src.gemini_analyzer import GeminiAnalyzer
from src.markdown_generator import MarkdownGenerator
from src.category_suggester import CategorySuggester


def setup_logging(log_dir: Path) -> logging.Logger:
    log_file = log_dir / f"classifier_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


# -----------------------------------------------------------------------
# 公共工具
# -----------------------------------------------------------------------

def get_pending_papers(logger: logging.Logger) -> list[Path]:
    cfg = active_config.get()
    pdf_files = sorted(cfg.pdf_input_dir.glob("*.pdf"))
    logger.info(f"找到 {len(pdf_files)} 个待处理 PDF")
    return pdf_files


def load_staging_jsons() -> list[dict]:
    """读取 staging 目录下所有 JSON（排除 category_suggestions.json）"""
    cfg = active_config.get()
    jsons = []
    for p in sorted(cfg.staging_dir.glob("*.json")):
        if p.name == CategorySuggester.SUGGESTIONS_FILENAME:
            continue
        with open(p, "r", encoding="utf-8") as f:
            jsons.append(json.load(f))
    return jsons


def save_staging_json(data: dict) -> None:
    cfg = active_config.get()
    filename = data["source_pdf"].replace(".pdf", ".json")
    path = cfg.staging_dir / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def staging_json_exists(pdf_name: str) -> bool:
    cfg = active_config.get()
    return (cfg.staging_dir / pdf_name.replace(".pdf", ".json")).exists()


def save_markdown(md_content: str, dir_name: str, md_filename: str) -> Path:
    cfg = active_config.get()
    dest_dir = cfg.md_output_root / dir_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    md_path = dest_dir / md_filename
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    return md_path


def move_pdf_to_processed(pdf_path: Path, logger: logging.Logger) -> Path:
    cfg = active_config.get()
    dest = cfg.pdf_processed_dir / pdf_path.name
    if dest.exists():
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        dest = cfg.pdf_processed_dir / f"{pdf_path.stem}_{timestamp}.pdf"
    shutil.move(str(pdf_path), str(dest))
    logger.info(f"✓ PDF 已归档: {dest.name}")
    return dest


# -----------------------------------------------------------------------
# 阶段 1：analyze
# -----------------------------------------------------------------------

async def _analyze_one(
    pdf_path: Path,
    analyzer: GeminiAnalyzer,
    md_generator: MarkdownGenerator,
    semaphore: asyncio.Semaphore,
    logger: logging.Logger,
) -> bool:
    """异步处理单篇文献"""
    async with semaphore:
        try:
            logger.info(f"[analyze] 开始: {pdf_path.name}")

            # 跳过已处理
            if staging_json_exists(pdf_path.name):
                logger.info(f"[analyze] 已存在 staging JSON，跳过: {pdf_path.name}")
                return True

            # 调用 Gemini 分析
            analysis = await analyzer.analyze_paper_async(pdf_path)

            cfg = active_config.get()
            md_filename = md_generator.sanitize_filename(
                analysis.get("title", pdf_path.stem)
            )

            # 移动 PDF，获取归档路径
            processed_path = move_pdf_to_processed(pdf_path, logger)

            # 注入元数据供 Markdown 模板使用
            analysis["source_pdf"] = pdf_path.name

            # 保存 staging JSON
            staging_data = {
                "source_pdf": pdf_path.name,
                "processed_pdf_path": str(processed_path),
                "processed_at": datetime.now().isoformat(),
                "analysis": analysis,
                "md_filename": md_filename,
            }
            save_staging_json(staging_data)

            # 生成 Markdown → 0.未分类/
            md_content = md_generator.generate_markdown(analysis)
            md_path = save_markdown(md_content, cfg.unclassified_dir_name, md_filename)
            logger.info(f"✓ Markdown 已保存: {md_path.name}")

            logger.info(f"✓ 完成: {pdf_path.name}")
            return True

        except Exception as e:
            logger.error(f"✗ 处理失败 {pdf_path.name}: {e}", exc_info=True)
            return False


async def run_analyze(args, logger: logging.Logger):
    cfg = active_config.get()
    analyzer = GeminiAnalyzer(
        model_name=cfg.gemini_model,
        temperature=cfg.gemini_temperature
    )
    md_generator = MarkdownGenerator()

    pdf_files = get_pending_papers(logger)
    if not pdf_files:
        logger.info("没有待处理的 PDF 文件")
        return

    if args.single:
        target = cfg.pdf_input_dir / args.single
        if not target.exists():
            logger.error(f"文件不存在: {target}")
            sys.exit(1)
        pdf_files = [target]
    elif args.limit:
        pdf_files = pdf_files[:args.limit]
        logger.info(f"限制处理数量: {args.limit}")

    semaphore = asyncio.Semaphore(args.workers)
    tasks = [
        _analyze_one(p, analyzer, md_generator, semaphore, logger)
        for p in pdf_files
    ]

    logger.info(f"开始并发分析（最多 {args.workers} 个并发）...")
    results = await asyncio.gather(*tasks, return_exceptions=False)

    success = sum(1 for r in results if r)
    failed = len(results) - success
    logger.info(f"\n分析完成：成功 {success} 篇，失败 {failed} 篇")
    logger.info(f"结果已保存至: {cfg.staging_dir}")
    logger.info(f"Markdown 已保存至: {cfg.md_output_root / cfg.unclassified_dir_name}")


# -----------------------------------------------------------------------
# 阶段 2：suggest
# -----------------------------------------------------------------------

def run_suggest(args, logger: logging.Logger):
    cfg = active_config.get()
    staging_jsons = load_staging_jsons()

    if not staging_jsons:
        print(f"错误：staging 目录为空 ({cfg.staging_dir})")
        print("请先运行 --mode analyze 分析文献。")
        sys.exit(1)

    analyzer = GeminiAnalyzer(
        model_name=cfg.gemini_model,
        temperature=cfg.gemini_temperature
    )
    suggester = CategorySuggester(analyzer)
    suggester.suggest()


# -----------------------------------------------------------------------
# 阶段 3：classify
# -----------------------------------------------------------------------

def run_classify(args, logger: logging.Logger):
    cfg = active_config.get()

    if not cfg.categories:
        print("错误：projects.yaml 中 categories 为空。")
        print("请先运行 --mode suggest，根据建议在 projects.yaml 中填写分类，然后重试。")
        sys.exit(1)

    staging_jsons = load_staging_jsons()
    if not staging_jsons:
        print(f"错误：staging 目录为空 ({cfg.staging_dir})")
        print("请先运行 --mode analyze 分析文献。")
        sys.exit(1)

    logger.info(f"开始批量分类 {len(staging_jsons)} 篇文献...")
    analyzer = GeminiAnalyzer(
        model_name=cfg.gemini_model,
        temperature=cfg.gemini_temperature
    )
    md_generator = MarkdownGenerator()

    # 一次 API 调用批量分类
    classifications = analyzer.classify_papers_batch(staging_jsons, cfg.categories)

    # 移动文件
    moved = 0
    skipped = 0
    for item in classifications:
        source_pdf = item["source_pdf"]
        category = item.get("category")

        if category is not None and category in cfg.categories:
            category_name = cfg.categories[category]
        else:
            category_name = cfg.unclassified_dir_name

        # 找对应的 staging JSON 以获取 md_filename
        staging = next(
            (s for s in staging_jsons if s.get("source_pdf") == source_pdf),
            None
        )
        if staging is None:
            logger.warning(f"未找到 staging 记录，跳过: {source_pdf}")
            skipped += 1
            continue

        md_filename = staging.get("md_filename", "")
        if not md_filename:
            logger.warning(f"staging 缺少 md_filename，跳过: {source_pdf}")
            skipped += 1
            continue

        success = md_generator.move_to_category(md_filename, category_name)
        if success:
            moved += 1
            # 更新 staging JSON，记录最终分类
            staging["final_category"] = category
            staging["final_category_name"] = category_name
            staging["category_reasoning"] = item.get("category_reasoning", "")
            save_staging_json(staging)
        else:
            skipped += 1

    logger.info(f"\n分类完成：移动 {moved} 篇，跳过 {skipped} 篇")
    logger.info("分类统计：")
    cat_counts: dict[str, int] = {}
    for item in classifications:
        cat = item.get("category")
        name = cfg.categories.get(cat, cfg.unclassified_dir_name) if cat else cfg.unclassified_dir_name
        cat_counts[name] = cat_counts.get(name, 0) + 1
    for name, count in sorted(cat_counts.items()):
        logger.info(f"  {name}: {count} 篇")


# -----------------------------------------------------------------------
# 入口
# -----------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='文献分类系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "工作流：\n"
            "  1. analyze  分析 PDF，提取信息，保存至 staging/\n"
            "  2. suggest  读取 staging/，建议分类方案\n"
            "  3. classify 根据 projects.yaml 中的 categories，将文献移动到对应目录\n"
        )
    )
    parser.add_argument(
        '--config',
        required=True,
        metavar='PROJECT',
        help=f'项目名称，可选：{", ".join(list_projects())}'
    )
    parser.add_argument(
        '--mode',
        required=True,
        choices=['analyze', 'suggest', 'classify'],
        help='运行模式'
    )
    parser.add_argument('--limit', type=int, default=None, help='限制处理数量（仅 analyze）')
    parser.add_argument('--single', type=str, default=None, help='处理单个 PDF 文件名（仅 analyze）')
    parser.add_argument('--workers', type=int, default=3, help='并发处理数（仅 analyze，默认 3）')

    args = parser.parse_args()

    # 加载配置
    try:
        config = load_config(args.config)
    except KeyError as e:
        print(f"错误：{e}")
        sys.exit(1)

    active_config.set(config)
    logger = setup_logging(config.log_dir)

    logger.info(f"项目: {config.name}")
    logger.info(f"模式: {args.mode}")

    if args.mode == 'analyze':
        asyncio.run(run_analyze(args, logger))
    elif args.mode == 'suggest':
        run_suggest(args, logger)
    elif args.mode == 'classify':
        run_classify(args, logger)


if __name__ == "__main__":
    main()
