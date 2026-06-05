"""
Step 3 of the pipeline: convert the merged annotated TSV into the final Excel file.

Usage:
    python -m rosenwald.postprocess.export_excel 1887               # all entries
    python -m rosenwald.postprocess.export_excel 1887 --women-only  # only women (is_woman=Y)

Output columns follow the project specification from Quantifying_the_invisible_support.docx.
If openpyxl is not installed, falls back to a UTF-8 CSV file.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from rosenwald.config import Settings


# Mapping: (master_tsv_column, final_excel_header)
COLUMN_MAP: List[Tuple[str, str]] = [
    ("full_name_raw",      "Nom / Prénom (brut)"),
    ("diploma_year",       "Date diplôme"),
    ("profession_section", "Profession"),
    ("specialties_raw",    "Spécialités"),
    ("address_raw",        "Adresse"),
    ("phone_raw",          "Téléphone"),
    ("hours_raw",          "Horaires consultation"),
    ("notes_raw",          "Remarques / Distinctions"),
    ("is_woman",           "Femme (Y/N)"),
    ("year",               "Année volume"),
    ("pdf_page",           "Page PDF"),
    ("list_type",          "Type de liste"),
    ("arrondissement",     "Arrondissement"),
    ("quartier",           "Quartier"),
    ("rue",                "Rue"),
    ("departement",        "Département"),
    ("canton",             "Canton"),
    ("specialite",         "Spécialité (section)"),
    ("station",            "Station thermale"),
    ("entry_raw",          "Entrée brute"),
]

EXCEL_HEADERS = [h for _, h in COLUMN_MAP]
TSV_KEYS      = [k for k, _ in COLUMN_MAP]


def export_to_excel(year: int, settings: Settings, women_only: bool = False) -> Path:
    merged_path = settings.merged_tsv_path(year)
    if not merged_path.exists():
        raise FileNotFoundError(
            f"Merged TSV not found: {merged_path}\n"
            f"Run women_filter.py {year} first."
        )

    rows: List[Dict[str, str]] = []
    with merged_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if women_only and row.get("is_woman") != "Y":
                continue
            rows.append(row)

    label = "women only" if women_only else "all entries"
    print(f"[INFO] Exporting {len(rows)} rows ({label}) for year {year}")

    out_path = settings.output_excel_path(year)
    if women_only:
        out_path = out_path.with_stem(out_path.stem + "_women_only")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"{year}"

        # Header row (bold)
        ws.append(EXCEL_HEADERS)
        for cell in ws[1]:
            cell.font = openpyxl.styles.Font(bold=True)

        # Data rows
        for row in rows:
            ws.append([row.get(k, "") for k in TSV_KEYS])

        # Auto-width (best-effort)
        for col in ws.columns:
            max_len = max((len(str(cell.value or "")) for cell in col), default=0)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

        wb.save(out_path)
        print(f"[OK] Saved Excel: {out_path}  ({len(rows)} rows)")

    except ImportError:
        # Fallback: UTF-8 CSV (Excel can open this)
        out_path = out_path.with_suffix(".csv")
        with out_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(EXCEL_HEADERS)
            for row in rows:
                writer.writerow([row.get(k, "") for k in TSV_KEYS])
        print(f"[OK] Saved CSV (openpyxl not installed): {out_path}  ({len(rows)} rows)")
        print("     Install openpyxl for proper .xlsx output:  pip install openpyxl")

    return out_path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m rosenwald.postprocess.export_excel YEAR [--women-only]")
        sys.exit(1)
    year = int(sys.argv[1])
    women_only = "--women-only" in sys.argv
    settings = Settings()
    export_to_excel(year, settings, women_only=women_only)


if __name__ == "__main__":
    main()
