#!/usr/bin/env python3
import argparse
import fnmatch
import os
from pathlib import Path

def format_path_header(rel_path: str) -> str:
    """Формирует визуальный блок-заголовок для пути"""
    width = max(60, len(rel_path) + 10)
    border = '━' * (width - 2)
    top = f'◈{border}◈'
    content = f' 📂 {rel_path} '
    padding = max(0, width - len(content) - 2)
    middle = f'┃{content}{" " * padding}┃'
    bottom = f'◈{border}◈'
    return f'{top}\n{middle}\n{bottom}'

def should_ignore(name: str, patterns: list) -> bool:
    """Проверяет, совпадает ли имя файла/папки с любым из паттернов"""
    return any(fnmatch.fnmatch(name, p) for p in patterns)

def merge_directory_to_txt(root_dir: str, output_file: str, ignore_patterns: list):
    root_path = Path(root_dir).resolve()
    output_path = Path(output_file).resolve()

    if not root_path.is_dir():
        raise FileNotFoundError(f"❌ Папка не найдена: {root_path}")
    if output_path.is_relative_to(root_path):
        raise ValueError("❌ Выходной файл не должен находиться внутри исходной папки.")

    print(f"🔍 Рекурсивный обход: {root_path}")
    print(f"🚫 Игнорируются паттерны: {', '.join(ignore_patterns)}")
    files_processed = 0

    with output_path.open('w', encoding='utf-8') as out_f:
        # os.walk позволяет модифицировать dirnames "на лету", 
        # чтобы не рекурсивно заходить в ненужные папки
        for dirpath, dirnames, filenames in os.walk(root_path):
            # Фильтруем и сортируем директории для детерминированного обхода
            dirnames[:] = sorted([
                d for d in dirnames if not should_ignore(d, ignore_patterns)
            ])

            for fname in sorted(filenames):
                file_path = Path(dirpath) / fname

                # Защита от чтения самого себя
                if file_path.resolve() == output_path:
                    continue
                if file_path.is_symlink():
                    continue
                if should_ignore(fname, ignore_patterns):
                    continue

                rel_path = file_path.relative_to(root_path)
                rel_str = str(rel_path).replace(os.sep, '/')

                out_f.write(format_path_header(rel_str) + '\n\n')

                try:
                    with file_path.open('r', encoding='utf-8', errors='replace') as in_f:
                        for line in in_f:
                            out_f.write(line)
                except Exception as e:
                    out_f.write(f'[⚠ ОШИБКА ЧТЕНИЯ: {e}]\n')

                out_f.write('\n' + '·' * 50 + '\n\n')
                files_processed += 1

    print(f"✅ Готово! Обработано файлов: {files_processed}")
    print(f"💾 Результат сохранён: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Рекурсивно собирает файлы в один .txt, игнорируя заданные паттерны."
    )
    parser.add_argument("source_dir", help="Путь к исходной директории")
    parser.add_argument("output_txt", help="Путь к выходному .txt файлу")
    parser.add_argument(
        "--ignore", nargs="*",
        default=[".env", "*.pyc", "__pycache__", ".DS_Store"],
        help="Паттерны для игнорирования (по умолчанию: .env *.pyc __pycache__ .DS_Store)"
    )
    args = parser.parse_args()

    try:
        # Убираем trailing slash, если пользователь указал __pycache__/
        patterns = [p.rstrip("/") for p in args.ignore]
        merge_directory_to_txt(args.source_dir, args.output_txt, patterns)
    except Exception as err:
        print(err)