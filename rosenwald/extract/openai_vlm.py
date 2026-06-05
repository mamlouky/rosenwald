"""
GPT (OpenAI) multimodal extractor — same interface as gemini.py.

Used for the §4.7 model benchmark. Requires OPENAI_API_KEY in the environment.
Sends the page image + the assembled RouteGeo prompt and returns the TSV text.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from rosenwald.extract.vlm_common import b64_image, build_prompt

API_URL = "https://api.openai.com/v1/chat/completions"


def openai_extract_tsv_from_image(
    image_path: Path,
    year: int,
    pdf_page: int,
    *,
    model: str,                       # e.g. "gpt-4o"
    api_key: str,                     # OPENAI_API_KEY
    prompt_template: str,
    prev_context: Optional[Dict[str, str]] = None,
    timeout_s: int = 180,
    max_tokens: int = 8192,
) -> str:
    prompt = build_prompt(prompt_template, year, pdf_page, prev_context)
    data_url = "data:image/png;base64," + b64_image(image_path)
    payload: Dict[str, Any] = {
        "model": model,
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(4):
        try:
            r = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=timeout_s)
        except requests.exceptions.Timeout:
            last_exc = RuntimeError(f"GPT timed out after {timeout_s}s (attempt {attempt+1}/4)")
            time.sleep(10)
            continue
        if r.status_code == 429:
            last_exc = RuntimeError(f"GPT HTTP 429 rate-limit (attempt {attempt+1}/4)")
            time.sleep(30 * (attempt + 1))
            continue
        if r.status_code != 200:
            raise RuntimeError(f"GPT HTTP error {r.status_code}\n{r.text[:1500]}")
        data = r.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except Exception:
            raise RuntimeError(f"Unexpected GPT response:\n{json.dumps(data, ensure_ascii=False)[:2000]}")
    raise last_exc
