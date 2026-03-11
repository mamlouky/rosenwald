"""
One TSV extraction prompt per list type.
Each prompt defines its own column schema (documented inline).
The PROMPTS dict maps list_type -> prompt string.
"""

# ══════════════════════════════════════════════════════════════════════
# 1. PARIS PAR QUARTIERS  (1887-1914)
#
# TSV columns:
#   year | pdf_page | arrondissement | quartier | profession_section
#   | full_name_raw | civil_status | diploma_year | address_raw
#   | phone_raw | hours_raw | specialties_raw | notes_raw | entry_raw
# ══════════════════════════════════════════════════════════════════════
PARIS_QUARTIERS_PROMPT = """\
You are analyzing a scanned page from the Rosenwald directory — Paris geographic list organized by quartiers.

CRITICAL RULES
- The page may contain advertisements at the top or bottom. Ignore ads completely.
- The page is often in TWO COLUMNS. Read the entire LEFT column top-to-bottom, then the entire RIGHT column top-to-bottom.
  CRITICAL: The right column is an INDEPENDENT list. When you start reading the right column, reset your quartier/section context.
  Determine the right column's starting context from headers visible AT THE TOP of the right column.
  Do NOT carry over the quartier from the bottom of the left column into the right column.
  If the right column's first entries have no header above them, they continue the same section that was active
  at the TOP of the page (not the bottom of the left column).
- Do NOT skip any entries. Be exhaustive.

TASK
Return TSV only (no markdown, no header row, no code fences, no blank lines). One line per person entry.

COLUMNS (tab-separated, in this exact order):
year\tpdf_page\tarrondissement\tquartier\tprofession_section\tfull_name_raw\tcivil_status\tdiploma_year\taddress_raw\tphone_raw\thours_raw\tspecialties_raw\tnotes_raw\tentry_raw

DEFINITIONS
- arrondissement : last ARRONDISSEMENT header seen (e.g. "1er ARRONDISSEMENT"). Carry forward across pages.
- quartier       : last QUARTIER header seen (e.g. "QUARTIER SAINT-GERMAIN L'AUXERROIS"). Carry forward.
- profession_section : DOCTEURS, OFFICIERS_DE_SANTE, or PHARMACIENS when a section header is visible; else blank.
- full_name_raw  : the person's name exactly as printed, INCLUDING any civil-status prefix (Mme, Mlle, etc.).
- civil_status   : ONLY the civil-status marker if explicitly present — Mme, Mme Vve, Mme., Mlle, Mlle.,
                   Mademoiselle, Melle, Dame, nee. Leave blank if absent.
- diploma_year   : 4-digit diploma year near the name if present; else blank.
- address_raw    : street name + number if present; else blank.
- phone_raw      : telephone number if present (e.g. "INVALIDES 01-74", "232-18"); else blank.
- hours_raw      : consultation hours if present (e.g. "1 a 3", "Lun. Mer. Ven. 2-4"); else blank.
- specialties_raw: medical specialties mentioned (e.g. "mal. fem.", "accouchements", "mal. enf."); else blank.
- notes_raw      : other titles, hospital affiliations, or distinction symbols; else blank.
- entry_raw      : the complete raw entry text exactly as printed.

CONSTRAINTS
- year and pdf_page are provided below. Use them exactly in every row.
- If a field is illegible, leave it blank. NEVER invent content.
- Output TSV only. No header row. No blank lines.
- Empty fields must be completely empty (just a tab). NEVER write NULL, null, N/A, or any placeholder.
"""

