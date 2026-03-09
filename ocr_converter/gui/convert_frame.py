# src/ocr_converter/gui/convert_frame.py
import customtkinter as ctk
from tkinter import filedialog, messagebox
from pathlib import Path
from typing import List, Optional, Dict
import threading
from dataclasses import dataclass
import queue
import logging
import traceback
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
import sys
import os

from ..config import OCRConfig

# Настройка логирования
logger = logging.getLogger(__name__)

@dataclass
class QueueItem:
    path: Path
    status: str
    output_path: Optional[Path] = None
    total_pages: int = 0

@dataclass
class FileWidget:
    """Хранит ссылки на виджеты файла для обновления статуса."""
    frame: ctk.CTkFrame
    lbl_name: ctk.CTkLabel
    lbl_status: ctk.CTkLabel
    progress_bar: ctk.CTkProgressBar
    lbl_progress: ctk.CTkLabel
    queue_item: QueueItem

@dataclass
class ProcessTask:
    """Задача для обработки одного файла в отдельном процессе."""
    input_path: Path
    output_path: Path
    dpi: int
    languages: str
    tesseract_path: Optional[str]
    file_index: int

def _get_base_path():
    """Возвращает базовый путь для импортов (работает в .exe и .py)"""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    else:
        return Path(__file__).parent.parent.parent

def _process_single_file(task: ProcessTask, progress_queue: multiprocessing.Queue) -> dict:
    """
    Функция для обработки одного файла в отдельном процессе.
    ВСЕ импорты в начале функции - до любого использования переменных!
    """
    # ← ИМПОРТЫ В САМОМ НАЧАЛЕ (критично для PyInstaller)
    import sys as _sys
    from pathlib import Path as _Path
    import fitz as _fitz
    from PIL import Image as _Image
    import io as _io
    
    # Добавляем путь для импортов
    base_path = _get_base_path()
    if str(base_path) not in _sys.path:
        _sys.path.insert(0, str(base_path))
    
    try:
        # Теперь импортируем наши модули
        from ocr_converter.config import OCRConfig as _OCRConfig
        from ocr_converter.services.ocr_engine import OCREngine as _OCREngine
        from ocr_converter.services.pdf_service import PDFService as _PDFService
        
        config = _OCRConfig(
            languages=task.languages,
            dpi=task.dpi,
            tesseract_path=_Path(task.tesseract_path) if task.tesseract_path else None
        )
        
        # Открываем PDF и считаем страницы
        doc = _fitz.open(task.input_path)
        total_pages = len(doc)
        
        # Отправляем общее количество страниц
        progress_queue.put({
            "type": "pages_total",
            "file_index": task.file_index,
            "total_pages": total_pages
        })
        
        # Создаём сервисы
        engine = _OCREngine(config)
        pdf_service = _PDFService(engine, config)
        
        # Очищаем выходной файл перед записью
        with open(task.output_path, "w", encoding="utf-8-sig") as f:
            pass
        
        current_page = 0
        
        for page_num in range(1, total_pages + 1):
            # Проверяем сигнал остановки
            try:
                check_msg = progress_queue.get_nowait()
                if check_msg.get("type") == "stop" and check_msg.get("file_index") == task.file_index:
                    doc.close()
                    return {
                        "success": False,
                        "input_path": str(task.input_path),
                        "error": "Остановлено пользователем",
                        "pages_processed": current_page
                    }
            except queue.Empty:
                pass
            
            try:
                # Рендеринг страницы
                page = doc[page_num - 1]
                zoom = config.dpi / 72.0
                mat = _fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                image = _Image.open(_io.BytesIO(img_data))
                del pix
                
                # OCR
                text = engine.recognize(image)
                
                # Запись в файл
                with open(task.output_path, "a", encoding="utf-8-sig") as f:
                    marker = config.get_page_marker(page_num)
                    f.write(marker)
                    f.write(text)
                    f.write("\n")
                
                del image
                current_page = page_num
                
                # Отправляем прогресс каждые 5 страниц
                if page_num % 5 == 0 or page_num == total_pages:
                    progress_queue.put({
                        "type": "page_progress",
                        "file_index": task.file_index,
                        "current_page": current_page,
                        "total_pages": total_pages
                    })
                
            except Exception as e:
                logger.error(f"Error on page {page_num}: {e}")
                with open(task.output_path, "a", encoding="utf-8-sig") as f:
                    f.write(f"\n@@ERROR:PAGE:{page_num}@@\n")
                continue
        
        doc.close()
        
        # Финальный прогресс
        progress_queue.put({
            "type": "page_progress",
            "file_index": task.file_index,
            "current_page": total_pages,
            "total_pages": total_pages
        })
        
        return {
            "success": True,
            "input_path": str(task.input_path),
            "output_path": str(task.output_path),
            "error": None,
            "pages_processed": total_pages
        }
        
    except Exception as e:
        logger.error(f"Critical error in _process_single_file: {e}", exc_info=True)
        return {
            "success": False,
            "input_path": str(task.input_path),
            "error": str(e),
            "pages_processed": 0
        }

