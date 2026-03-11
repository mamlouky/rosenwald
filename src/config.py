"""
Project-wide settings.

All path logic is centralised here so every script uses the same
directory layout without hard-coded strings scattered through the code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# Project root = one directory above src/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    # ── Model ──────────────────────────────────────────────────────────────
    model: str = "models/gemini-2.5-flash"
    dpi:   int = 300

    # ── Root paths ─────────────────────────────────────────────────────────
    project_root: Path = field(default_factory=lambda: _PROJECT_ROOT)

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def excel_index(self) -> Path:
        return self.project_root / "GR_index_listes_géographiques_final.xlsx"

    # ── Per-year input ──────────────────────────────────────────────────────
    def pdf_path(self, year: int) -> Path:
        return self.data_dir / "pdfs" / f"{year}.pdf"

    # ── Per-year / per-section outputs ──────────────────────────────────────
    def images_dir(self, year: int, list_type: str) -> Path:
        return self.data_dir / "images" / str(year) / list_type

    def tsv_raw_dir(self, year: int, list_type: str) -> Path:
        return self.data_dir / "tsv_raw" / str(year) / list_type

    def merged_tsv_path(self, year: int) -> Path:
        return self.data_dir / "tsv_merged" / f"{year}_all.tsv"

    def output_excel_path(self, year: int) -> Path:
        return self.data_dir / "output" / f"{year}_women_doctors.xlsx"
