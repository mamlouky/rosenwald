"""
Project-wide settings.

All path logic is centralised here so every script uses the same
directory layout without hard-coded strings scattered through the code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    model:        str = "gemini-2.5-flash"
    dpi:          int = 300
    gcp_project:  str = "rosenwald"
    gcp_location: str = "us-central1"

    project_root: Path = field(default_factory=lambda: _PROJECT_ROOT)

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def excel_index(self) -> Path:
        return self.data_dir / "index" / "GR_index_listes_géographiques_final.xlsx"

    @property
    def liste_femmes(self) -> Path:
        
        ref = self.data_dir / "reference"
        corrected = ref / "Liste_femmes_corrige.xlsx"
        return corrected if corrected.exists() else ref / "Liste_femmes.xlsx"

    def pdf_path(self, year: int) -> Path:
        return self.data_dir / "pdfs" / f"{year}.pdf"

    def images_dir(self, year: int, list_type: str) -> Path:
        return self.data_dir / "images" / str(year) / list_type

    def tsv_raw_dir(self, year: int, list_type: str) -> Path:
        return self.data_dir / "tsv_raw" / str(year) / list_type

    def ocr_text_dir(self, year: int, list_type: str) -> Path:
        return self.data_dir / "ocr_text" / str(year) / list_type

    def merged_tsv_path(self, year: int) -> Path:
        return self.data_dir / "tsv_merged" / f"{year}_all.tsv"

    def output_excel_path(self, year: int) -> Path:
        return self.data_dir / "output" / f"{year}_women_doctors.xlsx"
