from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests


GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Human-readable labels for context fields injected into the prompt
_CONTEXT_LABELS: Dict[str, str] = {
    "arrondissement":   "arrondissement",
    "quartier":         "quartier",
    "departement":      "département",
    "canton":           "canton",
    "specialite":       "specialty section",
    "station":          "spa/station name",
    "rue":              "street/boulevard/avenue",
    "profession_section": "profession section (DOCTEURS / OFFICIERS_DE_SANTE / PHARMACIENS)",
}


def _b64_image(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def gemini_extract_tsv_from_image_http(
    image_path: Path,
    year: int,
    pdf_page: int,
    model: str,              # e.g. "models/gemini-2.5-flash"
    api_key: str,
    prompt_template: str,
    prev_context: Optional[Dict[str, str]] = None,
    timeout_s: int = 180,
) -> str:
    """
    Calls Gemini API generateContent via REST.

    prev_context: dict of {field_name: last_seen_value} from the previous page.
    These are injected into the prompt so Gemini can carry values forward
    when a page starts mid-section (no header visible).
    """
    url = f"{GEMINI_API_BASE}/{model}:generateContent"

    # Build the optional context section
    context_section = ""
    if prev_context:
        filled = {k: v for k, v in prev_context.items() if v}
        if filled:
            lines = [
                "CONTEXT FROM PREVIOUS PAGE",
                "(Carry these values forward in every row unless this page shows a new header that overrides them):",
            ]
            for key, val in filled.items():
                label = _CONTEXT_LABELS.get(key, key)
                lines.append(f"  - Last {label}: {val}")
            context_section = "\n".join(lines) + "\n\n"

    prompt = (
        prompt_template
        + "\n\n"
        + context_section
        + f"YEAR: {year}\nPDF_PAGE: {pdf_page}\n"
        + "Now extract the entries from the image."
    )

    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": _b64_image(image_path),
                        }
                    },
                    {"text": prompt},
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
        },
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }

    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(2):          # 1 attempt + 1 retry
        try:
            r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout_s)
        except requests.exceptions.Timeout:
            last_exc = RuntimeError(f"Gemini timed out after {timeout_s}s (attempt {attempt+1}/2)")
            if attempt == 0:
                time.sleep(10)
            continue

        if r.status_code == 429:      # rate-limit: wait and retry
            last_exc = RuntimeError(f"Gemini HTTP 429 rate-limit (attempt {attempt+1}/2)")
            if attempt == 0:
                time.sleep(30)
            continue

        if r.status_code != 200:
            raise RuntimeError(f"Gemini HTTP error {r.status_code}\n{r.text[:1500]}")

        data = r.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
            return "\n".join(t for t in texts if t).strip()
        except Exception:
            raise RuntimeError(f"Unexpected Gemini response:\n{json.dumps(data, ensure_ascii=False)[:2000]}")

    raise last_exc
