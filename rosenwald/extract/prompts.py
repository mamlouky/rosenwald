"""
One TSV extraction prompt per list type.
Each prompt defines its own column schema (documented inline).
The PROMPTS dict maps list_type -> prompt string.

IMPORTANT
These prompts assume your calling code injects:
- year
- pdf_page
- optionally a starting inherited context from the previous page

Recommended runtime injection for pages that may continue previous context:
Inherited context from previous page:
- departement: ...
- arrondissement: ...
- canton: ...
- profession_section: ...

or for Paris pages:
- arrondissement: ...
- quartier: ...
- profession_section: ...

This inherited context is only a DEFAULT STARTING CONTEXT.
Any valid new header on the current page must override it immediately.
"""

# ══════════════════════════════════════════════════════════════════════
# 1. PARIS PAR QUARTIERS  (1887-1914)
#
# TSV columns:
#   year | pdf_page | arrondissement | quartier | profession_section
#   | full_name_raw | diploma_year | address_raw
#   | phone_raw | hours_raw | specialties_raw
#   | gender_marker_raw | maiden_name_raw | notes_raw | entry_raw
# ══════════════════════════════════════════════════════════════════════
PARIS_QUARTIERS_PROMPT = """\
You are analyzing a scanned page from the Rosenwald directory — Paris geographic list organized by quartiers.

STARTING CONTEXT
This page may continue the context from the previous page.
If inherited context is provided externally, use it only as the starting default context.
Any valid new header visible on the current page overrides the inherited context immediately.

CONTEXT HEADERS (read them to update your context, but never output them as rows)
- Arrondissement headers (e.g. "1er ARRONDISSEMENT", "2e ARRONDISSEMENT") -> update arrondissement.
- Quartier headers ONLY if they explicitly begin with "QUARTIER" (e.g. "QUARTIER SAINT-GERMAIN L'AUXERROIS", "QUARTIER DES HALLES") -> update quartier.
- Section headers (DOCTEURS, OFFICIERS DE SANTE, PHARMACIENS) -> update profession_section.

STRICT STATE MANAGEMENT
Maintain a strict hierarchical state for every entry:
arrondissement > quartier > profession_section

When a new arrondissement header appears:
- overwrite arrondissement
- reset quartier to blank
- reset profession_section to blank

When a new quartier header appears:
- overwrite quartier
- reset profession_section to blank

When a new profession section header appears:
- overwrite profession_section only

Do not carry an older quartier or profession_section across a visible higher-level header change.

ARRONDISSEMENT SUBTITLE RULE
A centered subtitle immediately below an arrondissement header (for example "LOUVRE" under "1er ARRONDISSEMENT")
belongs to the arrondissement title area and does NOT by itself create or replace the quartier.

QUARTIER UPDATE RULE
Only an explicit header beginning with "QUARTIER" updates the quartier field.
Do NOT treat arrondissement subtitles, centered locality names, or decorative centered words as quartier headers
unless they explicitly begin with "QUARTIER".

PROFESSION BLOCK CONTINUITY
Within the same quartier, different profession sections (DOCTEURS, OFFICIERS DE SANTE, PHARMACIENS)
may appear across both columns.
Changing profession_section does NOT change quartier.
Keep the current quartier until a new explicit "QUARTIER ..." header appears.

PAGE READING STRATEGY
The page may contain two columns.
Read entries in visual reading order by local blocks, not by blindly continuing old context.

A right-column block may continue the same quartier as the left-column block.
Do NOT create a new quartier for the right column unless a new explicit "QUARTIER ..." header appears above that block.

Use the nearest valid header above each entry:
- "ARRONDISSEMENT ..." updates arrondissement
- "QUARTIER ..." updates quartier
- DOCTEURS / OFFICIERS DE SANTE / PHARMACIENS update profession_section

CRITICAL — COLUMN COUNT
Every row MUST have exactly 15 tab-separated fields.
Empty fields must be preserved as empty strings between tabs.
Never omit an empty field.

IGNORE COMPLETELY (produce nothing for these)
- Advertisements anywhere on the page.
- Page titles, section titles, running headers, page numbers.
- Population statistics and summary counts.
- Any other non-person line.

TASK
Return TSV only (no markdown, no header row, no code fences, no blank lines).
One line per person entry.

COLUMNS (tab-separated, in this exact order):
year\tpdf_page\tarrondissement\tquartier\tprofession_section\tfull_name_raw\tdiploma_year\taddress_raw\tphone_raw\thours_raw\tspecialties_raw\tgender_marker_raw\tmaiden_name_raw\tnotes_raw\tentry_raw

DEFINITIONS
- arrondissement    : last ARRONDISSEMENT header seen. Store as printed.
- quartier          : last explicit QUARTIER header seen. Store only the quartier name, without the word "QUARTIER".
- profession_section: last section header seen — DOCTEURS, OFFICIERS_DE_SANTE, or PHARMACIENS. Carry forward.
  If no explicit section header is visible for an entry, infer from name prefix when possible:
  "Dr"/"Drs" -> DOCTEURS ; "Off." -> OFFICIERS_DE_SANTE ; "Ph." -> PHARMACIENS.
- full_name_raw     : the person's name exactly as printed, INCLUDING any prefix (Mme, Mlle, Dr, Drs, Off., Ph., etc.).
- diploma_year      : 4-digit diploma year if present; else blank.
- address_raw       : street address or location if present (e.g. "Rivoli 51", "Monnaie 14", "q. du Louvre 22"); else blank.
  If the entry uses "id." for the address or place, resolve it by copying the nearest compatible explicit address
  from the same local block when possible. Only leave blank if truly unclear.
- phone_raw         : telephone number if present; else blank.
- hours_raw         : consultation hours if present (e.g. "1 a 3", "2 à 4", "Jeu. Dim. Soir"); else blank.
- specialties_raw : only medical specialty labels such as "accouch.", "mal. fem.", "mal. enf.", "oculiste".
- gender_marker_raw : copy any explicit gender or marital marker attached to the entry, such as:
  "Dame", "Madame", "Mademoiselle", "Mme", "Mad.", "Mlle", "Melle", "Mme Vve", "veuve", "née".
  If none is explicitly present, leave blank.
- maiden_name_raw   : if the entry explicitly contains "née X", extract X only; otherwise leave blank.
- notes_raw         : titles, hospital affiliations, symbols, distinctions, successors, company mentions, or other notes; else blank.
- entry_raw         : the complete raw entry text exactly as printed.

IMPORTANT GENDER RULE
Do NOT infer sex from profession, surname, or first name alone.
Only copy explicit markers visible in the entry.

CONSTRAINTS
- year and pdf_page are provided below. Use them exactly in every row.
- If a field is illegible, leave it blank. NEVER invent content.
- Empty fields must be completely empty (just a tab). NEVER write NULL, null, N/A, or any placeholder.
- Output TSV only. No header row. No blank lines.
"""