# ══════════════════════════════════════════════════════════════════════
# 2. DEPARTEMENTS & COLONIES PAR CANTONS  (1887-1914, 1922)
#
# TSV columns:
#   year | pdf_page | departement | canton | profession_section
#   | full_name_raw | civil_status | diploma_year | address_raw
#   | notes_raw | entry_raw
# ══════════════════════════════════════════════════════════════════════
DEPS_CANTONS_PROMPT = """\
You are analyzing a scanned page from the Rosenwald directory — geographic list by cantons (departments and colonies).

CRITICAL RULES
- The page may contain advertisements at the top or bottom. Ignore ads completely.
- The page is often in TWO COLUMNS. Read the entire LEFT column top-to-bottom, then the entire RIGHT column top-to-bottom.
  CRITICAL: The right column is an INDEPENDENT list. When you start reading the right column, reset your canton/section context.
  Determine the right column's starting context from headers visible AT THE TOP of the right column.
  Do NOT carry over the canton from the bottom of the left column into the right column.
  If the right column's first entries have no header above them, they continue the same section that was active
  at the TOP of the page (not the bottom of the left column).
- Do NOT skip any entries. Be exhaustive.

TASK
Return TSV only (no markdown, no header row, no code fences, no blank lines). One line per person entry.

COLUMNS (tab-separated, in this exact order — always exactly 11 fields per row):
year\tpdf_page\tdepartement\tcanton\tprofession_section\tfull_name_raw\tcivil_status\tdiploma_year\taddress_raw\tnotes_raw\tentry_raw

CRITICAL — COLUMN COUNT: Every row MUST have exactly 11 tab-separated fields.
Count: year(1) | pdf_page(2) | departement(3) | canton(4) | profession_section(5) | full_name_raw(6) | civil_status(7) | diploma_year(8) | address_raw(9) | notes_raw(10) | entry_raw(11)
Empty fields must be output as an empty string between two tabs (NOT skipped, NOT omitted).
Example of a typical sparse entry where civil_status (col 7) and notes_raw (col 10) are empty:
1887\t380\tAIN\tBOURG\tDOCTEURS\tDupont\t\t1881\tpl. du Greffe\t\tDupont 1881, pl. du Greffe.
That row has 10 tabs = 11 fields. Always verify your tab count before outputting each line.

HIERARCHY OF HEADERS (critical — read carefully)
The page uses a three-level hierarchy:
  1. DÉPARTEMENT  — e.g. "AIN", "CHER", "ALGÉRIE". Large bold header. → goes in departement column.
  2. ARRONDISSEMENT — e.g. "ARRONDISSEMENT DE BOURG", "ARR. DE BELLEY". A grouping header only.
     → DO NOT put in canton. It is structural context; ignore it for the canton column.
  3. CANTON — e.g. "BOURG", "BAGÉ-LE-CHÂTEL", "PONT-D'AIN". The actual unit to extract.
     → Put in canton column. Carry forward until the next canton header overrides it.

DEFINITIONS
- departement    : last DÉPARTEMENT (or colony) header seen (e.g. "AIN", "CHER", "ALGÉRIE", "MARTINIQUE"). Carry forward.
- canton         : last CANTON header seen (e.g. "BOURG", "PONT-D'AIN", "BAGÉ-LE-CHÂTEL").
                   NEVER put an ARRONDISSEMENT name here. Carry forward until overridden.
- profession_section : DOCTEURS, OFFICIERS_DE_SANTE, or PHARMACIENS.
  Use the last explicit section header seen. If no header is visible for a canton, INFER from the name prefix:
    "Drs" or "Dr" at the start → DOCTEURS
    "Off." at the start → OFFICIERS_DE_SANTE
    "Ph." at the start → PHARMACIENS
  Never leave profession_section blank if a prefix like Drs/Off./Ph. is present.
- full_name_raw  : the person's name exactly as printed, INCLUDING any civil-status prefix or professional prefix (Drs, Dr, Off., Ph.).
- civil_status   : ONLY the civil-status marker if explicitly present — Mme, Mme Vve, Mme., Mlle, Mlle.,
                   Mademoiselle, Melle, Dame, nee. Leave blank if absent.
- diploma_year   : 4-digit diploma year near the name if present; else blank.
- address_raw    : town or city name if mentioned; else blank. (Full street addresses are rare in this list.)
- notes_raw      : any other notes, distinctions, or symbols; else blank.
- entry_raw      : the complete raw entry text exactly as printed.

CONSTRAINTS
- year and pdf_page are provided below. Use them exactly in every row.
- Entries in this list are typically sparse: name + diploma year + sometimes a town. Treat absent fields as blank.
- If a field is illegible, leave it blank. NEVER invent content.
- Output TSV only. No header row. No blank lines.
- Empty fields must be completely empty (just a tab). NEVER write NULL, null, N/A, or any placeholder.
"""

# ══════════════════════════════════════════════════════════════════════
# 3. MEDECINS SPECIALISTES  (from 1888)
#
# TSV columns:
#   year | pdf_page | specialite | full_name_raw | civil_status
#   | diploma_year | address_raw | phone_raw | hours_raw
#   | notes_raw | entry_raw
# ══════════════════════════════════════════════════════════════════════
SPECIALISTS_PROMPT = """\
You are analyzing a scanned page from the Rosenwald directory — list of specialist doctors in Paris.

CRITICAL RULES
- The page may contain advertisements at the top or bottom. Ignore ads completely.
- The page is often in TWO COLUMNS. Read the entire LEFT column top-to-bottom, then the RIGHT column top-to-bottom.
  When starting the right column, reset context — determine it from headers visible at the TOP of the right column.
- Do NOT skip any entries. Be exhaustive.

TASK
Return TSV only (no markdown, no header row, no code fences, no blank lines). One line per person entry.

COLUMNS (tab-separated, in this exact order):
year\tpdf_page\tspecialite\tfull_name_raw\tcivil_status\tdiploma_year\taddress_raw\tphone_raw\thours_raw\tnotes_raw\tentry_raw

DEFINITIONS
- specialite     : last specialty section header seen, in uppercase as printed
                   (e.g. "MALADIES DES FEMMES", "ACCOUCHEMENTS", "MALADIES DES ENFANTS",
                   "MALADIES DE LA PEAU", "MALADIES DES YEUX"). Carry forward.
- full_name_raw  : the person's name exactly as printed, INCLUDING any civil-status prefix.
- civil_status   : ONLY the civil-status marker if explicitly present — Mme, Mme Vve, Mme., Mlle, Mlle.,
                   Mademoiselle, Melle, Dame, nee. Leave blank if absent.
- diploma_year   : 4-digit diploma year near the name if present; else blank.
- address_raw    : street name + number if present; else blank.
- phone_raw      : telephone number if present; else blank.
- hours_raw      : consultation hours if present; else blank.
- notes_raw      : titles, hospital affiliations, or distinction symbols; else blank.
- entry_raw      : the complete raw entry text exactly as printed.

CONSTRAINTS
- year and pdf_page are provided below. Use them exactly in every row.
- If a field is illegible, leave it blank. NEVER invent content.
- Output TSV only. No header row. No blank lines.
- Empty fields must be completely empty (just a tab). NEVER write NULL, null, N/A, or any placeholder.
"""

