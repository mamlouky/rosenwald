#!/usr/bin/env python3
"""
Copie uniquement les pages à vérifier (listées dans pages_a_imager.csv)
depuis un dossier d'images vers un dossier 'a_envoyer/'.

USAGE :
    python -m rosenwald.women.sample_pages CHEMIN_DOSSIER_IMAGES CHEMIN_pages_a_imager.csv

Exemple :
    python -m rosenwald.women.sample_pages ./data/images ./data/index/pages_a_imager.csv

Structures gérées (recherche récursive, l'ordre des sous-dossiers importe peu) :
    images/<annee>/<type>/page-XXXX.ext
    images/<annee>/page-XXXX.ext
    dossier plat : page-XXXX.ext  (peut être ambigu entre années)
Formats acceptés : .png .jpg .jpeg .tif .tiff .webp
"""
from __future__ import annotations

import csv
import re
import shutil
import sys
from pathlib import Path

EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}


def year_from_path(p: Path):
    for part in p.parts:
        if re.fullmatch(r"(18|19)\d{2}", part):
            return part
    return None


def page_from_name(name: str):
    m = re.search(r"page[-_]?(\d{1,4})", name, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{1,4})(?=\.\w+$)", name)
    if m:
        return int(m.group(1))
    return None


def main() -> None:
    if len(sys.argv) < 3:
        print("USAGE: python -m rosenwald.women.sample_pages DOSSIER_IMAGES pages_a_imager.csv")
        sys.exit(1)
    img_root = Path(sys.argv[1])
    csv_path = Path(sys.argv[2])
    out_dir = Path("a_envoyer")
    out_dir.mkdir(exist_ok=True)

    # Index every image on disk by (year, page) so we can match flexibly.
    index: dict = {}
    all_imgs = [p for p in img_root.rglob("*") if p.suffix.lower() in EXTS]
    print(f"{len(all_imgs)} images trouvées dans {img_root}")
    for p in all_imgs:
        pg = page_from_name(p.name)
        if pg is not None:
            index.setdefault((year_from_path(p), pg), []).append(p)

    targets = []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            targets.append((row["annee"].strip(),
                            int(re.sub(r"\D", "", row["page"]) or 0),
                            row["type_liste"].strip()))

    copied, missing = 0, []
    for annee, page, lt in targets:
        cands = index.get((annee, page)) or index.get((None, page))
        chosen = None
        if cands:
            for c in cands:
                if lt in str(c):
                    chosen = c
                    break
            chosen = chosen or cands[0]
        if chosen:
            dest = out_dir / f"{annee}_{page:04d}_{lt}{chosen.suffix.lower()}"
            shutil.copy2(chosen, dest)
            copied += 1
        else:
            missing.append((annee, page, lt))

    print(f"\n{copied} images copiées dans ./{out_dir}/")
    if missing:
        print(f"{len(missing)} pages introuvables :")
        for a, p, lt in missing[:30]:
            print(f"   {a} page {p} ({lt})")
        if len(missing) > 30:
            print(f"   ... et {len(missing) - 30} autres")


if __name__ == "__main__":
    main()