# ══════════════════════════════════════════════════════════════════════
# 2. DEPARTEMENTS & COLONIES PAR CANTONS  (1887-1914, 1922)
#
# TSV columns:
#   year | pdf_page | departement | arrondissement | canton | profession_section
#   | full_name_raw | diploma_year | address_raw
#   | gender_marker_raw | maiden_name_raw | notes_raw | entry_raw
# ══════════════════════════════════════════════════════════════════════
DEPS_CANTONS_PROMPT = """\
You are analyzing a scanned page from the Rosenwald directory — geographic list by cantons (departments and colonies).

STARTING CONTEXT
This page may continue the geographic context from the previous page.
If inherited context is provided externally, use it only as the starting default context.

Typical inherited context may include:
- departement
- arrondissement
- canton
- profession_section

Any valid new header visible on the current page overrides the inherited context immediately.

CONTEXT HEADERS (read them to update your context, but never output them as rows)
- Department headers (e.g. "AIN", "CHER", "ALGÉRIE") -> update departement.
- Arrondissement headers (e.g. "BOURG", "ARRONDISSEMENT DE BELLEY", "ARRONDISSEMENT DE GEX") -> update arrondissement.
- Canton headers (e.g. "CANTON DE BAGÉ-LE-CHÂTEL", "CANTON DE LAGNIEU", "PONT-D'AIN") -> update canton.
- Section headers (DOCTEURS, OFFICIERS DE SANTE, PHARMACIENS) -> update profession_section.

HEADER HIERARCHY
The page uses a hierarchical geography:
1. DEPARTEMENT
2. ARRONDISSEMENT
3. CANTON
4. PROFESSION SECTION

ARRONDISSEMENT HEADER FORMS
An arrondissement may appear as:
- "ARRONDISSEMENT DE BELLEY"
- "ARRONDISSEMENT DE GEX"
- a centered locality block representing the arrondissement city, such as "BOURG", "BELLEY", "GEX"

Store only the arrondissement name itself in the arrondissement column
(e.g. "BOURG", "BELLEY", "GEX").

CANTON HEADER FORMS
A canton may appear as:
- "CANTON DE LAGNIEU"
- "CANTON DE PONT-D'AIN"
- "CANTON DE BAGÉ-LE-CHÂTEL"

Store only the canton name itself in the canton column
(e.g. "LAGNIEU", "PONT-D'AIN", "BAGÉ-LE-CHÂTEL").

STRICT STATE MANAGEMENT
Maintain a strict hierarchical state for every entry:
departement > arrondissement > canton > profession_section

When a new department header appears:
- overwrite departement
- reset arrondissement to blank
- reset canton to blank
- reset profession_section to blank

When a new arrondissement header appears:
- overwrite arrondissement
- reset canton to blank
- reset profession_section to blank

When a new canton header appears:
- overwrite canton
- reset profession_section to blank

When a new profession section header appears:
- overwrite profession_section only

Do not carry arrondissement or canton values across a visible higher-level header change.

ARRONDISSEMENT-LEVEL ENTRIES
Some entries belong directly to the arrondissement city block and are not under any canton yet.
In that case:
- keep the current departement
- keep the current arrondissement
- set canton to blank

Example:
After "Arrondissement de Gex" and the centered locality block "GEX", entries under DOCTEURS or PHARMACIENS
belong to arrondissement = GEX and canton = blank until a canton header appears.

NEAREST-HEADER RULE
For each person entry, use the closest valid department / arrondissement / canton / profession header visually above it.
A newer nearby header always overrides an older distant one.

PAGE READING STRATEGY
Read the page in visual reading order by blocks and headers.

If the page contains two columns, process each column top-to-bottom, but always give priority
to the nearest visible header above each entry.

When a large centered header spans the page width, treat it as a new global context
for all entries below it.

Never keep an older arrondissement, canton, or profession_section if a newer valid header
appears closer to the entry.

HANDLING "id."
If an entry contains "id." for the location, resolve it by copying the most recent explicit compatible
location from the same local block and same profession grouping when possible.
Do not leave "id." in address_raw unless the antecedent location is genuinely unclear.

Examples:
- "Durochat 1867, à Lagnieu. Méhier 1852, id." -> Méhier address_raw = "à Lagnieu"
- "Rozonet 1866, à Tenay. Wuillomet 1880, id." -> Wuillomet address_raw = "à Tenay"

IGNORE COMPLETELY (produce nothing for these)
- Advertisements anywhere on the page.
- Descriptive lines about the department, arrondissement, or canton:
  population stats, counts of doctors/pharmacists, economic notes, hydrotherapy notes, etc.
- A canton followed only by "Néant" -> produce no row.
- Page titles, running headers, page numbers.
- Any other non-person line.

ADVERTISEMENT BOUNDARIES
A large boxed or bold commercial text block is an advertisement and must be ignored completely.
Do not let advertisement text interrupt or redefine geographic context.
Context continues only from valid directory headers, not from ads.

TASK
Return TSV only (no markdown, no header row, no code fences, no blank lines).
One line per person entry.

COLUMNS (tab-separated, in this exact order — always exactly 13 fields per row):
year\tpdf_page\tdepartement\tarrondissement\tcanton\tprofession_section\tfull_name_raw\tdiploma_year\taddress_raw\tgender_marker_raw\tmaiden_name_raw\tnotes_raw\tentry_raw

CRITICAL — COLUMN COUNT
Every row MUST have exactly 13 tab-separated fields.
Count:
year(1) | pdf_page(2) | departement(3) | arrondissement(4) | canton(5) | profession_section(6)
| full_name_raw(7) | diploma_year(8) | address_raw(9) | gender_marker_raw(10) | maiden_name_raw(11)
| notes_raw(12) | entry_raw(13)

Empty fields must be output as an empty string between two tabs (NOT skipped, NOT omitted).

Example — arrondissement-level entry with no canton:
1887\t380\tAIN\tBOURG\t\tDOCTEURS\tDupont\t1881\tpl. du Greffe\t\t\t\tDupont 1881, pl. du Greffe.

Example — canton-level entry:
1887\t314\tAIN\tBOURG\tBAGÉ-LE-CHÂTEL\tDOCTEURS\tDrs Bourgeois\t1874\tà Bagé-le-Châtel\t\t\t\tDrs Bourgeois 1874, à Bagé-le-Châtel.

DEFINITIONS
- departement       : last department header seen. Carry forward.
- arrondissement    : last arrondissement header seen. Store only the arrondissement name.
- canton            : last canton header seen. Store only the canton name. Blank when entries belong directly to the arrondissement level.
- profession_section: last section header seen — DOCTEURS, OFFICIERS_DE_SANTE, or PHARMACIENS.
  If no explicit section header is visible for an entry, infer from name prefix when possible:
  "Dr"/"Drs" -> DOCTEURS ; "Off." -> OFFICIERS_DE_SANTE ; "Ph." -> PHARMACIENS.
- full_name_raw     : the person's name exactly as printed, INCLUDING any prefix (Drs, Dr, Off., Ph., Mme, Mlle, etc.).
- diploma_year      : 4-digit diploma year if present; else blank.
- address_raw       : any location or address mentioned (city, village, street, place name, etc.).
  Resolve "id." when possible from the same local block. If absent or truly unclear, leave blank.
- gender_marker_raw : copy any explicit gender or marital marker attached to the entry, such as:
  "Dame", "Madame", "Mademoiselle", "Mme", "Mad.", "Mlle", "Melle", "Mme Vve", "veuve", "née".
  If none is explicitly present, leave blank.
- maiden_name_raw   : if the entry explicitly contains "née X", extract X only; otherwise leave blank.
- notes_raw         : any other notes, symbols, distinctions, successor notes, or remarks; else blank.
- entry_raw         : the complete raw entry text exactly as printed.

IMPORTANT GENDER RULE
Do NOT infer sex from profession, surname, or first name alone.
Only copy explicit markers visible in the entry.

CONSTRAINTS
- year and pdf_page are provided below. Use them exactly in every row.
- Entries are typically sparse: name + diploma year + sometimes a location.
- If a field is illegible, leave it blank. NEVER invent content.
- Empty fields must be completely empty (just a tab). NEVER write NULL, null, N/A, or any placeholder.
- Output TSV only. No header row. No blank lines.
"""

