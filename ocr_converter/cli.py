import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from .config import OCRConfig
from .services.ocr_engine import OCREngine
from .services.pdf_service import PDFService
from .services.search_service import SearchService
from .exceptions import OCRError
from .services.batch_service import BatchService

def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("ocr_converter.log", encoding="utf-8", mode='a')
        ]
    )

def run_conversion(input_file: Path, output_file: Path, config: OCRConfig) -> None:
    engine = OCREngine(config)
    service = PDFService(engine, config)
    service.process_file(input_file, output_file)

def run_search(file_path: Path, query: str, verbose: bool = False) -> None:
    """Запускает поиск и выводит форматированный результат."""
    search_service = SearchService(case_sensitive=False)
    
    # Проверяем, существует ли TXT файл. Если нет, пытаемся найти его по имени PDF
    if not file_path.exists():
        if file_path.suffix == ".pdf":
            file_path = file_path.with_suffix(".txt")
        if not file_path.exists():
            logging.error(f"File not found: {file_path}")
            sys.exit(1)
    
    try:
        result = search_service.search(file_path, query)
        
        print("\n" + "="*60)
        print(f"🔍 РЕЗУЛЬТАТЫ ПОИСКА: '{query}'")
        print(f"📄 Файл: {result.file_path.name}")
        print("="*60)
        
        if result.total_matches == 0:
            print("❌ Ничего не найдено.")
        else:
            print(f"✅ Всего найдено: {result.total_matches} вхождений")
            print(f"📌 Страницы: {', '.join(map(str, result.pages_with_matches))}")
            print("-"*60)
            
            # Выводим первые 5 совпадений для примера (чтобы не спамить в консоль)
            preview_count = min(5, len(result.matches))
            print(f"📋 Первые {preview_count} совпадений:")
            
            for i, match in enumerate(result.matches[:preview_count], 1):
                print(f"\n  [{i}] Страница {match.page_number}")
                print(f"      ...{match.line_content}...")
            
            if len(result.matches) > preview_count:
                print(f"\n  ... и ещё {len(result.matches) - preview_count} совпадений")
        
        print("="*60 + "\n")
        
        if verbose and result.matches:
            # В режиме verbose выводим все совпадения
            logging.debug(f"All matches: {result.matches}")
            
    except FileNotFoundError as e:
        logging.error(e)
        sys.exit(1)
    except Exception as e:
        logging.critical(f"Search failed: {e}", exc_info=True)
        sys.exit(3)

def run_batch(source: Path, config: OCRConfig, max_workers: Optional[int] = None, skip_existing: bool = True) -> None:
    """Запускает пакетную обработку."""
    service = BatchService(
        config=config,
        max_workers=max_workers,
        skip_existing=skip_existing
    )
    summary = service.process_batch(source)
    
    # Выход с кодом ошибки если есть неудачи
    if summary.failed > 0:
        import sys
        sys.exit(2)

def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCR Конвертер PDF + Поиск по тексту + Пакетная обработка."
    )
    
    # Группы режимов работы
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--convert", 
        type=Path, 
        help="Режим конвертации: путь к входному PDF"
    )
    mode_group.add_argument(
        "--search", 
        type=Path, 
        help="Режим поиска: путь к TXT файлу (или PDF, будет искаться .txt)"
    )
    mode_group.add_argument(
        "--batch", 
        type=Path, 
        help="Режим пакетной обработки: путь к папке или файлу"
    )
    
    # Аргументы конвертации
    parser.add_argument(
        "-o", "--output", 
        type=Path, 
        help="Путь к выходному TXT файлу (для --convert)"
    )
    parser.add_argument(
        "--tesseract", 
        type=Path, 
        help="Путь к tesseract.exe"
    )
    parser.add_argument(
        "--dpi", 
        type=int, 
        default=300, 
        help="DPI для рендеринга (рекомендуется 300)"
    )
    
    # Аргументы поиска
    parser.add_argument(
        "-q", "--query", 
        type=str, 
        help="Искомое слово или фраза (для режима --search)"
    )
    
    # Аргументы пакетной обработки
    parser.add_argument(
        "--workers", 
        type=int, 
        default=None,
        help="Количество параллельных процессов (по умолчанию: CPU - 1)"
    )
    parser.add_argument(
        "--no-skip", 
        action="store_true",
        help="Не пропускать уже обработанные файлы (перезаписать)"
    )
    
    # Общие
    parser.add_argument(
        "-v", "--verbose", 
        action="store_true", 
        help="Подробное логирование"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    # Общая конфигурация
    config = OCRConfig(
        languages="rus",
        dpi=args.dpi,
        tesseract_path=args.tesseract
    )

    # Режим конвертации (один файл)
    if args.convert:
        output_path = args.output or args.convert.with_suffix(".txt")
        if output_path.suffix != ".txt":
            output_path = output_path.with_suffix(".txt")

        try:
            run_conversion(args.convert, output_path, config)
        except FileNotFoundError as e:
            logging.error(e)
            sys.exit(1)
        except OCRError as e:
            logging.error(f"OCR Processing failed: {e}")
            sys.exit(2)
        except Exception as e:
            logging.critical(f"Unexpected error: {e}", exc_info=True)
            sys.exit(3)

    # Режим поиска
    elif args.search:
        if not args.query:
            logging.error("Для режима поиска обязателен аргумент --query (-q)")
            sys.exit(1)
        
        run_search(args.search, args.query, args.verbose)

    # Режим пакетной обработки
    elif args.batch:
        run_batch(
            source=args.batch,
            config=config,
            max_workers=args.workers,
            skip_existing=not args.no_skip
        )

if __name__ == "__main__":
    main()