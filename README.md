# OCR Converter

Конвертация PDF-сканов в текст с поиском по документам.

## Возможности

- 📄 Конвертация PDF (сканов) в TXT с помощью OCR
- 🔍 Поиск слов и словосочетаний по оцифрованным документам
- 📊 Пакетная обработка нескольких файлов одновременно
- 📈 Постраничный прогресс обработки
- 🖥️ Современный GUI на CustomTkinter

## Требования

- Python 3.10+
- Windows 10/11
- Tesseract OCR 5.x (обязательно!)

## Установка Tesseract

1. Скачайте установщик: https://github.com/UB-Mannheim/tesseract/wiki
2. При установке отметьте:
   - ✓ Russian language data
   - ✓ Add Tesseract to the PATH

## Установка

```bash
# Клонирование репозитория
git clone https://github.com/ваш-username/ocr-converter.git
cd ocr-converter

# Создание виртуального окружения
python -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
venv\Scripts\activate  # Windows

# Установка зависимостей
pip install -r requirements.txt


##Запуск gui версии
python main_gui.py


## Запуск CLI версии
# Конвертация одного файла
python main.py --convert document.pdf
# Пакетная обработка
python main.py --batch C:\Scans\
# Поиск по файлу
python main.py --search document.txt -q "договор"


##Сборка в .exe
pip install pyinstaller
pyinstaller --onedir --windowed --name "OCR_Converter" main_gui.py --clean