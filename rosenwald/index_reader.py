"""
Reads the Excel index (GR_index_listes_géographiques_final.xlsx) to get
page ranges and list types for each year, plus the feminine first-names list.
"""
from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set

EXCEL_PATH = Path("GR_index_listes_géographiques_final.xlsx")


@dataclass
class ListSection:
    year: int
    page_start: int
    page_end: int
    list_type: str   # see _classify() below
    list_name: str   # raw name from Excel
    localisation: str
    notes: str = ""  # raw notes from column 6 

    @property
    def pages(self) -> range:
        return range(self.page_start, self.page_end + 1)

    @property
    def num_pages(self) -> int:
        return self.page_end - self.page_start + 1

    @property
    def is_rotated(self) -> bool:
        """True when the Excel notes the page as landscape/inverted (needs 90° rotation)."""
        return "invers" in self.notes.lower()


def _classify(list_name: str, localisation: str) -> str:
    """Map a raw list name to one of the known list_type keys."""
    n = list_name.lower()
    loc = localisation.lower()

    # Order matters: most specific checks first
    if "par rues" in n:
        return "paris_rues"
    if "par quartiers" in n:
        return "paris_quartiers"
    if "préfecture" in n or "prefecture" in n:
        return "prefecture_seine"
    if "bienfaisance" in n:
        return "bienfaisance"
    if "thermales" in n or "eaux thermales" in n:
        return "thermal_spas"
    if "spécialistes" in n or "specialistes" in n:
        return "specialists"
    # Seine-specific canton lists (distinct from main depts)
    if "seine" in n and "cantons" in n:
        return "seine_cantons"
    if "seine" in loc and ("cantons" in n or "par cantons" in n):
        return "seine_cantons"
    # Main departments + colonies canton lists
    if "cantons" in n or "par cantons" in n:
        return "deps_cantons"
    # Remaining Seine references
    if "seine" in n:
        return "seine_cantons"
    return "unknown"


# Internal XML helpers
def _read_shared_strings(z: zipfile.ZipFile) -> List[str]:
    strings: List[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        with z.open("xl/sharedStrings.xml") as f:
            root = ET.parse(f).getroot()
            ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
            for si in root.findall(f"{{{ns}}}si"):
                parts = [t.text for t in si.iter(f"{{{ns}}}t") if t.text]
                strings.append("".join(parts))
    return strings


def _parse_sheet(z: zipfile.ZipFile, sheet_path: str, strings: List[str]) -> List[List[str]]:
    rows: List[List[str]] = []
    with z.open(sheet_path) as f:
        root = ET.parse(f).getroot()
        ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        for row in root.findall(f".//{{{ns}}}row"):
            cells: List[str] = []
            for c in row.findall(f"{{{ns}}}c"):
                t = c.get("t", "")
                v = c.find(f"{{{ns}}}v")
                val = ""
                if v is not None and v.text:
                    val = strings[int(v.text)] if t == "s" else v.text
                cells.append(val)
            rows.append(cells)
    return rows


# Public API
def read_index(excel_path: Path = EXCEL_PATH) -> List[ListSection]:
    """Return all list sections across all years from the Excel index."""
    sections: List[ListSection] = []
    with zipfile.ZipFile(excel_path) as z:
        strings = _read_shared_strings(z)
        rows = _parse_sheet(z, "xl/worksheets/sheet1.xml", strings)

    for cells in rows:
        if not cells or not cells[0] or cells[0] == "year":
            continue

        year_raw        = cells[0]
        page_start_raw  = cells[1] if len(cells) > 1 else ""
        page_end_raw    = cells[2] if len(cells) > 2 else ""
        list_name       = cells[3] if len(cells) > 3 else ""
        localisation    = cells[4] if len(cells) > 4 else ""
        notes           = cells[5] if len(cells) > 5 else ""

        if not list_name:
            continue
        if "manquant" in str(page_start_raw).lower() or not page_start_raw.strip():
            continue

        try:
            year       = int(float(year_raw))
            page_start = int(float(page_start_raw))
            page_end   = int(float(page_end_raw)) if page_end_raw and page_end_raw.strip() else page_start
        except (ValueError, TypeError):
            continue

        list_type = _classify(list_name, localisation)
        sections.append(ListSection(
            year=year,
            page_start=page_start,
            page_end=page_end,
            list_type=list_type,
            list_name=list_name,
            localisation=localisation,
            notes=notes,
        ))

    return sections


def read_sections_for_year(year: int, excel_path: Path = EXCEL_PATH) -> List[ListSection]:
    """Return all list sections for a given year."""
    return [s for s in read_index(excel_path) if s.year == year]


def read_feminine_first_names(excel_path: Path = EXCEL_PATH) -> Set[str]:
    """Return the set of feminine first names from Sheet3 of the Excel."""
    names: Set[str] = set()
    with zipfile.ZipFile(excel_path) as z:
        strings = _read_shared_strings(z)
        rows = _parse_sheet(z, "xl/worksheets/sheet3.xml", strings)

    for cells in rows:
        for val in cells:
            name = val.strip()
            if name and name.lower() not in ("prénoms féminins", "prenoms feminins", ""):
                names.add(name)
    return names
