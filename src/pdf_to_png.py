from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import fitz  # PyMuPDF
from PIL import Image


def render_pdf_page_to_png(
    pdf_path: Path,
    page_1indexed: int,
    out_path: Path,
    dpi: int = 300,
    rotate_deg: int = 0,
) -> None:
    """Render a single PDF page (1-indexed) to a PNG file.

    rotate_deg: counter-clockwise degrees to rotate the output image.
    Use rotate_deg=90 to correct landscape pages scanned sideways ("inversée").
    """
    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(page_1indexed - 1)  # 0-indexed internally
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        if rotate_deg:
            img = img.rotate(rotate_deg, expand=True)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, format="PNG")
    finally:
        doc.close()


def render_pages(pdf_path: Path, pages_1indexed: Iterable[int], out_dir: Path, dpi: int = 300) -> List[Path]:
    """Render multiple PDF pages to PNGs. Returns list of created paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for p in pages_1indexed:
        out_path = out_dir / f"page-{p:04d}.png"
        render_pdf_page_to_png(pdf_path, p, out_path, dpi=dpi)
        paths.append(out_path)
    return paths