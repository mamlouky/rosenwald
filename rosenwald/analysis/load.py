from __future__ import annotations

from pathlib import Path
from typing import Optional

import re
import unicodedata

import pandas as pd

from rosenwald.config import Settings

# ─────────────────────────────────────────────────────────────────────────────
# tsv_clean schema per list_type (the cleaned, restructured output)
# ─────────────────────────────────────────────────────────────────────────────
SCHEMA: dict[str, list[str]] = {
    "paris_quartiers": ["arrondissement", "quartier", "profession", "nom", "annee", "notes", "adresse", "horaires", "sexe", "year", "page"],
    "paris_rues":      ["rue", "nom", "annee", "notes", "adresse", "horaires", "sexe", "year", "page"],
    "deps_cantons":    ["departement", "arrondissement_dept", "canton", "profession", "nom", "annee", "notes", "adresse", "horaires", "sexe", "year", "page"],
    "seine_cantons":   ["departement", "arrondissement_dept", "canton", "profession", "nom", "annee", "notes", "adresse", "horaires", "sexe", "year", "page"],
    "specialists":     ["specialite", "nom", "annee", "notes", "adresse", "horaires", "sexe", "year", "page"],
    "thermal_spas":    ["station", "nom", "annee", "notes", "adresse", "horaires", "sexe", "year", "page"],
    "bienfaisance":    ["institution", "arrondissement", "nom", "year", "page"],
    "prefecture_seine": ["categorie", "nom", "year", "page"],
}


def _load_tsv_dir(lt_dir: Path, cols: list[str], year_from_dir: int) -> pd.DataFrame:
    frames = []
    for tsv in sorted(lt_dir.glob("*.tsv")):
        try:
            df = pd.read_csv(tsv, sep="\t", header=None, dtype=str, names=cols,
                             on_bad_lines="skip", encoding="utf-8", engine="python")
            for c in cols:
                if c not in df.columns:
                    df[c] = ""
            df = df[cols].copy()
            df["year"] = str(year_from_dir)   # dir name is authoritative
            df["_page_file"] = tsv.name
            frames.append(df)
        except Exception:
            pass
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols)


def load_corpus(tsv_clean_root: Optional[Path] = None) -> pd.DataFrame:
    """Load all cleaned per-page TSVs (every practitioner, every list)."""
    root = Path(tsv_clean_root) if tsv_clean_root else Settings().data_dir / "tsv_clean"
    frames = []
    for year_dir in sorted(root.iterdir()) if root.exists() else []:
        if not year_dir.is_dir():
            continue
        try:
            year = int(year_dir.name)
        except ValueError:
            continue
        for lt_dir in sorted(year_dir.iterdir()):
            if not lt_dir.is_dir():
                continue
            cols = SCHEMA.get(lt_dir.name)
            if not cols:
                continue
            df = _load_tsv_dir(lt_dir, cols, year)
            if not df.empty:
                df["list_type"] = lt_dir.name
                frames.append(df)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["year"])
    df = df[df["year"] >= 1887].fillna("")
    return df


load_all = load_corpus

_SHEET_TO_LT = {
    "paris_quartiers": "paris_quartiers", "deps_cantons": "deps_cantons",
    "paris_rues": "paris_rues", "seine_cantons": "seine_cantons",
    "specialistes": "specialists", "stations_thermales": "thermal_spas",
    "bienfaisance": "bienfaisance",
}

# Normalised field -> ordered list of header-substring matchers.
# Order matters: more specific keys are tested first to avoid collisions
# (e.g. "prénom" before "nom", which is a substring of "prénom").
_FIELD_MATCHERS = [
    ("prenom",        lambda h: h.startswith("prénom") or h.startswith("prenom")),
    ("nom",           lambda h: h.startswith("nom")),
    ("etat_civil",    lambda h: "civil" in h or "indicateur" in h),
    ("detection",     lambda h: "indication" in h or "preuve" in h),
    ("annee_diplome", lambda h: "diplôme" in h or "diplome" in h),
    ("profession",    lambda h: "profession" in h),
    ("departement",   lambda h: "département" in h or "departement" in h),
    ("arrondissement", lambda h: "arrondissement" in h),
    ("canton",        lambda h: "canton" in h),
    ("quartier",      lambda h: "quartier" in h),
    ("rue",           lambda h: h.startswith("rue")),
    ("specialite",    lambda h: "spécialité" in h or "specialite" in h),
    ("station",       lambda h: "station" in h),
    ("adresse",       lambda h: "adresse" in h),
    ("horaires",      lambda h: "horaires" in h),
    ("annee_volume",  lambda h: "année du volume" in h or h.strip() in ("année", "annee")),
    ("page",          lambda h: "page" in h),
    ("raw_text",      lambda h: "brute" in h or "raw_text" in h),
]

