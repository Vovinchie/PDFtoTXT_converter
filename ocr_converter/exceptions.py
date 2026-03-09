class OCRError(Exception):
    """Базовое исключение для ошибок OCR."""
    pass

class PDFProcessingError(OCRError):
    """Ошибка при обработке PDF файла."""
    pass

class TesseractNotFoundError(OCRError):
    """Движок Tesseract не найден или не настроен."""
    pass