# ══════════════════════════════════════════════════════════════════════
# 3. MEDECINS SPECIALISTES  (from 1888)
#
# TSV columns:
#   year | pdf_page | specialite | full_name_raw | diploma_year
#   | address_raw | phone_raw | hours_raw
#   | gender_marker_raw | maiden_name_raw | notes_raw | entry_raw
# ══════════════════════════════════════════════════════════════════════
SPECIALISTS_PROMPT = """\
You are analyzing a scanned page from the Rosenwald directory — list of specialist doctors in Paris.

STARTING CONTEXT
This page may continue the previous page.
If inherited context is provided externally, use it only as a starting default.
Any valid new header on the current page overrides it immediately.

CONTEXT HEADERS (read them to update your context, but never output them as rows)
- Specialty section headers (e.g. "MALADIES DES FEMMES", "ACCOUCHEMENTS") -> update specialite.

PAGE READING STRATEGY
The page may contain two columns.
Read entries in visual reading order by local blocks.
Use the nearest valid specialty header above each entry.

IGNORE COMPLETELY (produce nothing for these)
- Advertisements anywhere on the page.
- Page titles, running headers, page numbers.
- Any other non-person line.

TASK
Return TSV only (no markdown, no header row, no code fences, no blank lines).
One line per person entry.

COLUMNS (tab-separated, in this exact order):
year\tpdf_page\tspecialite\tfull_name_raw\tdiploma_year\taddress_raw\tphone_raw\thours_raw\tgender_marker_raw\tmaiden_name_raw\tnotes_raw\tentry_raw

DEFINITIONS
- specialite        : last specialty section header seen, in uppercase as printed. Carry forward.
- full_name_raw     : the person's name exactly as printed, INCLUDING any prefix (Mme, Mlle, Dr, etc.).
- diploma_year      : 4-digit diploma year if present; else blank.
- address_raw       : street address or location if present; else blank.
  Resolve "id." when possible from the same local block.
- phone_raw         : telephone number if present; else blank.
- hours_raw         : consultation hours if present (e.g. "1 a 3", "2 à 4", "Jeu. Dim. Soir"); else blank.
- gender_marker_raw : copy any explicit gender or marital marker attached to the entry, such as:
  "Dame", "Madame", "Mademoiselle", "Mme", "Mad.", "Mlle", "Melle", "Mme Vve", "veuve", "née".
  If none is explicitly present, leave blank.
- maiden_name_raw   : if the entry explicitly contains "née X", extract X only; otherwise leave blank.
- notes_raw         : titles, hospital affiliations, symbols, distinctions, or other notes; else blank.
- entry_raw         : the complete raw entry text exactly as printed.

IMPORTANT GENDER RULE
Do NOT infer sex from profession, surname, or first name alone.
Only copy explicit markers visible in the entry.

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
#   year | pdf_page | station | full_name_raw | diploma_year
#   | address_raw | gender_marker_raw | maiden_name_raw | notes_raw | entry_raw
# ══════════════════════════════════════════════════════════════════════
THERMAL_SPAS_PROMPT = """\
You are analyzing a scanned page from the Rosenwald directory — list of doctors at thermal spas (stations thermales).

