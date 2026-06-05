"""Tests for the evaluation harness."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from rosenwald.evaluation import evaluate as ev   # noqa: E402


def test_wer_cer_identical_is_zero():
    w, c = ev.wer_cer("bénard 1865 censier 28", "bénard 1865 censier 28")
    assert w == 0.0 and c == 0.0


def test_wer_one_substitution():
    # 1 word wrong out of 4 -> WER 0.25
    w, _ = ev.wer_cer("bénard 1866 censier 28", "bénard 1865 censier 28")
    assert abs(w - 0.25) < 1e-9


def test_empty_reference_handling():
    assert ev.wer_cer("", "") == (0.0, 0.0)
    assert ev.wer_cer("x", "") == (1.0, 1.0)


def test_aggregate_median_and_avg():
    res = ev.aggregate([(0.0, 0.0), (0.2, 0.1), (0.4, 0.3)])
    assert abs(res["avg_wer"] - 0.2) < 1e-9
    assert abs(res["mid_wer"] - 0.2) < 1e-9
    assert res["n"] == 3


def test_score_tsv_dirs(tmp_path):
    gold = tmp_path / "gold" / "1887" / "paris_quartiers"
    pred = tmp_path / "pred" / "1887" / "paris_quartiers"
    gold.mkdir(parents=True); pred.mkdir(parents=True)
    (gold / "page-0001.tsv").write_text("Bénard\t1865\tCensier 28\n", encoding="utf-8")
    (pred / "page-0001.tsv").write_text("Bénard\t1865\tCensier 28\n", encoding="utf-8")
    r = ev.score_tsv_dirs(tmp_path / "gold", tmp_path / "pred")
    assert r["matched_pages"] == 1
    assert r["avg_wer"] == 0.0


def test_markdown_and_latex_render():
    rows = [["A", "B"], ["1", "2"]]
    md = ev.to_markdown(rows)
    assert "| A | B |" in md and "| 1 | 2 |" in md
    tex = ev.to_latex(rows, caption="cap", label="lab")
    assert r"\begin{tabular}" in tex and r"\caption{cap}" in tex
