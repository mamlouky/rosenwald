"""
Main pipeline runner for one year.

Usage:
    python src/run_year.py 1887
    python src/run_year.py 1887 --limit=2   # test: at most 2 pages per section

What it does:
    1. Reads the Excel index to get all list sections for the given year
    2. For each section (e.g. paris_quartiers pages 328-375):
       a. Renders each PDF page to PNG (skips if already rendered)
       b. Calls Gemini with the right prompt for that list type,
          injecting geographic context from the previous page so
          carry-forward fields (arrondissement, canton, etc.) are not lost.
       c. Saves the TSV response to data/tsv_raw/YEAR/LIST_TYPE/page-NNNN.tsv
    3. Skips pages that already have a non-empty TSV (safe to re-run / resume)

Requires:
    GOOGLE_API_KEY env var (or .env file at project root).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from config import Settings
from index_reader import read_sections_for_year
from pdf_to_png import render_pdf_page_to_png
from prompts import PROMPTS
from gemini_image_extract import gemini_extract_tsv_from_image_http


# ─────────────────────────────────────────────────────────────────────────────
# Which TSV columns carry geographic / section context across pages.
# Must match the column order defined in women_filter.SCHEMA exactly.
# ─────────────────────────────────────────────────────────────────────────────
CONTEXT_FIELDS: Dict[str, List[str]] = {
    "paris_quartiers":  ["arrondissement", "quartier", "profession_section"],
    "deps_cantons":     ["departement", "canton", "profession_section"],
    "seine_cantons":    ["departement", "canton", "profession_section"],
    "specialists":      ["specialite", "profession_section"],
    "thermal_spas":     ["station"],
    "paris_rues":       ["rue", "arrondissement", "profession_section"],
    "bienfaisance":     ["specialite", "profession_section"],
    "prefecture_seine": ["specialite"],
}

# Column order per list_type (mirrors women_filter.SCHEMA — kept here to avoid
# a circular import and to make run_year.py self-contained).
TSV_SCHEMA: Dict[str, List[str]] = {
    "paris_quartiers": [
        "year", "pdf_page", "arrondissement", "quartier", "profession_section",
        "full_name_raw", "civil_status", "diploma_year", "address_raw",
        "phone_raw", "hours_raw", "specialties_raw", "notes_raw", "entry_raw",
    ],
    "deps_cantons": [
        "year", "pdf_page", "departement", "canton", "profession_section",
        "full_name_raw", "civil_status", "diploma_year", "address_raw",
        "notes_raw", "entry_raw",
    ],
    "specialists": [
        "year", "pdf_page", "specialite",
        "full_name_raw", "civil_status", "diploma_year", "address_raw",
        "phone_raw", "hours_raw", "notes_raw", "entry_raw",
    ],
    "thermal_spas": [
        "year", "pdf_page", "station",
        "full_name_raw", "civil_status", "diploma_year", "address_raw",
        "notes_raw", "entry_raw",
    ],
    "paris_rues": [
        "year", "pdf_page", "rue", "arrondissement", "profession_section",
        "full_name_raw", "civil_status", "diploma_year", "address_raw",
        "phone_raw", "hours_raw", "specialties_raw", "notes_raw", "entry_raw",
    ],
}
TSV_SCHEMA["seine_cantons"]    = TSV_SCHEMA["deps_cantons"]
TSV_SCHEMA["bienfaisance"]     = TSV_SCHEMA["specialists"]
TSV_SCHEMA["prefecture_seine"] = TSV_SCHEMA["specialists"]


def _extract_last_context(
    tsv_path: Path,
    schema: List[str],
    fields: List[str],
) -> Dict[str, str]:
    """
    Parse a saved TSV page and return the *last* non-empty value for each
    context field.  Called both for freshly written pages and for already-
    skipped pages so the carry-forward chain is never broken.
    """
    context: Dict[str, str] = {f: "" for f in fields}
    if not tsv_path.exists() or tsv_path.stat().st_size < 5:
        return context
    try:
        for line in tsv_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            for field in fields:
                if field in schema:
                    idx = schema.index(field)
                    val = parts[idx].strip() if idx < len(parts) else ""
                    if val and val not in (r"\N", "NULL", "null"):
                        context[field] = val
    except Exception:
        pass
    return context


def run_year(year: int, settings: Settings, api_key: str, limit: int = 0) -> None:
    """limit: if > 0, process at most this many pages per section (for testing)."""
    sections = read_sections_for_year(year, settings.excel_index)
    if not sections:
        print(f"[WARN] No sections found for year {year} in {settings.excel_index}")
        return

    print(f"\n{'='*60}")
    print(f"  Year {year} — {len(sections)} sections")
    print(f"{'='*60}")
    for s in sections:
        print(f"  [{s.list_type:20s}]  pages {s.page_start:4d}–{s.page_end:4d}  ({s.num_pages:3d} pages)  {s.list_name}")

    total_pages = sum(s.num_pages for s in sections)
    print(f"\n  Total pages: {total_pages}")
    print(f"{'='*60}\n")

    done = skipped = errors = 0

    for section in sections:
        prompt = PROMPTS.get(section.list_type)
        if prompt is None:
            print(f"[WARN] No prompt defined for list_type='{section.list_type}' — skipping: {section.list_name}")
            continue

        pdf_path = settings.pdf_path(year)
        if not pdf_path.exists():
            print(f"[ERROR] PDF not found: {pdf_path}")
            continue

        img_dir = settings.images_dir(year, section.list_type)
        tsv_dir = settings.tsv_raw_dir(year, section.list_type)
        img_dir.mkdir(parents=True, exist_ok=True)
        tsv_dir.mkdir(parents=True, exist_ok=True)

        rotate_deg = 90 if section.is_rotated else 0
        if rotate_deg:
            print(f"[SECTION] {section.list_type} — pages {section.page_start}–{section.page_end}  [landscape → rotating {rotate_deg}°]")
        else:
            print(f"[SECTION] {section.list_type} — pages {section.page_start}–{section.page_end}")

        pages = list(section.pages)
        if limit > 0:
            pages = pages[:limit]

        ctx_fields = CONTEXT_FIELDS.get(section.list_type, [])
        schema     = TSV_SCHEMA.get(section.list_type, [])
        prev_context: Dict[str, str] = {}   # reset at the start of each section

        for page in pages:
            tsv_path = tsv_dir / f"page-{page:04d}.tsv"

            # Skip already-processed pages — but still update carry-forward context
            if tsv_path.exists() and tsv_path.stat().st_size > 10:
                if ctx_fields and schema:
                    prev_context = _extract_last_context(tsv_path, schema, ctx_fields)
                skipped += 1
                continue

            # Render PDF page to PNG if needed
            img_path = img_dir / f"page-{page:04d}.png"
            if not img_path.exists():
                try:
                    render_pdf_page_to_png(pdf_path, page, img_path, dpi=settings.dpi, rotate_deg=rotate_deg)
                except Exception as e:
                    print(f"  [ERROR] Render failed page {page}: {e}")
                    errors += 1
                    continue

            # Call Gemini (with context from previous page)
            try:
                tsv = gemini_extract_tsv_from_image_http(
                    image_path=img_path,
                    year=year,
                    pdf_page=page,
                    model=settings.model,
                    api_key=api_key,
                    prompt_template=prompt,
                    prev_context=prev_context if prev_context else None,
                )
                tsv_path.write_text(tsv, encoding="utf-8")
                done += 1
                processed_so_far = done + errors
                print(f"  [OK] page {page:04d}  ({processed_so_far}/{total_pages - skipped} to do)")

                # Update context for the next page
                if ctx_fields and schema:
                    prev_context = _extract_last_context(tsv_path, schema, ctx_fields)

            except Exception as e:
                err_path = tsv_dir / f"page-{page:04d}.error"
                err_path.write_text(str(e), encoding="utf-8")
                print(f"  [ERROR] page {page}: {e}")
                errors += 1

    print(f"\n[DONE] Year {year}: {done} extracted, {skipped} already done, {errors} errors")
    if errors:
        print(f"  -> Check .error files in data/tsv_raw/{year}/")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python src/run_year.py YEAR")
        print("Example: python src/run_year.py 1887")
        sys.exit(1)

    year = int(sys.argv[1])

    limit = 0
    for arg in sys.argv[2:]:
        if arg.startswith("--limit="):
            limit = int(arg.split("=")[1])

    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set.\n"
            "Add it to your .env file at the project root:\n"
            "  GOOGLE_API_KEY=your-key-here"
        )

    settings = Settings()
    run_year(year, settings, api_key, limit=limit)


if __name__ == "__main__":
    main()