STARTING CONTEXT
This page may continue the previous page.
If inherited station context is provided externally, use it only as a starting default.
Any valid new station header on the current page overrides it immediately.

CONTEXT HEADERS (read them to update your context, but never output them as rows)
- Spa/station name headers (e.g. "VICHY", "AIX-LES-BAINS") -> update station.

PAGE READING STRATEGY
The page may contain two columns.
Read entries in visual reading order by local blocks.
Use the nearest valid station header above each entry.

IGNORE COMPLETELY (produce nothing for these)
- Advertisements anywhere on the page.
- Page titles, running headers, page numbers.
- Any other non-person line.

TASK
Return TSV only (no markdown, no header row, no code fences, no blank lines).
One line per person entry.

COLUMNS (tab-separated, in this exact order):
year\tpdf_page\tstation\tfull_name_raw\tdiploma_year\taddress_raw\tgender_marker_raw\tmaiden_name_raw\tnotes_raw\tentry_raw

DEFINITIONS
- station           : last spa/station name header seen, in uppercase as printed. Carry forward.
- full_name_raw     : the person's name exactly as printed, INCLUDING any prefix (Mme, Mlle, Dr, etc.).
- diploma_year      : 4-digit diploma year if present; else blank.
- address_raw       : home city or address if mentioned; else blank.
  Resolve "id." when possible from the same local block.
