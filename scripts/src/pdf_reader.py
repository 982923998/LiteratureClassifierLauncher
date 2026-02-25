"""
PDF 阅读工具
"""
import pypdf
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PDFReader:
    """PDF 文件读取器"""

    def __init__(self):
        self.logger = logger

    def read_pdf(self, pdf_path: Path) -> str:
        """
        读取 PDF 文件内容

        Args:
            pdf_path: PDF 文件路径

        Returns:
            str: PDF 文本内容
        """
        try:
            self.logger.info(f"正在读取 PDF: {pdf_path.name}")

            with open(pdf_path, 'rb') as file:
                pdf_reader = pypdf.PdfReader(file)
                total_pages = len(pdf_reader.pages)

                self.logger.info(f"PDF 总页数: {total_pages}")

                # 提取所有页面的文本
                text_content = []
                for page_num in range(total_pages):
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()
                    if text:
                        text_content.append(text)

                full_text = "\n\n".join(text_content)

                self.logger.info(f"成功提取文本，总字符数: {len(full_text)}")

                return full_text

        except Exception as e:
            self.logger.error(f"读取 PDF 失败: {str(e)}")
            raise

    def get_pdf_summary(self, text: str, max_length: int = 1000) -> str:
        """
        获取 PDF 文本摘要（用于日志）

        Args:
            text: 完整文本
            max_length: 最大长度

        Returns:
            str: 摘要文本
        """
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."
