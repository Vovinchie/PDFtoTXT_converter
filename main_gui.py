# main_gui.py
import sys
import os
from pathlib import Path
import logging
import multiprocessing

# === КРИТИЧЕСКИ ВАЖНО: Должно быть ДО всего остального ===
if __name__ == '__main__':
    multiprocessing.freeze_support()

# === Настройка путей для PyInstaller ===
def get_app_path():
    """Возвращает базовый путь приложения"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent

APP_PATH = get_app_path()

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
docs_path = Path.home() / "Documents" / "OCR_Converter"
docs_path.mkdir(exist_ok=True)

log_path = docs_path / "ocr_app.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8", mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# === НАСТРОЙКА CUSTOMTKINTER ===
try:
    import customtkinter as ctk
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    logger.info("CustomTkinter initialized successfully")
except Exception as e:
    logger.critical(f"CustomTkinter init failed: {e}", exc_info=True)
    raise

# === ИМПОРТ ПРИЛОЖЕНИЯ ===
try:
    from ocr_converter.gui.app import OCRApp
    logger.info("OCRApp imported successfully")
except Exception as e:
    logger.critical(f"Failed to import OCRApp: {e}", exc_info=True)
    raise

# === ТОЧКА ВХОДА ===
if __name__ == "__main__":
    try:
        # ← Проверка что это главный процесс (не воркер)
        if multiprocessing.current_process().name != 'MainProcess':
            # Это воркер multiprocessing — не запускаем GUI
            sys.exit(0)
        
        logger.info("=" * 60)
        logger.info("OCR Converter starting...")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"App path: {APP_PATH}")
        logger.info(f"Frozen: {getattr(sys, 'frozen', False)}")
        logger.info(f"sys.executable: {sys.executable}")
        logger.info(f"Process ID: {os.getpid()}")
        logger.info(f"Process name: {multiprocessing.current_process().name}")
        
        # Проверка доступности модулей
        import fitz
        import pytesseract
        from PIL import Image
        logger.info("All required modules imported successfully")
        
        # Создание приложения
        logger.info("Creating OCRApp instance...")
        app = OCRApp()
        logger.info("OCRApp instance created successfully")
        
        # Запуск главного цикла
        logger.info("Starting mainloop...")
        app.mainloop()
        logger.info("Application closed normally")
        
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)