- gender_marker_raw : copy any explicit gender or marital marker attached to the entry, such as:
  "Dame", "Madame", "Mademoiselle", "Mme", "Mad.", "Mlle", "Melle", "Mme Vve", "veuve", "née".
  If none is explicitly present, leave blank.
- maiden_name_raw   : if the entry explicitly contains "née X", extract X only; otherwise leave blank.
- notes_raw         : any other information, distinctions, affiliations, or symbols; else blank.
- entry_raw         : the complete raw entry text exactly as printed.

IMPORTANT GENDER RULE
Do NOT infer sex from profession, surname, or first name alone.
Only copy explicit markers visible in the entry.

CONSTRAINTS
- year and pdf_page are provided below. Use them exactly in every row.
- Entries are typically sparse: name + diploma year.
- If a field is illegible, leave it blank. NEVER invent content.
- Output TSV only. No header row. No blank lines.
- Empty fields must be completely empty (just a tab). NEVER write NULL, null, N/A, or any placeholder.
"""

# ══════════════════════════════════════════════════════════════════════
# 5. PARIS PAR RUES  (1917, 1922)
#
# TSV columns:
#   year | pdf_page | rue | arrondissement | profession_section
#   | full_name_raw | diploma_year | address_raw
#   | phone_raw | hours_raw | specialties_raw
#   | gender_marker_raw | maiden_name_raw | notes_raw | entry_raw
# ══════════════════════════════════════════════════════════════════════
PARIS_RUES_PROMPT = """\
You are analyzing a scanned page from the Rosenwald directory — Paris list organized by street names (par rues).

STARTING CONTEXT
This page may continue the previous page.
If inherited context is provided externally, use it only as a starting default.
Any valid new header on the current page overrides it immediately.

CONTEXT HEADERS (read them to update your context, but never output them as rows)
- Street/boulevard/avenue headers -> update rue.
- Arrondissement indicators if explicitly present -> update arrondissement.
- Section headers (DOCTEURS, OFFICIERS DE SANTE, PHARMACIENS) -> update profession_section.

