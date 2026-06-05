"""Tests for the ablation mode selector in run_year."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from rosenwald.extract import run_year as ry           # noqa: E402
from rosenwald.extract.prompts import PROMPTS, UNIFIED_PROMPT   # noqa: E402


def test_unified_ignores_routing_and_context():
    prompt, ctx = ry.select_prompt_and_context("unified", "deps_cantons", {"departement": "AUDE"})
    assert prompt is UNIFIED_PROMPT
    assert ctx is None


def test_routed_nogeo_keeps_prompt_drops_context():
    prompt, ctx = ry.select_prompt_and_context("routed-nogeo", "deps_cantons", {"departement": "AUDE"})
    assert prompt is PROMPTS["deps_cantons"]
    assert ctx is None


def test_routegeo_keeps_prompt_and_context():
    ctx_in = {"departement": "AUDE"}
    prompt, ctx = ry.select_prompt_and_context("routegeo", "deps_cantons", ctx_in)
    assert prompt is PROMPTS["deps_cantons"]
    assert ctx == ctx_in


def test_routegeo_empty_context_becomes_none():
    prompt, ctx = ry.select_prompt_and_context("routegeo", "paris_quartiers", {})
    assert ctx is None


def test_raw_root_name_per_mode():
    assert ry._raw_root_name("routegeo") == "tsv_raw"
    assert ry._raw_root_name("unified") == "tsv_raw_unified"
    assert ry._raw_root_name("routed-nogeo") == "tsv_raw_routed_nogeo"