# ══════════════════════════════════════════════════════════════════════
# 4. MEDECINS DES STATIONS THERMALES  (from 1891)
#
# TSV columns:
#   year | pdf_page | station | full_name_raw | civil_status
#   | diploma_year | address_raw | notes_raw | entry_raw
# ══════════════════════════════════════════════════════════════════════
THERMAL_SPAS_PROMPT = """\
You are analyzing a scanned page from the Rosenwald directory — list of doctors at thermal spas (stations thermales).

CRITICAL RULES
- The page may contain advertisements at the top or bottom. Ignore ads completely.
- The page is often in TWO COLUMNS. Read the entire LEFT column top-to-bottom, then the RIGHT column top-to-bottom.
  When starting the right column, reset context — determine it from headers visible at the TOP of the right column.
- Do NOT skip any entries. Be exhaustive.

TASK
Return TSV only (no markdown, no header row, no code fences, no blank lines). One line per person entry.

COLUMNS (tab-separated, in this exact order):
year\tpdf_page\tstation\tfull_name_raw\tcivil_status\tdiploma_year\taddress_raw\tnotes_raw\tentry_raw

DEFINITIONS
- station        : last spa/station name header seen, in uppercase as printed
                   (e.g. "VICHY", "AIX-LES-BAINS", "CONTREXEVILLE", "EVIAN"). Carry forward.
- full_name_raw  : the person's name exactly as printed, INCLUDING any civil-status prefix.
- civil_status   : ONLY the civil-status marker if explicitly present — Mme, Mme Vve, Mme., Mlle, Mlle.,
                   Mademoiselle, Melle, Dame, nee. Leave blank if absent.
- diploma_year   : 4-digit diploma year near the name if present; else blank.
- address_raw    : home city or address if mentioned; else blank.
- notes_raw      : any other information, distinctions, or symbols; else blank.
- entry_raw      : the complete raw entry text exactly as printed.

CONSTRAINTS
- year and pdf_page are provided below. Use them exactly in every row.
- Entries are typically very sparse: name + diploma year. Treat absent fields as blank.
- If a field is illegible, leave it blank. NEVER invent content.
- Output TSV only. No header row. No blank lines.
- Empty fields must be completely empty (just a tab). NEVER write NULL, null, N/A, or any placeholder.
"""

# ══════════════════════════════════════════════════════════════════════
# 5. PARIS PAR RUES  (1917, 1922)
#
# TSV columns:
#   year | pdf_page | rue | arrondissement | profession_section
#   | full_name_raw | civil_status | diploma_year | address_raw
#   | phone_raw | hours_raw | specialties_raw | notes_raw | entry_raw
# ══════════════════════════════════════════════════════════════════════
PARIS_RUES_PROMPT = """\
You are analyzing a scanned page from the Rosenwald directory — Paris list organized by street names (par rues).

CRITICAL RULES
- The page may contain advertisements at the top or bottom. Ignore ads completely.
- The page is often in TWO COLUMNS. Read the entire LEFT column top-to-bottom, then the RIGHT column top-to-bottom.
  When starting the right column, reset context — determine it from headers visible at the TOP of the right column.
- Do NOT skip any entries. Be exhaustive.

TASK
Return TSV only (no markdown, no header row, no code fences, no blank lines). One line per person entry.

COLUMNS (tab-separated, in this exact order):
year\tpdf_page\true\tarrondissement\tprofession_section\tfull_name_raw\tcivil_status\tdiploma_year\taddress_raw\tphone_raw\thours_raw\tspecialties_raw\tnotes_raw\tentry_raw

DEFINITIONS
- rue            : last street/boulevard/avenue/passage header seen, as printed
                   (e.g. "RUE DE RIVOLI", "BOULEVARD SAINT-GERMAIN"). Carry forward.
- arrondissement : arrondissement number if indicated near the street header or entry; else blank.
- profession_section : DOCTEURS, OFFICIERS_DE_SANTE, or PHARMACIENS if visible; else blank.
- full_name_raw  : the person's name exactly as printed, INCLUDING any civil-status prefix.
- civil_status   : ONLY the civil-status marker if explicitly present — Mme, Mme Vve, Mme., Mlle, Mlle.,
                   Mademoiselle, Melle, Dame, nee. Leave blank if absent.
- diploma_year   : 4-digit diploma year near the name if present; else blank.
- address_raw    : street number or building detail if present; else blank.
- phone_raw      : telephone number if present; else blank.
- hours_raw      : consultation hours if present; else blank.
- specialties_raw: medical specialties mentioned; else blank.
- notes_raw      : titles, hospital affiliations, or distinction symbols; else blank.
- entry_raw      : the complete raw entry text exactly as printed.

CONSTRAINTS
- year and pdf_page are provided below. Use them exactly in every row.
- If a field is illegible, leave it blank. NEVER invent content.
- Output TSV only. No header row. No blank lines.
- Empty fields must be completely empty (just a tab). NEVER write NULL, null, N/A, or any placeholder.
"""

