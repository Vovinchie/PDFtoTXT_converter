# src/ocr_converter/gui/search_frame.py
import customtkinter as ctk
from tkinter import filedialog, messagebox
from pathlib import Path
import threading
import queue

from ..services.search_service import SearchService, SearchResult

class SearchFrame(ctk.CTkFrame):
    """Вкладка поиска по оцифрованным документам."""
    
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        
        self.selected_file: Path = None
        self.status_queue = queue.Queue()
        
        # === Выбор файла ===
        self.file_frame = ctk.CTkFrame(self)
        self.file_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.file_frame.grid_columnconfigure(1, weight=1)
        
        self.btn_select = ctk.CTkButton(
            self.file_frame,
            text="📁 Выбрать файл",
            command=self._select_file,
            width=150
        )
        self.btn_select.grid(row=0, column=0, padx=10, pady=10)
        
        self.lbl_file = ctk.CTkLabel(
            self.file_frame,
            text="Файл не выбран",
            text_color="gray",
            anchor="w"
        )
        self.lbl_file.grid(row=0, column=1, padx=10, pady=10, sticky="w")
        
        # === Тип поиска ===
        self.type_frame = ctk.CTkFrame(self)
        self.type_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        
        self.search_type = ctk.StringVar(value="word")
        
        self.radio_word = ctk.CTkRadioButton(
            self.type_frame,
            text="Точное слово",
            variable=self.search_type,
            value="word"
        )
        self.radio_word.grid(row=0, column=0, padx=20, pady=10)
        
        self.radio_phrase = ctk.CTkRadioButton(
            self.type_frame,
            text="Словосочетание (фраза)",
            variable=self.search_type,
            value="phrase"
        )
        self.radio_phrase.grid(row=0, column=1, padx=20, pady=10)
        
        # === Поле ввода ===
        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.input_frame.grid_columnconfigure(0, weight=1)
        
        self.entry_query = ctk.CTkEntry(
            self.input_frame,
            placeholder_text="Введите слово или фразу для поиска...",
            height=40
        )
        self.entry_query.grid(row=0, column=0, padx=20, pady=10, sticky="ew")
        
        self.btn_search = ctk.CTkButton(
            self.input_frame,
            text="🔍 Поиск",
            command=self._start_search,
            height=40,
            width=150
        )
        self.btn_search.grid(row=0, column=1, padx=20, pady=10)
        
        # === Результаты ===
        self.result_frame = ctk.CTkFrame(self)
        self.result_frame.grid(row=3, column=0, sticky="nsew")
        self.result_frame.grid_columnconfigure(0, weight=1)
        self.result_frame.grid_rowconfigure(1, weight=1)
        
        self.lbl_result_title = ctk.CTkLabel(
            self.result_frame,
            text="Результаты поиска",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.lbl_result_title.grid(row=0, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.result_text = ctk.CTkTextbox(
            self.result_frame,
            state="disabled"
        )
        self.result_text.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
    
    def _select_file(self) -> None:
        """Выбор файла для поиска."""
        file = filedialog.askopenfilename(
            title="Выберите TXT файл для поиска",
            filetypes=[("TXT файлы", "*.txt"), ("PDF файлы", "*.pdf")]
        )
        
        if file:
            self.selected_file = Path(file)
            self.lbl_file.configure(text=self.selected_file.name, text_color="green")
    
    def _start_search(self) -> None:
        """Запускает поиск в отдельном потоке."""
        if not self.selected_file:
            messagebox.showwarning("Предупреждение", "Выберите файл для поиска")
            return
        
        query = self.entry_query.get().strip()
        if not query:
            messagebox.showwarning("Предупреждение", "Введите слово или фразу для поиска")
            return
        
        self.btn_search.configure(state="disabled", text="⏳ Поиск...")
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", "Выполняется поиск...\n")
        self.result_text.configure(state="disabled")
        
        thread = threading.Thread(target=self._run_search, args=(query,), daemon=True)
        thread.start()
    
    def _run_search(self, query: str) -> None:
        """Логика поиска (в потоке)."""
        try:
            service = SearchService(case_sensitive=False)
            result = service.search(self.selected_file, query)
            self.status_queue.put(("result", result))
        except Exception as e:
            self.status_queue.put(("error", str(e)))
        
        self.after(100, self._check_status)
    
    def _check_status(self) -> None:
        """Проверяет результаты поиска."""
        try:
            msg_type, msg_data = self.status_queue.get_nowait()
            
            if msg_type == "result":
                self._display_results(msg_data)
            elif msg_type == "error":
                self.result_text.configure(state="normal")
                self.result_text.delete("1.0", "end")
                self.result_text.insert("1.0", f"❌ Ошибка поиска:\n{msg_data}")
                self.result_text.configure(state="disabled")
            
            self.btn_search.configure(state="normal", text="🔍 Поиск")
            
        except queue.Empty:
            self.after(100, self._check_status)
    
    def _display_results(self, result: SearchResult) -> None:
        """Отображает результаты поиска в текстовом поле."""
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        
        if result.total_matches == 0:
            self.result_text.insert("1.0", "❌ Ничего не найдено\n")
        else:
            header = (
                f"✅ Найдено: {result.total_matches} вхождений\n"
                f"📌 Страницы: {', '.join(map(str, result.pages_with_matches))}\n"
                f"{'='*60}\n\n"
            )
            self.result_text.insert("1.0", header)
            
            for i, match in enumerate(result.matches[:20], 1):  # Показываем первые 20
                line = (
                    f"[{i}] Страница {match.page_number}\n"
                    f"    ...{match.line_content}...\n\n"
                )
                self.result_text.insert("end", line)
            
            if len(result.matches) > 20:
                self.result_text.insert("end", f"\n... и ещё {len(result.matches) - 20} совпадений\n")
        
        self.result_text.configure(state="disabled")