# src/ocr_converter/config.py
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass(frozen=True)
class OCRConfig:
    # ... (предыдущие поля)
    languages: str = "rus"
    dpi: int = 300
    tesseract_path: Optional[Path] = None
    psm: int = 3
    oem: int = 3
    
    # Формат маркера страницы. 
    # Используем символы, которые редко встречаются в тексте, для надёжного парсинга.
    # Формат: @@PAGE:123@@
    page_marker_template: str = "\n@@PAGE:{page_num}@@\n"

    def get_tesseract_config(self) -> str:
        return f"--oem {self.oem} --psm {self.psm}"

    def get_page_marker(self, page_num: int) -> str:
        return self.page_marker_template.format(page_num=page_num)