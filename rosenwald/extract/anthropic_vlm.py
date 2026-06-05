"""
Claude (Anthropic) multimodal extractor — same interface as gemini.py.

Requires ANTHROPIC_API_KEY in the
environment. Sends the page image + the assembled RouteGeo prompt and returns
the model's TSV text.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from rosenwald.extract.vlm_common import b64_image, build_prompt

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


def anthropic_extract_tsv_from_image(
    image_path: Path,
    year: int,
    pdf_page: int,
    *,
    model: str,                      
    api_key: str,                     
    prompt_template: str,
    prev_context: Optional[Dict[str, str]] = None,
    timeout_s: int = 180,
    max_tokens: int = 8192,
) -> str:
    prompt = build_prompt(prompt_template, year, pdf_page, prev_context)
    payload: Dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64_image(image_path),
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }

    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(4):
        try:
            r = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=timeout_s)
        except requests.exceptions.Timeout:
            last_exc = RuntimeError(f"Claude timed out after {timeout_s}s (attempt {attempt+1}/4)")
            time.sleep(10)
            continue
        if r.status_code == 429:
            last_exc = RuntimeError(f"Claude HTTP 429 rate-limit (attempt {attempt+1}/4)")
            time.sleep(30 * (attempt + 1))
            continue
        if r.status_code != 200:
            raise RuntimeError(f"Claude HTTP error {r.status_code}\n{r.text[:1500]}")
        data = r.json()
        try:
            blocks = data["content"]
            return "\n".join(b["text"] for b in blocks if b.get("type") == "text").strip()
        except Exception:
            raise RuntimeError(f"Unexpected Claude response:\n{json.dumps(data, ensure_ascii=False)[:2000]}")
    raise last_exc
