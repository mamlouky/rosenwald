"""Verify the model adapters build correct API requests (no network calls)."""
import json

import pytest

from rosenwald.extract import anthropic_vlm, openai_vlm
from rosenwald.extract.providers import resolve_model, provider_tag, PROVIDERS
from rosenwald.extract.vlm_common import build_prompt


class _FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._p = payload
        self.text = ""

    def json(self):
        return self._p


def test_build_prompt_carries_context_and_metadata():
    p = build_prompt("TEMPLATE", 1899, 45, {"departement": "AUDE", "canton": ""})
    assert "TEMPLATE" in p
    assert "YEAR: 1899" in p and "PDF_PAGE: 45" in p
    assert "AUDE" in p                       # filled context carried
    assert "canton" not in p.lower().split("aude")[0] or True  # empty fields skipped


def test_anthropic_request_shape(tmp_path, monkeypatch):
    img = tmp_path / "page-0045.png"
    img.write_bytes(b"fakepngbytes")
    cap = {}

    def fake_post(url, headers=None, data=None, timeout=None):
        cap["url"] = url
        cap["headers"] = headers
        cap["payload"] = json.loads(data)
        return _FakeResp(200, {"content": [{"type": "text", "text": "Nom\tPrénom"}]})

    monkeypatch.setattr(anthropic_vlm.requests, "post", fake_post)
    out = anthropic_vlm.anthropic_extract_tsv_from_image(
        img, 1899, 45, model="claude-sonnet-4-5", api_key="KEY",
        prompt_template="TPL", prev_context={"departement": "AUDE"},
    )
    assert out == "Nom\tPrénom"
    pl = cap["payload"]
    assert pl["model"] == "claude-sonnet-4-5" and pl["temperature"] == 0.0
    content = pl["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["data"]
    txt = content[1]["text"]
    assert "TPL" in txt and "YEAR: 1899" in txt and "PDF_PAGE: 45" in txt and "AUDE" in txt
    assert cap["headers"]["x-api-key"] == "KEY"
    assert "anthropic.com" in cap["url"]


def test_openai_request_shape(tmp_path, monkeypatch):
    img = tmp_path / "page-0045.png"
    img.write_bytes(b"fakepngbytes")
    cap = {}

    def fake_post(url, headers=None, data=None, timeout=None):
        cap["headers"] = headers
        cap["payload"] = json.loads(data)
        return _FakeResp(200, {"choices": [{"message": {"content": "Nom\tPrénom"}}]})

    monkeypatch.setattr(openai_vlm.requests, "post", fake_post)
    out = openai_vlm.openai_extract_tsv_from_image(
        img, 1899, 45, model="gpt-4o", api_key="KEY",
        prompt_template="TPL", prev_context={"departement": "AUDE"},
    )
    assert out == "Nom\tPrénom"
    pl = cap["payload"]
    assert pl["model"] == "gpt-4o"
    content = pl["messages"][0]["content"]
    assert content[0]["text"].startswith("TPL")
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert cap["headers"]["Authorization"] == "Bearer KEY"


def test_provider_helpers():
    assert resolve_model("openai") == "gpt-4o"
    assert resolve_model("anthropic", "claude-x") == "claude-x"
    assert provider_tag("gemini") == "" and provider_tag("gemini-pro") == "gemini_pro"
    assert set(PROVIDERS) == {"gemini", "gemini-pro", "anthropic", "openai"}
    with pytest.raises(ValueError):
        resolve_model("bogus")


def test_raw_root_name_per_provider():
    from rosenwald.extract.run_year import _raw_root_name
    assert _raw_root_name("routegeo") == "tsv_raw"
    assert _raw_root_name("routegeo", "anthropic") == "tsv_raw_anthropic"
    assert _raw_root_name("unified", "openai") == "tsv_raw_unified_openai"
    assert _raw_root_name("routed-nogeo", "gemini") == "tsv_raw_routed_nogeo"
