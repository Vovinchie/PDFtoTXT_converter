# src/ocr_converter/gui/app.py
import customtkinter as ctk
from typing import Optional
from .convert_frame import ConvertFrame
from .search_frame import SearchFrame

class OCRApp(ctk.CTk):
    """
    Главное приложение OCR Converter.
    Содержит переключение между режимами Конвертации и Поиска.
    """
    
    def __init__(self):
        super().__init__()
        
        # Настройки окна
        self.title("OCR Converter — Поиск и Конвертация PDF")
        self.geometry("900x700")
        self.minsize(800, 600)
        
        # Настройка темы
        ctk.set_appearance_mode("System")  # System, Dark, Light
        ctk.set_default_color_theme("blue")  # blue, dark-blue, green
        
        # Сетка
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # Заголовок
        self.grid_rowconfigure(1, weight=1)  # Контент
        
        # Заголовок
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        
        self.title_label = ctk.CTkLabel(
            self.header_frame,
            text="📄 OCR Converter",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        self.title_label.pack(side="left")
        
        self.subtitle_label = ctk.CTkLabel(
            self.header_frame,
            text="Конвертация сканов в текст + Поиск по документам",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.subtitle_label.pack(side="left", padx=20, pady=10)
        
        # Переключатель режимов (Segmented Button)
        self.mode_switch = ctk.CTkSegmentedButton(
            self.header_frame,
            values=["convert", "search"],
            command=self._switch_mode
        )
        self.mode_switch.pack(side="right")
        self.mode_switch.set("convert")
        
        # Контейнер для вкладок
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)
        
        # Инициализация вкладок
        self.convert_frame: Optional[ConvertFrame] = None
        self.search_frame: Optional[SearchFrame] = None
        
        # Показываем начальную вкладку
        self._switch_mode("convert")
    
    def _switch_mode(self, mode: str) -> None:
        """Переключает между режимами Конвертации и Поиска."""
        # Очищаем текущий контент
        if self.convert_frame:
            self.convert_frame.grid_forget()
        if self.search_frame:
            self.search_frame.grid_forget()
        
        # Создаём/показываем нужную вкладку
        if mode == "convert":
            if not self.convert_frame:
                self.convert_frame = ConvertFrame(self.content_frame)
            self.convert_frame.grid(row=0, column=0, sticky="nsew")
        elif mode == "search":
            if not self.search_frame:
                self.search_frame = SearchFrame(self.content_frame)
            self.search_frame.grid(row=0, column=0, sticky="nsew")
    
    def get_config(self):
        """Возвращает общую конфигурацию для обоих режимов."""
        from ..config import OCRConfig
        return OCRConfig(
            languages="rus",
            dpi=300,
            tesseract_path=None
        )

if __name__ == "__main__":
    app = OCRApp()
    app.mainloop()