from __future__ import annotations

import argparse

from rosenwald.config import Settings
from rosenwald.analysis import load, figures, tables


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--women-only", action="store_true",
                    help="only figures derived from Liste_femmes.xlsx (no tsv_clean needed)")
    args = ap.parse_args()

    s = Settings()
    fig_dir = s.data_dir / "output" / "figures"
    tab_dir = s.data_dir / "output" / "tables"

    women = load.load_women()
    print(f"[load] women: {len(women)} entries from {s.liste_femmes.name}")

    # women-only figures + tables (always)
    for name, fn in figures.WOMEN_ONLY.items():
        out = fn(women, fig_dir / f"{name}.png")
        print(f"  [fig] {out.relative_to(s.data_dir)}")
    tables.write_csv(tables.women_summary(women), tab_dir / "women_summary.csv")
    tables.write_csv(tables.women_by_year(women), tab_dir / "women_by_year.csv")
    tables.write_csv(tables.women_by_profession(women), tab_dir / "women_by_profession.csv")
    print("  [tab] women_summary.csv, women_by_year.csv, women_by_profession.csv")

    if args.women_only:
        print("[done] women-only mode")
        return

    corpus = load.load_corpus()
    if corpus.empty:
        print("[skip] corpus empty (data/tsv_clean absent) — ratio + coverage skipped")
        return
    print(f"[load] corpus: {len(corpus)} entries")
    figures.women_ratio_by_year(women, corpus, fig_dir / "women_ratio_by_year.png")
    tables.write_csv(tables.corpus_coverage(corpus), tab_dir / "corpus_coverage.csv")
    print("[done] full analysis")


if __name__ == "__main__":
    main()
