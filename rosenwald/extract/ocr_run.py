"""
Classic OCR pipeline — runs Tesseract on every PDF page for a given year.

Usage:
    python ocr/run_ocr.py <year> [--limit N] [--lang fra]

Output:
    data/ocr_text/<year>/<list_type>/page-XXXX.txt  — one text file per page

Already-processed pages (non-empty .txt) are skipped automatically.
Re-running after failures will only retry failed pages.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Project root (used to locate the index file)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

from rosenwald.config import Settings
from rosenwald.index_reader import read_sections_for_year
from rosenwald.extract.pdf_to_png import render_pdf_page_to_png
from rosenwald.extract.tesseract import ocr_image


def main() -> None:
    parser = argparse.ArgumentParser(description="Tesseract OCR pipeline for one year")
    parser.add_argument("year", type=int)
    parser.add_argument("--limit", type=int, default=0,
                        help="Max pages per section (0 = all)")
    parser.add_argument("--lang", default="fra",
                        help="Tesseract language code (default: fra)")
    args = parser.parse_args()

    settings = Settings()
    excel_path = _PROJECT_ROOT / settings.excel_index.name

    sections = read_sections_for_year(args.year, excel_path=excel_path)
    if not sections:
        print(f"[ERROR] No sections found for year {args.year} in the index.")
        sys.exit(1)

    total_pages = sum(s.num_pages for s in sections)
    print()
    print("=" * 60)
    print(f"  Year {args.year} — {len(sections)} sections  (OCR mode)")
    print("=" * 60)
    for s in sections:
        print(f"  [{s.list_type:<20}]  pages {s.page_start:4d}–{s.page_end:4d}  ({s.num_pages:3d} pages)  {s.list_name}")
    print(f"\n  Total pages: {total_pages}")
    print("=" * 60)

    pdf_path = settings.pdf_path(args.year)
    if not pdf_path.exists():
        print(f"[ERROR] PDF not found: {pdf_path}")
        sys.exit(1)

    done = skipped = errors = 0

    for section in sections:
        pages = list(section.pages)
        if args.limit > 0:
            pages = pages[: args.limit]

        rotate_deg = 90 if section.is_rotated else 0
        print(f"\n[SECTION] {section.list_type} — pages {section.page_start}–{section.page_end}")

        img_dir = settings.images_dir(args.year, section.list_type)
        txt_dir = settings.ocr_text_dir(args.year, section.list_type)
        img_dir.mkdir(parents=True, exist_ok=True)
        txt_dir.mkdir(parents=True, exist_ok=True)

        for page in pages:
            txt_path = txt_dir / f"page-{page:04d}.txt"

            # Skip already-processed pages
            if txt_path.exists() and txt_path.stat().st_size > 10:
                skipped += 1
                continue

            # Render PDF page to PNG if not already rendered
            img_path = img_dir / f"page-{page:04d}.png"
            if not img_path.exists():
                try:
                    render_pdf_page_to_png(
                        pdf_path, page, img_path,
                        dpi=settings.dpi,
                        rotate_deg=rotate_deg,
                    )
                except Exception as e:
                    print(f"  [ERROR] Render failed page {page}: {e}")
                    errors += 1
                    continue

            # Run Tesseract OCR
            # prefecture_seine pages are single-column (landscape, rotated)
            two_columns = section.list_type != "prefecture_seine"
            try:
                text = ocr_image(img_path, lang=args.lang, two_columns=two_columns)
                txt_path.write_text(text, encoding="utf-8")
                done += 1
                print(f"  [OK] page {page:04d}")
            except Exception as e:
                print(f"  [ERROR] OCR failed page {page}: {e}")
                errors += 1

    print()
    print("=" * 60)
    print(f"  Done: {done}  |  Skipped: {skipped}  |  Errors: {errors}")
    print("=" * 60)


if __name__ == "__main__":
    main()