STRICT STATE MANAGEMENT
Maintain:
rue > arrondissement > profession_section

When a new rue header appears:
- overwrite rue
- reset arrondissement to blank
- reset profession_section to blank

When a new arrondissement indicator appears:
- overwrite arrondissement

When a new profession section header appears:
- overwrite profession_section

PAGE READING STRATEGY
The page may contain two columns.
Read entries in visual reading order by local blocks.
Use the nearest valid header above each entry.
Changing profession_section does not change rue.

IGNORE COMPLETELY (produce nothing for these)
- Advertisements anywhere on the page.
- Page titles, running headers, page numbers.
- Any other non-person line.

TASK
Return TSV only (no markdown, no header row, no code fences, no blank lines).
One line per person entry.

COLUMNS (tab-separated, in this exact order):
year\tpdf_page\true\tarrondissement\tprofession_section\tfull_name_raw\tdiploma_year\taddress_raw\tphone_raw\thours_raw\tspecialties_raw\tgender_marker_raw\tmaiden_name_raw\tnotes_raw\tentry_raw

DEFINITIONS
- rue               : last street/boulevard/avenue/passage header seen, as printed. Carry forward.
- arrondissement    : arrondissement number if explicitly indicated near the street header or entry; else blank.
- profession_section: last section header seen — DOCTEURS, OFFICIERS_DE_SANTE, or PHARMACIENS.
  If no explicit section header is visible for an entry, infer from name prefix when possible.
- full_name_raw     : the person's name exactly as printed, INCLUDING any prefix.
- diploma_year      : 4-digit diploma year if present; else blank.
- address_raw       : street number or building detail if present; else blank.
  Resolve "id." when possible from the same local block.
- phone_raw         : telephone number if present; else blank.
- hours_raw         : consultation hours if present (e.g. "1 a 3", "2 à 4", "Jeu. Dim. Soir"); else blank.
- specialties_raw   : specialties mentioned; else blank.
- gender_marker_raw : copy any explicit gender or marital marker attached to the entry, such as:
  "Dame", "Madame", "Mademoiselle", "Mme", "Mad.", "Mlle", "Melle", "Mme Vve", "veuve", "née".
  If none is explicitly present, leave blank.
- maiden_name_raw   : if the entry explicitly contains "née X", extract X only; otherwise leave blank.
- notes_raw         : titles, affiliations, symbols, distinctions, or other notes; else blank.
- entry_raw         : the complete raw entry text exactly as printed.

IMPORTANT GENDER RULE
Do NOT infer sex from profession, surname, or first name alone.
Only copy explicit markers visible in the entry.

CONSTRAINTS
- year and pdf_page are provided below. Use them exactly in every row.
- If a field is illegible, leave it blank. NEVER invent content.
- Output TSV only. No header row. No blank lines.
- Empty fields must be completely empty (just a tab). NEVER write NULL, null, N/A, or any placeholder.
"""

# ══════════════════════════════════════════════════════════════════════
# 6. MEDECINS DE LA PREFECTURE DE LA SEINE  (1907-1917)
#
# These pages are scanned in LANDSCAPE orientation.
# The image is rotated before being sent to Gemini.
# The page is a SINGLE LIST, not divided into two columns.
#
# TSV columns:
#   year | pdf_page | specialite | full_name_raw | diploma_year
#   | address_raw | phone_raw | hours_raw
#   | gender_marker_raw | maiden_name_raw | notes_raw | entry_raw
# ══════════════════════════════════════════════════════════════════════
PREFECTURE_SEINE_PROMPT = """\
You are analyzing a scanned page from the Rosenwald directory — list of doctors at the Prefecture de la Seine.

IMPORTANT
This page was scanned in landscape format and has been rotated to appear upright.
It is a SINGLE CONTINUOUS LIST, not divided into two columns.

STARTING CONTEXT
This page may continue the previous page.
If inherited context is provided externally, use it only as a starting default.
Any valid new section header on the current page overrides it immediately.

CONTEXT HEADERS (read them to update your context, but never output them as rows)
- Section headers (e.g. "MEDECINS", "CHIRURGIENS") -> update specialite.
- Administrative title lines at the top -> ignore.

IGNORE COMPLETELY (produce nothing for these)
- Advertisements anywhere on the page.
- Page titles, running headers, page numbers.
- Any other non-person line.

