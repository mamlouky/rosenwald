"""
Step 2 of the pipeline: merge all per-page TSVs for a year into one file
and annotate each entry with is_woman=Y/N based on:
  - civil_status field (Mme, Mlle, etc.)
  - keywords in full_name_raw
  - feminine first names from the Excel list

Usage:
    python -m rosenwald.women.filter 1887
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Dict, List, Set

from rosenwald.config import Settings
from rosenwald.index_reader import read_feminine_first_names


# Civil-status keywords that identify women
CIVIL_STATUS_KEYWORDS = {
    "mme", "mme.", "mme vve", "madame", "mad.",
    "mlle", "mlle.", "melle", "mademoiselle",
    "dame", "veuve", "nee", "née",
}

# TSV column schemas per list_type

SCHEMA: Dict[str, List[str]] = {
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
# Reuse schemas for list types that share the same prompt/format
SCHEMA["seine_cantons"]    = SCHEMA["deps_cantons"]
SCHEMA["bienfaisance"]     = SCHEMA["specialists"]
SCHEMA["prefecture_seine"] = SCHEMA["specialists"]

# Forward-fill fields per list_type
# Safety net: if Gemini left a geographic field blank because the header
# was on the previous page, we propagate the last seen value.
FFILL_FIELDS: Dict[str, List[str]] = {
    "paris_quartiers":  ["arrondissement", "quartier", "profession_section"],
    "deps_cantons":     ["departement", "arrondissement", "canton", "profession_section"],
    "seine_cantons":    ["departement", "arrondissement", "canton", "profession_section"],
    "specialists":      ["specialite"],
    "thermal_spas":     ["station"],
    "paris_rues":       ["rue", "arrondissement", "profession_section"],
    "bienfaisance":     ["specialite"],
    "prefecture_seine": ["specialite"],
}

# Unified output columns (master schema)
MASTER_COLUMNS = [
    "year", "pdf_page", "list_type",
    # geographic context (filled depending on list type)
    "arrondissement", "quartier",
    "departement", "canton",
    "specialite", "station", "rue",
    # person fields
    "profession_section",
    "full_name_raw", "diploma_year",
    "address_raw", "phone_raw", "hours_raw", "specialties_raw",
    "gender_marker_raw", "maiden_name_raw",
    "notes_raw", "entry_raw",
    # derived
    "is_woman",
]


# Women detection
def _detect_woman(row: Dict[str, str], fem_names: Set[str]) -> str:
    """Return 'Y' if the entry is likely a woman, else ''."""

    # 1. Check the dedicated gender_marker_raw field (extracted by LLM)
    gm = row.get("gender_marker_raw", "").strip().lower()
    if gm:
        for kw in CIVIL_STATUS_KEYWORDS:
            if kw in gm:
                return "Y"

    # 2. Check full_name_raw for civil-status keywords at the start or inline
    name_raw = row.get("full_name_raw", "").strip().lower()
    for kw in CIVIL_STATUS_KEYWORDS:
        if name_raw.startswith(kw + " ") or name_raw.startswith(kw + "."):
            return "Y"
        if f" {kw} " in name_raw:
            return "Y"

    # 3. Check each word of the name against the feminine first-names list
    name_original = row.get("full_name_raw", "").strip()
    # Strip common male prefixes that may precede the actual name
    for prefix in ("Dr ", "Dr. ", "M. ", "M ", "Pr. ", "Pr ", "Prof. "):
        if name_original.startswith(prefix):
            name_original = name_original[len(prefix):]
    for word in name_original.split():
        candidate = word.strip(".,()-").capitalize()
        if candidate in fem_names:
            return "Y"

    return ""


# Main merge + annotate function
def merge_and_annotate(year: int, settings: Settings) -> Path:
    fem_names = read_feminine_first_names(settings.excel_index)
    rows: List[Dict[str, str]] = []

    tsv_base = settings.data_dir / "tsv_raw" / str(year)
    if not tsv_base.exists():
        raise FileNotFoundError(
            f"No TSV output found for year {year} at {tsv_base}.\n"
            f"Run run_year.py {year} first."
        )

    # Walk each list_type subdirectory in sorted order
    for list_type_dir in sorted(tsv_base.iterdir()):
        if not list_type_dir.is_dir():
            continue

        list_type = list_type_dir.name
        schema = SCHEMA.get(list_type)
        if schema is None:
            print(f"[WARN] Unknown list_type '{list_type}' — skipping directory")
            continue

        tsv_files = sorted(list_type_dir.glob("page-*.tsv"))
        if not tsv_files:
            continue

        print(f"  Merging {len(tsv_files):3d} TSV files from {list_type}/")

        for tsv_file in tsv_files:
            content = tsv_file.read_text(encoding="utf-8", errors="ignore").strip()
            if not content:
                continue

            for line in content.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")

                # Build row dict from schema
                # Treat \N / NULL (Gemini null placeholder) as empty string
                raw: Dict[str, str] = {}
                for i, col in enumerate(schema):
                    val = parts[i].strip() if i < len(parts) else ""
                    raw[col] = "" if val in (r"\N", "NULL", "null") else val

                # Infer profession_section from name prefix if blank
                # (small cantons often have no explicit section header)
                if not raw.get("profession_section"):
                    name_lc = raw.get("full_name_raw", "").lstrip().lower()
                    if name_lc.startswith("drs ") or name_lc.startswith("dr ") or name_lc.startswith("dr."):
                        raw["profession_section"] = "DOCTEURS"
                    elif name_lc.startswith("off."):
                        raw["profession_section"] = "OFFICIERS_DE_SANTE"
                    elif name_lc.startswith("ph."):
                        raw["profession_section"] = "PHARMACIENS"

                # Build master row (all columns, defaulting to "")
                row: Dict[str, str] = {col: "" for col in MASTER_COLUMNS}
                row.update(raw)
                row["list_type"] = list_type
                row["is_woman"]  = _detect_woman(raw, fem_names)
                rows.append(row)

    if not rows:
        print(f"[WARN] No entries found for year {year}. Nothing to write.")
        return settings.merged_tsv_path(year)


    last_vals: Dict[str, str] = {}
    last_list_type: str = ""
    for row in rows:
        lt = row["list_type"]
        if lt != last_list_type:
            last_vals = {}          # reset carry-forward at every list_type boundary
            last_list_type = lt
        for field in FFILL_FIELDS.get(lt, []):
            if row[field]:
                last_vals[field] = row[field]   # update with fresh value
            elif field in last_vals:
                row[field] = last_vals[field]   # fill blank from last known

    # Write merged TSV
    out_path = settings.merged_tsv_path(year)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MASTER_COLUMNS, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    women = sum(1 for r in rows if r["is_woman"] == "Y")
    print(f"\n[OK] {len(rows)} entries merged for year {year}")
    print(f"[OK] Women detected (is_woman=Y): {women}")
    print(f"[OK] Saved: {out_path}")
    return out_path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m rosenwald.women.filter YEAR")
        sys.exit(1)
    year = int(sys.argv[1])
    settings = Settings()
    merge_and_annotate(year, settings)


if __name__ == "__main__":
    main()