# ══════════════════════════════════════════════════════════════════════
# 6. MEDECINS DE LA PREFECTURE DE LA SEINE  (1907-1917)
#
# These pages are scanned in LANDSCAPE orientation (noted "inversée"
# in the Excel). The image is rotated before being sent to Gemini,
# so the text will appear upright. The page is a SINGLE LIST,
# not divided into two columns.
#
# TSV columns (same as specialists):
#   year | pdf_page | specialite | full_name_raw | civil_status
#   | diploma_year | address_raw | phone_raw | hours_raw
#   | notes_raw | entry_raw
# ══════════════════════════════════════════════════════════════════════
PREFECTURE_SEINE_PROMPT = """\
You are analyzing a scanned page from the Rosenwald directory — list of doctors at the Prefecture de la Seine.

IMPORTANT: This page was scanned in landscape format and has been rotated to appear upright.
It is a SINGLE CONTINUOUS LIST, not divided into two columns.

CRITICAL RULES
- The page may contain a title header or administrative details at the top. Extract only the person entries.
- Do NOT skip any entries. Be exhaustive.

TASK
Return TSV only (no markdown, no header row, no code fences, no blank lines). One line per person entry.

COLUMNS (tab-separated, in this exact order):
year\tpdf_page\tspecialite\tfull_name_raw\tcivil_status\tdiploma_year\taddress_raw\tphone_raw\thours_raw\tnotes_raw\tentry_raw

DEFINITIONS
- specialite     : section or category header if any is visible (e.g. "MEDECINS", "CHIRURGIENS"); else blank.
- full_name_raw  : the person's name exactly as printed, INCLUDING any civil-status prefix.
- civil_status   : ONLY the civil-status marker if explicitly present — Mme, Mme Vve, Mme., Mlle, Mlle.,
                   Mademoiselle, Melle, Dame, nee. Leave blank if absent.
- diploma_year   : 4-digit diploma year near the name if present; else blank.
- address_raw    : address if present; else blank.
- phone_raw      : telephone number if present; else blank.
- hours_raw      : consultation hours if present; else blank.
- notes_raw      : titles, hospital affiliations, or distinction symbols; else blank.
- entry_raw      : the complete raw entry text exactly as printed.

CONSTRAINTS
- year and pdf_page are provided below. Use them exactly in every row.
- If a field is illegible, leave it blank. NEVER invent content.
- Output TSV only. No header row. No blank lines.
- Empty fields must be completely empty (just a tab). NEVER write NULL, null, N/A, or any placeholder.
"""

# ══════════════════════════════════════════════════════════════════════
# Dispatch table  —  list_type -> prompt
# ══════════════════════════════════════════════════════════════════════
PROMPTS: dict = {
    "paris_quartiers":  PARIS_QUARTIERS_PROMPT,
    "deps_cantons":     DEPS_CANTONS_PROMPT,
    "seine_cantons":    DEPS_CANTONS_PROMPT,   # same format, different geographic scope
    "specialists":      SPECIALISTS_PROMPT,
    "thermal_spas":     THERMAL_SPAS_PROMPT,
    "paris_rues":       PARIS_RUES_PROMPT,
    "bienfaisance":     SPECIALISTS_PROMPT,    # short specialist-style list
    "prefecture_seine": PREFECTURE_SEINE_PROMPT,  # landscape page, single column
}

# Backward-compatible alias used by old test scripts
PARIS_GEO_TSV_PROMPT = PARIS_QUARTIERS_PROMPT