class ConvertFrame(ctk.CTkFrame):
    """Вкладка пакетной конвертации PDF в TXT с постраничным прогрессом."""
    
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        
        self.file_widgets: List[FileWidget] = []
        self.output_folder: Optional[Path] = None
        self.is_processing = False
        self.stop_requested = False
        self.status_queue = queue.Queue()
        
        # Используем Manager().Queue() для общего доступа между процессами
        self.manager = multiprocessing.Manager()
        self.progress_queue = self.manager.Queue()
        
        self.executor: Optional[ProcessPoolExecutor] = None
        self.futures_dict: Dict = {}
        
        # Настройки параллелизма
        self.max_workers = min(4, max(1, multiprocessing.cpu_count() - 1))
        
        # === Верхняя панель ===
        self.top_frame = ctk.CTkFrame(self)
        self.top_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.top_frame.grid_columnconfigure(1, weight=1)
        
        self.btn_add = ctk.CTkButton(
            self.top_frame,
            text="📁 Добавить файлы",
            command=self._add_files,
            width=150
        )
        self.btn_add.grid(row=0, column=0, padx=10, pady=10)
        
        self.btn_clear = ctk.CTkButton(
            self.top_frame,
            text="🗑️ Очистить очередь",
            command=self._clear_queue,
            width=150,
            fg_color="gray"
        )
        self.btn_clear.grid(row=0, column=1, padx=10, pady=10, sticky="w")
        
        self.btn_output = ctk.CTkButton(
            self.top_frame,
            text="📂 Папка сохранения",
            command=self._select_output_folder,
            width=150
        )
        self.btn_output.grid(row=0, column=2, padx=10, pady=10)
        
        self.lbl_output = ctk.CTkLabel(
            self.top_frame,
            text="По умолчанию: рядом с PDF",
            text_color="gray"
        )
        self.lbl_output.grid(row=0, column=3, padx=10, pady=10, sticky="w")
        
        self.lbl_workers = ctk.CTkLabel(
            self.top_frame,
            text=f"Параллельно: {self.max_workers} файла",
            text_color="gray"
        )
        self.lbl_workers.grid(row=0, column=4, padx=10, pady=10, sticky="w")
        
        # === Общий прогресс бар ===
        self.progress_frame = ctk.CTkFrame(self)
        self.progress_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.pack(fill="x", padx=20, pady=10)
        self.progress_bar.set(0)
        
        self.lbl_progress = ctk.CTkLabel(
            self.progress_frame,
            text="Готов к работе",
            text_color="gray"
        )
        self.lbl_progress.pack(pady=(0, 10))
        
        # === Список файлов (очередь) ===
        self.list_frame = ctk.CTkFrame(self)
        self.list_frame.grid(row=2, column=0, sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)
        self.list_frame.grid_rowconfigure(0, weight=1)
        
        self.file_listbox = ctk.CTkScrollableFrame(self.list_frame)
        self.file_listbox.pack(fill="both", expand=True, padx=10, pady=10)
        
        # === Кнопки старта/стопа ===
        self.btn_start = ctk.CTkButton(
            self,
            text="▶️ Начать обработку",
            command=self._start_processing,
            height=50,
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.btn_start.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        
        self.btn_stop = ctk.CTkButton(
            self,
            text="⏹️ Остановить",
            command=self._stop_processing,
            height=50,
            fg_color="red",
            state="disabled"
        )
        self.btn_stop.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.btn_stop.grid_remove()
        
        # Поток для мониторинга прогресса
        self.progress_monitor_thread: Optional[threading.Thread] = None
        self.monitor_running = False
    
    def _add_files(self) -> None:
        """Открывает диалог выбора файлов и добавляет в очередь."""
        if self.is_processing:
            messagebox.showwarning("Предупреждение", "Нельзя добавлять файлы во время обработки")
            return
        
        files = filedialog.askopenfilenames(
            title="Выберите PDF файлы",
            filetypes=[("PDF файлы", "*.pdf")]
        )
        
        for file_path in files:
            path = Path(file_path)
            if not any(fw.queue_item.path == path for fw in self.file_widgets):
                queue_item = QueueItem(path=path, status="Ожидание")
                self._add_file_to_list(queue_item)
        
        self._update_progress_label()
    
    def _add_file_to_list(self, queue_item: QueueItem) -> None:
        """Добавляет файл в визуальный список с прогресс-баром."""
        frame = ctk.CTkFrame(self.file_listbox)
        frame.pack(fill="x", pady=5)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=0)
        
        lbl_name = ctk.CTkLabel(
            frame,
            text=queue_item.path.name,
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        lbl_name.grid(row=0, column=0, padx=10, pady=(5, 0), sticky="w")
        
        lbl_status = ctk.CTkLabel(
            frame,
            text=queue_item.status,
            text_color="gray",
            width=150
        )
        lbl_status.grid(row=0, column=1, padx=10, pady=(5, 0), sticky="e")
        
        progress_bar = ctk.CTkProgressBar(frame, width=300)
        progress_bar.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="ew")
        progress_bar.set(0)
        
        lbl_progress = ctk.CTkLabel(
            frame,
            text="0 / 0 страниц",
            text_color="gray",
            font=ctk.CTkFont(size=11)
        )
        lbl_progress.grid(row=1, column=1, padx=10, pady=(0, 5), sticky="e")
        
        file_widget = FileWidget(
            frame=frame,
            lbl_name=lbl_name,
            lbl_status=lbl_status,
            progress_bar=progress_bar,
            lbl_progress=lbl_progress,
            queue_item=queue_item
        )
        self.file_widgets.append(file_widget)
    
    def _clear_queue(self) -> None:
        """Очищает очередь файлов."""
        if self.is_processing:
            messagebox.showwarning("Предупреждение", "Нельзя очистить очередь во время обработки")
            return
        
        self.file_widgets.clear()
        for widget in self.file_listbox.winfo_children():
            widget.destroy()
        self._update_progress_label()
    
    def _select_output_folder(self) -> None:
        """Выбор папки для сохранения TXT файлов."""
        folder = filedialog.askdirectory(title="Выберите папку для сохранения TXT")
        if folder:
            self.output_folder = Path(folder)
            self.lbl_output.configure(text=f"✓ {folder}", text_color="green")
    
    def _update_progress_label(self) -> None:
        """Обновляет текст прогресса."""
        total = len(self.file_widgets)
        self.lbl_progress.configure(text=f"Файлов в очереди: {total}")
    
    def _start_processing(self) -> None:
        """Запускает параллельную обработку в ProcessPoolExecutor."""
        if not self.file_widgets:
            messagebox.showwarning("Предупреждение", "Добавьте файлы в очередь")
            return
        
        if self.is_processing:
            return
        
        # Проверка Tesseract перед запуском
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            logger.info("Tesseract found")
        except Exception as e:
            logger.error(f"Tesseract not found: {e}")
            messagebox.showerror(
                "Ошибка",
                f"Tesseract OCR не найден!\n\n"
                f"Установите Tesseract 5.x:\n"
                f"https://github.com/UB-Mannheim/tesseract/wiki\n\n"
                f"При установке отметьте:\n"
                f"✓ Russian language data\n"
                f"✓ Add to PATH\n\n"
                f"Ошибка: {str(e)}"
            )
            return
        
        # Очищаем очередь прогресса
        while not self.progress_queue.empty():
            try:
                self.progress_queue.get_nowait()
            except queue.Empty:
                break
        
        logger.info(f"Starting parallel processing with {self.max_workers} workers")
        
        self.is_processing = True
        self.stop_requested = False
        self.monitor_running = True
        self.btn_start.grid_remove()
        self.btn_stop.grid()
        self.btn_stop.configure(state="normal")
        self.btn_add.configure(state="disabled")
        self.btn_clear.configure(state="disabled")
        self.btn_output.configure(state="disabled")
        
        # Запуск обработки
        thread = threading.Thread(target=self._process_queue_parallel, daemon=True)
        thread.start()
        
        # Запуск мониторинга прогресса
        self.progress_monitor_thread = threading.Thread(target=self._monitor_progress, daemon=True)
        self.progress_monitor_thread.start()
        
        self._check_status()
    
    def _stop_processing(self) -> None:
        """Запрашивает остановку обработки."""
        self.stop_requested = True
        logger.info("Stop requested by user")
        self.lbl_progress.configure(text="⏹️ Остановка...")
        self.btn_stop.configure(state="disabled")
        
        # Отправляем сигнал остановки всем процессам
        for i in range(len(self.file_widgets)):
            self.progress_queue.put({"type": "stop", "file_index": i})
        
        messagebox.showinfo(
            "Информация", 
            "Обработка будет остановлена после завершения текущих страниц.\n"
            "Не закрывайте окно до полной остановки."
        )
    
    def _monitor_progress(self) -> None:
        """Мониторит очередь прогресса и обновляет GUI."""
        while self.monitor_running:
            try:
                msg = self.progress_queue.get(timeout=0.5)
                
                if msg["type"] == "pages_total":
                    self._update_page_total(msg["file_index"], msg["total_pages"])
                
                elif msg["type"] == "page_progress":
                    self._update_page_progress(
                        msg["file_index"],
                        msg["current_page"],
                        msg["total_pages"]
                    )
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Progress monitor error: {e}")
                break
        
        logger.info("Progress monitor stopped")
    
    def _update_page_total(self, index: int, total: int) -> None:
        """Обновляет общее количество страниц для файла."""
        def update():
            if index < len(self.file_widgets):
                fw = self.file_widgets[index]
                fw.queue_item.total_pages = total
                fw.lbl_progress.configure(text=f"0 / {total} страниц")
        self.after(0, update)
    
    def _update_page_progress(self, index: int, current: int, total: int) -> None:
        """Обновляет прогресс обработки страниц."""
        def update():
            if index < len(self.file_widgets):
                fw = self.file_widgets[index]
                fw.lbl_progress.configure(text=f"{current} / {total} страниц")
                
                if total > 0:
                    fw.progress_bar.set(current / total)
        self.after(0, update)
    
    def _process_queue_parallel(self) -> None:
        """Параллельная обработка через ProcessPoolExecutor."""
        try:
            total = len(self.file_widgets)
            completed = 0
            stopped = 0
            errors = 0
            
            # Определяем выходные пути
            for i, fw in enumerate(self.file_widgets):
                if self.output_folder:
                    fw.queue_item.output_path = self.output_folder / fw.queue_item.path.with_suffix(".txt").name
                else:
                    fw.queue_item.output_path = fw.queue_item.path.with_suffix(".txt")
            
            # Создаем пул процессов
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                self.executor = executor
                
                # Отправляем все задачи
                for i, fw in enumerate(self.file_widgets):
                    if self.stop_requested:
                        break
                    
                    task = ProcessTask(
                        input_path=fw.queue_item.path,
                        output_path=fw.queue_item.output_path,
                        dpi=300,
                        languages="rus",
                        tesseract_path=None,
                        file_index=i
                    )
                    
                    # Передаём progress_queue как аргумент
                    future = executor.submit(_process_single_file, task, self.progress_queue)
                    self.futures_dict[future] = i
                    self._update_file_status(i, "⏳ В процессе")
                
                # Обрабатываем завершённые задачи
                for future in as_completed(self.futures_dict):
                    if self.stop_requested:
                        for f in self.futures_dict:
                            f.cancel()
                        break
                    
                    index = self.futures_dict[future]
                    
                    try:
                        result = future.result(timeout=600)
                        
                        if result["success"]:
                            self._update_file_status(index, "✅ Готово")
                            completed += 1
                            logger.info(f"File completed: {result['input_path']}")
                        else:
                            if "Остановлено" in result.get("error", ""):
                                self._update_file_status(index, "⏹️ Остановлено")
                                stopped += 1
                            else:
                                self._update_file_status(index, "❌ Ошибка")
                                errors += 1
                            logger.error(f"File error: {result['error']}")
                            self.status_queue.put(("file_error", result['error']))
                        
                        # Обновляем общий прогресс
                        progress = (completed + errors + stopped) / total if total > 0 else 1.0
                        self._update_progress(progress, f"Обработано: {completed + errors + stopped}/{total}")
                        
                    except Exception as e:
                        logger.error(f"Future exception: {e}")
                        self._update_file_status(index, "❌ Ошибка")
                        errors += 1
                        self.status_queue.put(("file_error", str(e)))
            
            self.executor = None
            
            # Финальный отчёт
            self._update_progress(1.0, f"Завершено: {completed} успешно, {errors} ошибок")
            self.status_queue.put(("done", {
                "completed": completed,
                "errors": errors,
                "stopped": stopped
            }))
            
            logger.info(f"Parallel processing completed: {completed} successful, {errors} errors")
            
        except Exception as e:
            logger.critical(f"Critical error in parallel processing: {e}")
            logger.critical(traceback.format_exc())
            self.status_queue.put(("critical_error", str(e)))
        finally:
            self.executor = None
    
    def _update_file_status(self, index: int, status: str) -> None:
        """Обновляет статус файла в списке."""
        def update():
            if index < len(self.file_widgets):
                file_widget = self.file_widgets[index]
                file_widget.lbl_status.configure(text=status)
                
                if "✅" in status:
                    file_widget.lbl_status.configure(text_color="green")
                elif "❌" in status:
                    file_widget.lbl_status.configure(text_color="red")
                elif "⏹️" in status:
                    file_widget.lbl_status.configure(text_color="orange")
                elif "⏳" in status:
                    file_widget.lbl_status.configure(text_color="orange")
        
        self.after(0, update)
    
    def _update_progress(self, value: float, text: str) -> None:
        """Обновляет общий прогресс-бар."""
        def update():
            self.progress_bar.set(value)
            self.lbl_progress.configure(text=text)
        self.after(0, update)
    
    def _check_status(self) -> None:
        """Проверяет очередь статуса из потока обработки."""
        try:
            while True:
                msg_type, msg_data = self.status_queue.get_nowait()
                
                if msg_type == "done":
                    logger.info("Processing done message received")
                    self._reset_ui_state()
                    messagebox.showinfo(
                        "Завершено", 
                        f"Обработка завершена!\n"
                        f"✅ Успешно: {msg_data['completed']}\n"
                        f"❌ Ошибок: {msg_data['errors']}\n"
                        f"⏹️ Остановлено: {msg_data['stopped']}"
                    )
                
                elif msg_type == "file_error":
                    logger.warning(f"File error: {msg_data}")
                
                elif msg_type == "critical_error":
                    logger.error(f"Critical error: {msg_data}")
                    self._reset_ui_state()
                    messagebox.showerror("Критическая ошибка", msg_data)
                
        except queue.Empty:
            pass
        
        if self.is_processing:
            self.after(500, self._check_status)
    
    def _reset_ui_state(self) -> None:
        """Сбрасывает UI в исходное состояние."""
        self.is_processing = False
        self.stop_requested = False
        self.monitor_running = False
        self.futures_dict.clear()
        self.btn_start.grid()
        self.btn_stop.grid_remove()
        self.btn_add.configure(state="normal")
        self.btn_clear.configure(state="normal")
        self.btn_output.configure(state="normal")