"""Genera los libros de muestra en samples/ y su resultado esperado en samples/expected/.

    uv run python -m scripts.samples
"""

from pathlib import Path

from scripts.samples.books import BUILDERS

SAMPLES_DIR = Path("samples")


def main() -> None:
    expected_dir = SAMPLES_DIR / "expected"
    expected_dir.mkdir(parents=True, exist_ok=True)
    for build in BUILDERS:
        book = build(SAMPLES_DIR)
        book.save(expected_dir)
        print(f"{book.file_name}: hojas principales {book.principal}, {sum(book.quotations.values())} cotizaciones")


if __name__ == "__main__":
    main()
