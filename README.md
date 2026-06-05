# Quantifying The Invisible : Extraction structurée et analyse des listes « géographiques » des Guides Rosenwald (1887-1922).

Pipeline de transformation des pages numérisées des **Guides Rosenwald** en
données tabulaires exploitables, avec une attention particulière aux **femmes
médecins**, dans le cadre du projet MEDIF.

## Installation

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # ou : pip install -e .
```

Pour l'extraction (appels modèle), définir `GOOGLE_API_KEY` dans un `.env` à la
racine. Les analyses et l'évaluation locale ne nécessitent aucune clé.

## Structure

```
rosenwald/            paquet principal
├─ config.py          chemins centralises (data/, index, reference)
├─ index_reader.py    index des sections + prenoms feminins
├─ extract/           ETAPE 1 : image -> TSV
│  ├─ pdf_to_png.py   rendu des pages
│  ├─ prompts.py      prompts specialises + UNIFIED_PROMPT (ablation)
│  ├─ gemini.py       appel Vertex AI / Gemini
│  ├─ run_year.py     orchestrateur (--mode routegeo|routed-nogeo|unified)
│  ├─ ocr_run.py      baseline Tesseract
│  └─ tesseract.py
├─ postprocess/       ETAPE 2 : nettoyage / normalisation
│  ├─ diagnose_tsv.py · fix_tsv_columns.py · restructure_tsv.py
│  ├─ merge_to_excel.py · export_excel.py
├─ women/             EXTRACTION FEMMES
│  ├─ names.py        parsing nom / prenom / etat civil
│  ├─ detect.py       detection femme + preuve (source unique)
│  ├─ filter.py       merge tsv_raw -> tsv_merged + is_woman
│  ├─ build_workbook.py  -> Liste_femmes.xlsx (7 feuilles)
│  └─ sample_pages.py    echantillonnage des pages a verifier
├─ evaluation/
│  └─ evaluate.py     WER/CER · ablation · field-accuracy 
└─ analysis/          ANALYSES 
   ├─ load.py         load_women(Liste_femmes) · load_corpus(tsv_clean)
   ├─ figures.py · tables.py · run_all.py

webapp/               site scrollytelling (generate_site.py -> dist/)
data/                 (gitignored)
├─ index/             
├─ reference/         
├─ pdfs/ images/ ocr_text/ tsv_raw/ tsv_fixed/ tsv_clean/ tsv_merged/ output/
tests/                pytest (24 tests)
```

## Pipeline complet

```bash
# 1. Extraction (RouteGeo = systeme complet)
python -m rosenwald.extract.run_year 1887

# 2. Post-traitement
python -m rosenwald.postprocess.fix_tsv_columns
python -m rosenwald.postprocess.restructure_tsv
python -m rosenwald.postprocess.merge_to_excel

# 3. Femmes : merge annote -> classeur 7 feuilles
python -m rosenwald.women.filter 1887
python -m rosenwald.women.build_workbook
python -m rosenwald.women.build_workbook --validate data/reference/Liste_femmes.xlsx

# 4. Analyses (femmes <- Liste_femmes ; corpus <- tsv_clean)
python -m rosenwald.analysis.run_all --women-only
python -m rosenwald.analysis.run_all
```

## Les 4 methodes du rapport 

| Etape | Commande |
|---|---|
| Tesseract (OCR seul) | `python -m rosenwald.extract.ocr_run 1887` |
| Prompt unifie | `python -m rosenwald.extract.run_year 1887 --mode=unified` |
| Routage (sans contexte geo) | `… run_year 1887 --mode=routed-nogeo` |
| RouteGeo (complet) | `… run_year 1887` |

## Tests

```bash
pytest          # 24 tests, aucune dependance reseau
```