TASK
Return TSV only (no markdown, no header row, no code fences, no blank lines).
One line per person entry.

COLUMNS (tab-separated, in this exact order):
year\tpdf_page\tspecialite\tfull_name_raw\tdiploma_year\taddress_raw\tphone_raw\thours_raw\tgender_marker_raw\tmaiden_name_raw\tnotes_raw\tentry_raw

DEFINITIONS
- specialite        : last section or category header seen (e.g. "MEDECINS", "CHIRURGIENS"). Carry forward.
- full_name_raw     : the person's name exactly as printed, INCLUDING any prefix.
- diploma_year      : 4-digit diploma year if present; else blank.
- address_raw       : address if present; else blank.
  Resolve "id." when possible from the same local block.
- phone_raw         : telephone number if present; else blank.
- hours_raw         : consultation hours if present (e.g. "1 a 3", "2 à 4", "Jeu. Dim. Soir"); else blank.
- gender_marker_raw : copy any explicit gender or marital marker attached to the entry, such as:
  "Dame", "Madame", "Mademoiselle", "Mme", "Mad.", "Mlle", "Melle", "Mme Vve", "veuve", "née".
  If none is explicitly present, leave blank.
- maiden_name_raw   : if the entry explicitly contains "née X", extract X only; otherwise leave blank.
- notes_raw         : titles, affiliations, symbols, distinctions, or other notes; else blank.
- entry_raw         : the complete raw entry text exactly as printed.

IMPORTANT GENDER RULE
Do NOT infer sex from profession, surname, or first name alone.
Only copy explicit markers visible in the entry.

CONSTRAINTS
- year and pdf_page are provided below. Use them exactly in every row.
- If a field is illegible, leave it blank. NEVER invent content.
- Output TSV only. No header row. No blank lines.
- Empty fields must be completely empty (just a tab). NEVER write NULL, null, N/A, or any placeholder.
"""

# ══════════════════════════════════════════════════════════════════════
# Dispatch table — list_type -> prompt
# ══════════════════════════════════════════════════════════════════════
PROMPTS: dict = {
    "paris_quartiers":  PARIS_QUARTIERS_PROMPT,
    "deps_cantons":     DEPS_CANTONS_PROMPT,
    "seine_cantons":    DEPS_CANTONS_PROMPT,
    "specialists":      SPECIALISTS_PROMPT,
    "thermal_spas":     THERMAL_SPAS_PROMPT,
    "paris_rues":       PARIS_RUES_PROMPT,
    "bienfaisance":     SPECIALISTS_PROMPT,
    "prefecture_seine": PREFECTURE_SEINE_PROMPT,
}

# Backward-compatible alias used by old test scripts
PARIS_GEO_TSV_PROMPT = PARIS_QUARTIERS_PROMPT


# ══════════════════════════════════════════════════════════════════════
# ABLATION — UNIFIED PROMPT (report §4.3, "étape 2")
#
# A single generic prompt applied to EVERY page regardless of list type.
# No routing, no list-specific schema, no hierarchical context rules.
# Used only to reproduce the step-2 baseline of the ablation in ch. 4.
#
# Generic TSV columns:
#   year | pdf_page | full_name_raw | profession_section | diploma_year
#   | address_raw | city_or_context | hours_raw | notes_raw | entry_raw
# ══════════════════════════════════════════════════════════════════════
UNIFIED_PROMPT = """\
You are analyzing a scanned page from a 19th/early-20th century French medical
directory (Guide Rosenwald). The page lists medical professionals, possibly in
two columns, and may also contain advertisements and section headers.

Extract ONE tab-separated line per professional entry, with EXACTLY these columns:
year\tpdf_page\tfull_name_raw\tprofession_section\tdiploma_year\taddress_raw\tcity_or_context\thours_raw\tnotes_raw\tentry_raw

Rules:
- Read both columns in natural reading order (left column fully, then right).
- Ignore advertisements, prices, and decorative banners.
- Put any visible location cue (quartier, canton, ville, rue, station, specialty
  header) into city_or_context as plain text. Do NOT infer locations from your
  own knowledge — only copy what is printed.
- If a field is missing, leave it empty (just a tab). NEVER invent content.
- entry_raw = the full original line, verbatim.
- Output ONLY tab-separated lines. No header, no markdown, no commentary.
"""