WOMEN_COLUMNS = [
    "list_type", "nom", "prenom", "etat_civil", "detection", "annee_diplome",
    "profession", "departement", "arrondissement", "canton", "quartier", "rue",
    "specialite", "station", "adresse", "horaires", "annee_volume", "page", "raw_text",
]


def _profession_cat(profession: str, raw_text: str, list_type: str) -> str:
    """Classify each entry as docteur / pharmacien / officier de santé.

    Pharmacists and officiers de santé are NOT doctors, so they are kept apart. Prefer the
    explicit Profession column; otherwise infer from the raw printed line. The
    geographic/specialist lists are physician lists, hence 'docteur' by default.
    Midwives are not categorised separately (the printed 'Accouch.' cue is
    ambiguous between accoucheuse and an obstetrician doctor).
    """
    s = unicodedata.normalize("NFKD", str(profession)).encode("ascii", "ignore").decode().lower()
    if "pharm" in s:
        return "pharmacien"
    if "officier" in s:
        return "officier de santé"
    if "docteur" in s:
        return "docteur"
    t = unicodedata.normalize("NFKD", str(raw_text)).encode("ascii", "ignore").decode().lower()
    if re.search(r"\bph\.|pharm", t):
        return "pharmacien"
    if re.search(r"\boff\.|officier", t):
        return "officier de santé"
    if list_type == "bienfaisance":
        return "non précisé"
    return "docteur"


def _normalise_header(h: str) -> Optional[str]:
    low = str(h).lower().strip()
    for field, match in _FIELD_MATCHERS:
        if match(low):
            return field
    return None


def load_women(liste_femmes_path: Optional[Path] = None) -> pd.DataFrame:
    """Load every sheet of the verified women workbook into one long DataFrame."""
    path = Path(liste_femmes_path) if liste_femmes_path else Settings().liste_femmes
    book = pd.read_excel(path, sheet_name=None, dtype=str)
    frames = []
    for sheet, df in book.items():
        if sheet not in _SHEET_TO_LT:
            continue          # skip non-data sheets 
        lt = _SHEET_TO_LT[sheet]
        rename, seen = {}, set()
        for col in df.columns:
            field = _normalise_header(col)
            if field and field not in seen:
                rename[col] = field
                seen.add(field)
        sub = df.rename(columns=rename)
        sub = sub[[c for c in rename.values()]].copy()
        sub["list_type"] = lt
        if "etat_civil" not in sub.columns and "detection" in sub.columns:
            sub["etat_civil"] = sub["detection"]
        for c in WOMEN_COLUMNS:
            if c not in sub.columns:
                sub[c] = ""
        frames.append(sub[WOMEN_COLUMNS])
    if not frames:
        return pd.DataFrame(columns=WOMEN_COLUMNS)
    out = pd.concat(frames, ignore_index=True).fillna("")
    out["annee_volume"] = pd.to_numeric(out["annee_volume"], errors="coerce").astype("Int64")
    out["annee_diplome"] = pd.to_numeric(out["annee_diplome"], errors="coerce").astype("Int64")
    out["profession_cat"] = [
        _profession_cat(p, r, lt)
        for p, r, lt in zip(out["profession"], out["raw_text"], out["list_type"])
    ]
    return out


def load_raw(raw_root: Optional[Path] = None) -> pd.DataFrame:
    """Load tsv_raw entry_raw for cross-verification of diploma years (optional)."""
    root = Path(raw_root) if raw_root else Settings().data_dir / "tsv_raw"
    frames = []
    for year_dir in sorted(root.iterdir()) if root.exists() else []:
        if not year_dir.is_dir():
            continue
        for lt_dir in sorted(year_dir.iterdir()):
            for tsv in sorted(lt_dir.glob("*.tsv")):
                try:
                    df = pd.read_csv(tsv, sep="\t", header=None, dtype=str,
                                     on_bad_lines="skip", encoding="utf-8", engine="python")
                    df["list_type"] = lt_dir.name
                    df["year"] = year_dir.name
                    frames.append(df)
                except Exception:
                    pass
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
