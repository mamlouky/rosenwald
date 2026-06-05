from __future__ import annotations

from pathlib import Path

import pandas as pd


def women_summary(women: pd.DataFrame) -> pd.DataFrame:
    """Women counts per list type + per-year span."""
    g = women.groupby("list_type").agg(
        femmes=("nom", "size"),
        annee_min=("annee_volume", "min"),
        annee_max=("annee_volume", "max"),
    ).reset_index().sort_values("femmes", ascending=False)
    return g


def women_by_year(women: pd.DataFrame) -> pd.DataFrame:
    return (women.dropna(subset=["annee_volume"])
            .groupby("annee_volume").size().rename("femmes").reset_index())


def women_by_profession(women: pd.DataFrame) -> pd.DataFrame:
    """Entries and distinct women per profession category (docteur / pharmacien /
    officier de santé / sage-femme). Pharmacists and officiers de santé are not
    doctors, so they are reported separately."""
    key = women["nom"].str.strip().str.lower() + "|" + women["prenom"].str.strip().str.lower()
    g = (women.assign(_k=key).groupby("profession_cat")
         .agg(entrees=("nom", "size"),
              distinctes=("_k", "nunique"),
              diplome_min=("annee_diplome", "min"),
              diplome_max=("annee_diplome", "max"))
         .reset_index().sort_values("distinctes", ascending=False))
    return g


def corpus_coverage(corpus: pd.DataFrame) -> pd.DataFrame:
    """Entries per year x list type."""
    if corpus.empty:
        return pd.DataFrame()
    return (corpus.groupby(["year", "list_type"]).size()
            .rename("entries").reset_index())


def write_csv(df: pd.DataFrame, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8-sig")
    return out
