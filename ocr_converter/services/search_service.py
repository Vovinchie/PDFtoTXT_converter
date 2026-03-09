# src/ocr_converter/services/search_service.py
import logging
import re
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class SearchMatch:
    """Результат одного найденного вхождения."""
    page_number: int
    line_number: int
    line_content: str
    position: int  # Позиция в строке

@dataclass
class SearchResult:
    """Агрегированный результат поиска по файлу."""
    file_path: Path
    query: str
    total_matches: int
    pages_with_matches: List[int]
    matches: List[SearchMatch]

class SearchService:
    """
    Поиск по оцифрованным TXT файлам с определением номеров страниц.
    Работает только с файлами, созданными через PDFService (с маркерами).
    """
    
    # Регулярное выражение для поиска маркеров страниц @@PAGE:123@@
    PAGE_MARKER_PATTERN = re.compile(r"@@PAGE:(\d+)@@")
    
    def __init__(self, case_sensitive: bool = False):
        """
        Args:
            case_sensitive: Если False, поиск будет регистронезависимым.
        """
        self.case_sensitive = case_sensitive

    def _parse_file_with_pages(self, file_path: Path) -> List[Tuple[int, str]]:
        """
        Парсит TXT файл и возвращает список кортежей (номер_страницы, текст_строки).
        
        Returns:
            Список кортежей (page_num, line_content) для каждой строки текста.
        """
        result = []
        current_page = 1
        
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                for line in f:
                    # Проверяем, является ли строка маркером страницы
                    match = self.PAGE_MARKER_PATTERN.search(line)
                    if match:
                        current_page = int(match.group(1))
                        logger.debug(f"Page marker found: {current_page}")
                        continue
                    
                    # Если это не маркер и не пустая строка - добавляем в результат
                    if line.strip():
                        result.append((current_page, line))
                        
        except Exception as e:
            logger.error(f"Failed to parse file {file_path}: {e}")
            raise
        
        return result

    def search(self, file_path: Path, query: str) -> SearchResult:
        """
        Выполняет поиск запроса в файле.
        
        Args:
            file_path: Путь к TXT файлу.
            query: Искомое слово или фраза.
            
        Returns:
            SearchResult с полной статистикой.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Search file not found: {file_path}")
        
        logger.info(f"Starting search for '{query}' in {file_path.name}")
        
        # Подготовка к поиску
        lines_with_pages = self._parse_file_with_pages(file_path)
        matches: List[SearchMatch] = []
        pages_set: set = set()
        
        # Флаги для регистронезависимого поиска
        flags = 0 if self.case_sensitive else re.IGNORECASE
        
        try:
            # Экранируем спецсимволы regex в запросе пользователя
            escaped_query = re.escape(query)
            pattern = re.compile(escaped_query, flags)
            
            for line_num, (page_num, line_content) in enumerate(lines_with_pages, start=1):
                # Ищем все вхождения в строке
                for match_obj in pattern.finditer(line_content):
                    match = SearchMatch(
                        page_number=page_num,
                        line_number=line_num,
                        line_content=line_content.strip()[:100],  # Обрезаем для вывода
                        position=match_obj.start()
                    )
                    matches.append(match)
                    pages_set.add(page_num)
            
            # Сортируем страницы для удобного вывода
            pages_sorted = sorted(list(pages_set))
            
            logger.info(f"Search completed. Found {len(matches)} matches on {len(pages_sorted)} pages.")
            
            return SearchResult(
                file_path=file_path,
                query=query,
                total_matches=len(matches),
                pages_with_matches=pages_sorted,
                matches=matches
            )
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

    def search_multiple_files(self, files: List[Path], query: str) -> List[SearchResult]:
        """
        Поиск по нескольким файлам одновременно.
        """
        results = []
        for file_path in files:
            try:
                result = self.search(file_path, query)
                if result.total_matches > 0:
                    results.append(result)
            except Exception as e:
                logger.error(f"Skipping {file_path}: {e}")
                continue
        return results