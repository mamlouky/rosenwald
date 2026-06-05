"""
Main pipeline runner for one year.

Usage:
    python -m rosenwald.extract.run_year 1887
    python -m rosenwald.extract.run_year 1887 --limit=2   # test: at most 2 pages per section
    python -m rosenwald.extract.run_year 1887 --mode=unified       # ablation: step-2 baseline
    python -m rosenwald.extract.run_year 1887 --mode=routed-nogeo  # ablation: routing, no geo ctx
    # mode defaults to routegeo (full system). Non-default modes write to
    # data/tsv_raw_<mode>/ so they never clobber the production extraction.

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
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from rosenwald.config import Settings
from rosenwald.index_reader import read_sections_for_year
from rosenwald.extract.pdf_to_png import render_pdf_page_to_png
from rosenwald.extract.prompts import PROMPTS, UNIFIED_PROMPT
from rosenwald.extract.providers import (
    extract_tsv, resolve_model, api_key_for, provider_tag, PROVIDERS, KEY_ENV,
)


# Which TSV columns carry geographic / section context across pages.
CONTEXT_FIELDS: Dict[str, List[str]] = {
    "paris_quartiers":  ["arrondissement", "quartier", "profession_section"],
    "deps_cantons":     ["departement", "arrondissement", "canton", "profession_section"],
    "seine_cantons":    ["departement", "arrondissement", "canton", "profession_section"],
    "specialists":      ["specialite"],
    "thermal_spas":     ["station"],
    "paris_rues":       ["rue", "arrondissement", "profession_section"],
    "bienfaisance":     ["specialite"],
    "prefecture_seine": ["specialite"],
}

# Column order per list_type  kept here to avoi
# a circular import and to make run_year.py self-contained).
TSV_SCHEMA: Dict[str, List[str]] = {
    "paris_quartiers": [
        "year", "pdf_page", "arrondissement", "quartier", "profession_section",
        "full_name_raw", "diploma_year", "address_raw",
        "phone_raw", "hours_raw", "specialties_raw",
        "gender_marker_raw", "maiden_name_raw", "notes_raw", "entry_raw",
    ],
    "deps_cantons": [
        "year", "pdf_page", "departement", "arrondissement", "canton", "profession_section",
        "full_name_raw", "diploma_year", "address_raw",
        "gender_marker_raw", "maiden_name_raw", "notes_raw", "entry_raw",
    ],
    "specialists": [
        "year", "pdf_page", "specialite",
        "full_name_raw", "diploma_year", "address_raw",
        "phone_raw", "hours_raw",
        "gender_marker_raw", "maiden_name_raw", "notes_raw", "entry_raw",
    ],
    "thermal_spas": [
        "year", "pdf_page", "station",
        "full_name_raw", "diploma_year", "address_raw",
        "gender_marker_raw", "maiden_name_raw", "notes_raw", "entry_raw",
    ],
    "paris_rues": [
        "year", "pdf_page", "rue", "arrondissement", "profession_section",
        "full_name_raw", "diploma_year", "address_raw",
        "phone_raw", "hours_raw", "specialties_raw",
        "gender_marker_raw", "maiden_name_raw", "notes_raw", "entry_raw",
    ],
}
TSV_SCHEMA["seine_cantons"]    = TSV_SCHEMA["deps_cantons"]
TSV_SCHEMA["bienfaisance"]     = TSV_SCHEMA["specialists"]
TSV_SCHEMA["prefecture_seine"] = TSV_SCHEMA["specialists"]


# Ablation modes. Default is the full system, "routegeo".
# Each non-default mode writes to its own data/tsv_raw_<mode>/ tree so runs do
# not clobber the production extraction.
MODES = ("routegeo", "routed-nogeo", "unified")


def select_prompt_and_context(mode, list_type, prev_context):
    """Return (prompt_template, context_to_inject) for one page, given the mode.

    Pure function — unit-tested in tests/test_ablation.py.
    """
    if mode == "unified":
        return UNIFIED_PROMPT, None                  # no routing, no carry-forward
    prompt = PROMPTS.get(list_type)                  # routing on
    if mode == "routed-nogeo":
        return prompt, None                          # routing, but context off
    return prompt, (prev_context or None)            # routegeo: full system


def _raw_root_name(mode: str, provider: str = "gemini") -> str:
    base = "tsv_raw" if mode == "routegeo" else f"tsv_raw_{mode.replace('-', '_')}"
    tag = provider_tag(provider)
    return f"{base}_{tag}" if tag else base


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


def run_year(year: int, settings: Settings, api_key: str, limit: int = 0, mode: str = "routegeo",
             provider: str = "gemini", model_override: str = "") -> None:
    """limit: if > 0, process at most this many pages per section (for testing).
    mode: one of MODES; controls routing + context propagation.
    provider: which model adapter to use (gemini, gemini-pro, anthropic, openai)."""
    if mode not in MODES:
        raise ValueError(f"Unknown mode {mode!r}. Choose from {MODES}.")
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}. Choose from {PROVIDERS}.")
    model = resolve_model(provider, model_override)
    sections = read_sections_for_year(year, settings.excel_index)
    if not sections:
        print(f"[WARN] No sections found for year {year} in {settings.excel_index}")
        return

    print(f"\n{'='*60}")
    print(f"  Year {year} — {len(sections)} sections — mode={mode}")
    print(f"{'='*60}")
    for s in sections:
        print(f"  [{s.list_type:20s}]  pages {s.page_start:4d}–{s.page_end:4d}  ({s.num_pages:3d} pages)  {s.list_name}")

    total_pages = sum(s.num_pages for s in sections)
    print(f"\n  Total pages: {total_pages}")
    print(f"{'='*60}\n")

    done = skipped = errors = 0

    for section in sections:
        if mode != "unified" and PROMPTS.get(section.list_type) is None:
            print(f"[WARN] No prompt defined for list_type='{section.list_type}' — skipping: {section.list_name}")
            continue

        pdf_path = settings.pdf_path(year)
        if not pdf_path.exists():
            print(f"[ERROR] PDF not found: {pdf_path}")
            continue

        img_dir = settings.images_dir(year, section.list_type)
        tsv_dir = settings.data_dir / _raw_root_name(mode, provider) / str(year) / section.list_type
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

            # Call Gemini (prompt + context chosen per ablation mode)
            try:
                page_prompt, page_ctx = select_prompt_and_context(
                    mode, section.list_type, prev_context
                )
                tsv = extract_tsv(
                    provider,
                    settings=settings,
                    image_path=img_path,
                    year=year,
                    pdf_page=page,
                    model=model,
                    api_key=api_key,
                    prompt_template=page_prompt,
                    prev_context=page_ctx,
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
        print(f" -> Check .error files in data/tsv_raw/{year}/")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m rosenwald.extract.run_year YEAR")
        print("Example: python -m rosenwald.extract.run_year 1887")
        sys.exit(1)

    year = int(sys.argv[1])

    limit = 0
    mode = "routegeo"
    provider = "gemini"
    model_override = ""
    for arg in sys.argv[2:]:
        if arg.startswith("--limit="):
            limit = int(arg.split("=")[1])
        elif arg.startswith("--mode="):
            mode = arg.split("=", 1)[1]
        elif arg.startswith("--provider="):
            provider = arg.split("=", 1)[1]
        elif arg.startswith("--model="):
            model_override = arg.split("=", 1)[1]

    api_key = api_key_for(provider)
    if not api_key:
        env = KEY_ENV[provider]
        raise RuntimeError(
            f"{env} is not set.\n"
            "Add it to your .env file at the project root:\n"
            f"  {env}=your-key-here"
        )

    settings = Settings()
    run_year(year, settings, api_key, limit=limit, mode=mode,
             provider=provider, model_override=model_override)


if __name__ == "__main__":
    main()
