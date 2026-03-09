# src/ocr_converter/services/ocr_engine.py
import logging
from pathlib import Path
from typing import Optional
from PIL import Image

# Проверка наличия библиотеки
try:
    import pytesseract
except ImportError:
    raise ImportError("pytesseract is not installed. Please install it via pip.")

from ..config import OCRConfig
from ..exceptions import TesseractNotFoundError, OCRError

logger = logging.getLogger(__name__)

class OCREngine:
    """
    Инкапсулирует логику работы с Tesseract OCR.
    Позволяет легко заменить движок в будущем (например, на EasyOCR),
    не меняя код верхнего уровня.
    """
    
    def __init__(self, config: OCRConfig):
        self.config = config
        self._init_tesseract()

    def _init_tesseract(self) -> None:
        """Настраивает путь к бинарнику Tesseract."""
        if self.config.tesseract_path:
            if not self.config.tesseract_path.exists():
                raise TesseractNotFoundError(
                    f"Tesseract not found at {self.config.tesseract_path}"
                )
            pytesseract.pytesseract.tesseract_cmd = str(self.config.tesseract_path)
            logger.info(f"Tesseract path set to: {self.config.tesseract_path}")
        else:
            logger.info("Using system PATH for Tesseract")

    def recognize(self, image: Image.Image) -> str:
        """
        Выполняет распознавание текста на изображении.
        
        Args:
            image: Объект PIL.Image
            
        Returns:
            Распознанный текст
            
        Raises:
            OCRError: Если процесс распознавания не удался.
        """
        try:
            text = pytesseract.image_to_string(
                image,
                lang=self.config.languages,
                config=self.config.get_tesseract_config()
            )
            return text
        except Exception as e:
            logger.error(f"OCR recognition failed: {e}")
            raise OCRError(f"Failed to recognize text: {e}")