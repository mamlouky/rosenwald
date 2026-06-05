.PHONY: install test extract ocr postprocess women analysis eval site clean
YEAR ?= 1887

install:          ; pip install -r requirements.txt
test:             ; pytest -q
extract:          ; python -m rosenwald.extract.run_year $(YEAR)
ocr:              ; python -m rosenwald.extract.ocr_run $(YEAR)
postprocess:      ; python -m rosenwald.postprocess.fix_tsv_columns && \
                    python -m rosenwald.postprocess.restructure_tsv && \
                    python -m rosenwald.postprocess.merge_to_excel
women:            ; python -m rosenwald.women.build_workbook
analysis:         ; python -m rosenwald.analysis.run_all
analysis-women:   ; python -m rosenwald.analysis.run_all --women-only
eval-fields:      ; python -m rosenwald.evaluation.evaluate fields --ref data/reference/Liste_femmes.xlsx
site:             ; python webapp/generate_site.py
clean:            ; find . -name __pycache__ -type d -prune -exec rm -rf {} + ; find . -name '*.pyc' -delete
