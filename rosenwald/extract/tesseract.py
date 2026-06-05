"""
Classic OCR extraction using Tesseract.

Provides a single function: ocr_image(image_path, lang, two_columns) -> str

Two-column pages (the majority in this project) are split vertically at the
midpoint before OCR so that Tesseract never mixes lines across columns.
The left-column text is returned first, followed by the right-column text,
separated by a blank line.
"""
from __future__ import annotations

from pathlib import Path

import pytesseract
from PIL import Image

# Tesseract config: PSM 6 = assume a single uniform block of text.
# Used on each half after the image is split, so no multi-column confusion.
_TSS_CONFIG = r"--psm 6"


def ocr_image(image_path: Path, lang: str = "fra", two_columns: bool = True) -> str:
    """
    Run Tesseract OCR on a PNG image and return the extracted text.

    lang        : Tesseract language code.
                  "fra"     = French (requires tesseract-ocr-fra language pack).
                  "fra+lat" = French + Latin.
    two_columns : If True (default), split the image vertically at the midpoint
                  and OCR each half independently, then concatenate.
                  Set to False for single-column pages (e.g. prefecture_seine).
    """
    img = Image.open(image_path)

    if two_columns:
        mid = img.width // 2
        left  = img.crop((0,    0, mid,       img.height))
        right = img.crop((mid,  0, img.width, img.height))
        text_left  = pytesseract.image_to_string(left,  lang=lang, config=_TSS_CONFIG)
        text_right = pytesseract.image_to_string(right, lang=lang, config=_TSS_CONFIG)
        return text_left.rstrip() + "\n\n" + text_right.rstrip()
    else:
        return pytesseract.image_to_string(img, lang=lang, config=_TSS_CONFIG)
