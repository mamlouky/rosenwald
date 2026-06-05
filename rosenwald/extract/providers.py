"""
A single entry point, `extract_tsv(...)`, routes a page to the chosen model so
`run_year` (and any benchmark script) can swap providers without touching the
extraction logic. Each provider keeps its own default model id, API-key
environment variable, and output-directory tag.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

from rosenwald.config import Settings
from rosenwald.extract.gemini import gemini_extract_tsv_from_image_http
from rosenwald.extract.anthropic_vlm import anthropic_extract_tsv_from_image
from rosenwald.extract.openai_vlm import openai_extract_tsv_from_image

PROVIDERS = ("gemini", "gemini-pro", "anthropic", "openai")

DEFAULT_MODEL: Dict[str, str] = {
    "gemini":     "gemini-2.5-flash",
    "gemini-pro": "gemini-2.5-pro",
    "anthropic":  "claude-sonnet-4-5",   
    "openai":     "gpt-4o",
}

KEY_ENV: Dict[str, str] = {
    "gemini":     "GOOGLE_API_KEY",
    "gemini-pro": "GOOGLE_API_KEY",
    "anthropic":  "ANTHROPIC_API_KEY",
    "openai":     "OPENAI_API_KEY",
}


def resolve_model(provider: str, override: str = "") -> str:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}. Choose from {PROVIDERS}.")
    return override or DEFAULT_MODEL[provider]


def api_key_for(provider: str) -> str:
    return os.getenv(KEY_ENV[provider], "").strip()


def provider_tag(provider: str) -> str:
    """Suffix used to keep each provider's raw output in its own directory."""
    return "" if provider == "gemini" else provider.replace("-", "_")


def extract_tsv(
    provider: str,
    *,
    settings: Settings,
    image_path: Path,
    year: int,
    pdf_page: int,
    model: str,
    api_key: str,
    prompt_template: str,
    prev_context: Optional[Dict[str, str]] = None,
) -> str:
    """Dispatch one page to the selected provider; returns TSV text."""
    if provider in ("gemini", "gemini-pro"):
        return gemini_extract_tsv_from_image_http(
            image_path=image_path, year=year, pdf_page=pdf_page,
            model=model, api_key=api_key, prompt_template=prompt_template,
            prev_context=prev_context,
            gcp_project=settings.gcp_project, gcp_location=settings.gcp_location,
        )
    if provider == "anthropic":
        return anthropic_extract_tsv_from_image(
            image_path, year, pdf_page, model=model, api_key=api_key,
            prompt_template=prompt_template, prev_context=prev_context,
        )
    if provider == "openai":
        return openai_extract_tsv_from_image(
            image_path, year, pdf_page, model=model, api_key=api_key,
            prompt_template=prompt_template, prev_context=prev_context,
        )
    raise ValueError(f"Unknown provider {provider!r}. Choose from {PROVIDERS}.")
