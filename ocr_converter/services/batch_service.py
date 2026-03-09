# src/ocr_converter/services/batch_service.py
import logging
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass, field
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
import time

from ..config import OCRConfig
from .pdf_service import PDFService
from .ocr_engine import OCREngine

logger = logging.getLogger(__name__)

@dataclass
class BatchTask:
    """Задача на обработку одного файла."""
    input_path: Path
    output_path: Path
    config: OCRConfig

@dataclass
class BatchResult:
    """Результат обработки одного файла в пакете."""
    input_path: Path
    output_path: Path
    success: bool
    error_message: Optional[str] = None
    processing_time: float = 0.0
    pages_processed: int = 0

@dataclass
class BatchSummary:
    """Сводка по всей пакетной обработке."""
    total_files: int
    successful: int
    failed: int
    total_time: float
    results: List[BatchResult] = field(default_factory=list)
    
    def get_failed_files(self) -> List[Path]:
        """Возвращает список файлов, которые не удалось обработать."""
        return [r.input_path for r in self.results if not r.success]

def _process_single_file(task: BatchTask) -> BatchResult:
    """
    Функция-обёртка для обработки одного файла.
    Вызывается в отдельном процессе, поэтому должна быть на верхнем уровне модуля.
    """
    start_time = time.time()
    
    try:
        # В каждом процессе создаём свои экземпляры сервисов
        engine = OCREngine(task.config)
        service = PDFService(engine, task.config)
        
        # Получаем количество страниц для отчёта (до обработки)
        import fitz
        doc = fitz.open(task.input_path)
        pages_count = len(doc)
        doc.close()
        
        # Запускаем обработку
        service.process_file(task.input_path, task.output_path)
        
        processing_time = time.time() - start_time
        
        return BatchResult(
            input_path=task.input_path,
            output_path=task.output_path,
            success=True,
            processing_time=processing_time,
            pages_processed=pages_count
        )
        
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Failed to process {task.input_path}: {e}")
        
        return BatchResult(
            input_path=task.input_path,
            output_path=task.output_path,
            success=False,
            error_message=str(e),
            processing_time=processing_time
        )

class BatchService:
    """
    Сервис для пакетной обработки множества PDF файлов.
    Использует multiprocessing для параллелизации CPU-intensive задач.
    """
    
    def __init__(
        self, 
        config: OCRConfig, 
        max_workers: Optional[int] = None,
        skip_existing: bool = True
    ):
        """
        Args:
            config: Конфигурация OCR.
            max_workers: Максимальное количество параллельных процессов.
                        По умолчанию = количество ядер CPU - 1.
            skip_existing: Если True, пропускает уже обработанные файлы.
        """
        self.config = config
        # Оставляем 1 ядро свободным для системы, чтобы ПК не зависал
        self.max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)
        self.skip_existing = skip_existing
        
        logger.info(f"BatchService initialized with {self.max_workers} workers")

    def _discover_pdf_files(self, source: Path) -> List[Path]:
        """
        Находит все PDF файлы в источнике.
        
        Args:
            source: Путь к файлу или папке.
            
        Returns:
            Список путей к PDF файлам.
        """
        if source.is_file():
            return [source] if source.suffix.lower() == ".pdf" else []
        
        if source.is_dir():
            pdf_files = list(source.glob("**/*.pdf"))
            logger.info(f"Found {len(pdf_files)} PDF files in {source}")
            return pdf_files
        
        return []

    def _prepare_tasks(self, pdf_files: List[Path]) -> List[BatchTask]:
        """
        Подготавливает список задач, исключая уже обработанные файлы.
        """
        tasks = []
        skipped = 0
        
        for pdf_path in pdf_files:
            output_path = pdf_path.with_suffix(".txt")
            
            # Проверка на существующий выходной файл
            if self.skip_existing and output_path.exists():
                logger.info(f"Skipping {pdf_path.name} (already processed)")
                skipped += 1
                continue
            
            tasks.append(BatchTask(
                input_path=pdf_path,
                output_path=output_path,
                config=self.config
            ))
        
        if skipped > 0:
            logger.info(f"Skipped {skipped} already processed files")
        
        return tasks

    def process_batch(self, source: Path) -> BatchSummary:
        """
        Обрабатывает пакет файлов.
        
        Args:
            source: Путь к файлу или папке с PDF.
            
        Returns:
            BatchSummary с результатами обработки.
        """
        start_time = time.time()
        
        # 1. Поиск файлов
        pdf_files = self._discover_pdf_files(source)
        
        if not pdf_files:
            logger.warning("No PDF files found to process")
            return BatchSummary(
                total_files=0,
                successful=0,
                failed=0,
                total_time=0.0
            )
        
        # 2. Подготовка задач
        tasks = self._prepare_tasks(pdf_files)
        
        if not tasks:
            logger.info("All files already processed (skip_existing=True)")
            return BatchSummary(
                total_files=len(pdf_files),
                successful=len(pdf_files),
                failed=0,
                total_time=0.0
            )
        
        logger.info(f"Starting batch processing of {len(tasks)} files")
        
        # 3. Параллельная обработка
        results: List[BatchResult] = []
        completed = 0
        
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Отправляем задачи в пул
            future_to_task = {
                executor.submit(_process_single_file, task): task 
                for task in tasks
            }
            
            # Обрабатываем завершённые задачи
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                completed += 1
                
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Прогресс в лог
                    status = "✅" if result.success else "❌"
                    logger.info(
                        f"[{completed}/{len(tasks)}] {status} {task.input_path.name} "
                        f"({result.processing_time:.1f}s)"
                    )
                    
                except Exception as e:
                    # Если процесс упал критически
                    logger.critical(f"Task {task.input_path} crashed: {e}")
                    results.append(BatchResult(
                        input_path=task.input_path,
                        output_path=task.output_path,
                        success=False,
                        error_message=str(e)
                    ))
        
        # 4. Формирование сводки
        total_time = time.time() - start_time
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        
        summary = BatchSummary(
            total_files=len(tasks),
            successful=successful,
            failed=failed,
            total_time=total_time,
            results=results
        )
        
        # 5. Вывод итогов
        self._print_summary(summary)
        
        return summary

    def _print_summary(self, summary: BatchSummary) -> None:
        """Выводит красивую сводку по результатам обработки."""
        print("\n" + "="*70)
        print("📊 ОТЧЁТ ПО ПАКЕТНОЙ ОБРАБОТКЕ")
        print("="*70)
        print(f"📁 Всего файлов:      {summary.total_files}")
        print(f"✅ Успешно:           {summary.successful}")
        print(f"❌ Ошибок:            {summary.failed}")
        print(f"⏱️  Общее время:      {summary.total_time:.1f} сек")
        
        if summary.total_files > 0:
            avg_time = summary.total_time / summary.total_files
            print(f"📈 Среднее на файл:  {avg_time:.1f} сек")
        
        if summary.failed > 0:
            print("\n⚠️  Файлы с ошибками:")
            for result in summary.results:
                if not result.success:
                    print(f"   • {result.input_path.name}: {result.error_message}")
        
        print("="*70 + "\n")