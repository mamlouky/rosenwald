"""
Shared helpers for the multimodal extractors.

Every provider (Gemini, Claude, GPT, …) must build the *exact same* prompt from
the same template, page metadata and carried-forward context, otherwise the
model benchmark would not be comparing like with like. That assembly lives
here so all adapters share it.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Dict, Optional

# Human-readable labels for context fields injected into the prompt
# (kept identical to extract/gemini.py).
CONTEXT_LABELS: Dict[str, str] = {
    "arrondissement":     "arrondissement",
    "quartier":           "quartier",
    "departement":        "département",
    "canton":             "canton",
    "specialite":         "specialty section",
    "station":            "spa/station name",
    "rue":                "street/boulevard/avenue",
    "profession_section": "profession section (DOCTEURS / OFFICIERS_DE_SANTE / PHARMACIENS)",
}


def b64_image(path: Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("utf-8")


def build_prompt(
    prompt_template: str,
    year: int,
    pdf_page: int,
    prev_context: Optional[Dict[str, str]] = None,
) -> str:
    """Assemble the final prompt (template + carried context + page metadata)."""
    context_section = ""
    if prev_context:
        filled = {k: v for k, v in prev_context.items() if v}
        if filled:
            lines = [
                "CONTEXT FROM PREVIOUS PAGE",
                "(Carry these values forward in every row unless this page shows a new header that overrides them):",
            ]
            for key, val in filled.items():
                lines.append(f"  - Last {CONTEXT_LABELS.get(key, key)}: {val}")
            context_section = "\n".join(lines) + "\n\n"

    return (
        prompt_template
        + "\n\n"
        + context_section
        + f"YEAR: {year}\nPDF_PAGE: {pdf_page}\n"
        + "Now extract the entries from the image."
    )
