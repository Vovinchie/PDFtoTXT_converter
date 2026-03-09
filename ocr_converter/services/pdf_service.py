# src/ocr_converter/services/pdf_service.py
import logging
from pathlib import Path
from typing import Generator, Tuple

import fitz  # PyMuPDF
from PIL import Image
import io

from ..config import OCRConfig
from .ocr_engine import OCREngine
from ..exceptions import PDFProcessingError

logger = logging.getLogger(__name__)

# src/ocr_converter/services/pdf_service.py
# ... (существующий код)

class PDFService:
    def __init__(self, ocr_engine: OCREngine, config: OCRConfig):
        self.ocr_engine = ocr_engine
        self.config = config

    def process_single_page(self, input_path: Path, page_num: int, output_path: Path) -> dict:
        """
        Обрабатывает одну страницу PDF и добавляет текст в файл.
        
        Args:
            input_path: Путь к PDF
            page_num: Номер страницы (1-based)
            output_path: Путь к выходному TXT (режим append)
            
        Returns:
            dict с информацией о странице
        """
        import fitz
        from PIL import Image
        import io
        
        doc = fitz.open(input_path)
        
        try:
            page = doc[page_num - 1]  # 0-based индекс
            
            # Рендеринг
            image = self._render_page_to_image(page)
            
            # OCR
            text = self.ocr_engine.recognize(image)
            
            # Запись в файл (append)
            with open(output_path, "a", encoding="utf-8-sig") as f:
                marker = self.config.get_page_marker(page_num)
                f.write(marker)
                f.write(text)
                f.write("\n")
            
            del image
            
            return {
                "page_num": page_num,
                "success": True
            }
            
        finally:
            doc.close()

    def process_file(self, input_path: Path, output_path: Path) -> None:
        """
        Обрабатывает весь PDF файл (для обратной совместимости).
        """
        import fitz
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        logger.info(f"Starting processing: {input_path.name}")
        
        try:
            doc = fitz.open(input_path)
        except Exception as e:
            raise PDFProcessingError(f"Failed to open PDF: {e}")

        try:
            with open(output_path, "w", encoding="utf-8-sig") as txt_file:
                total_pages = len(doc)
                
                for page_num, page in enumerate(doc, start=1):
                    try:
                        logger.debug(f"Processing page {page_num}/{total_pages}")
                        
                        marker = self.config.get_page_marker(page_num)
                        txt_file.write(marker)
                        
                        image = self._render_page_to_image(page)
                        text = self.ocr_engine.recognize(image)
                        
                        txt_file.write(text)
                        txt_file.write("\n")
                        
                        del image
                        
                    except Exception as e:
                        logger.error(f"Error on page {page_num}: {e}")
                        txt_file.write(f"\n@@ERROR:PAGE:{page_num}@@\n")
                        continue
            
            logger.info(f"Successfully finished: {output_path.name}")
            
        finally:
            doc.close()

    def _render_page_to_image(self, page: fitz.Page) -> Image.Image:
        """Рендерит страницу PDF в изображение."""
        zoom = self.config.dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        image = Image.open(io.BytesIO(img_data))
        del pix
        return image