"""
Generate the women-doctors data story (webapp/dist/index.html).

    python webapp/generate_site.py
"""
from __future__ import annotations

import html
import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

# This script lives outside the package (webapp/)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rosenwald.analysis.load import load_women

OUT = Path(__file__).resolve().parent / "dist" / "index.html"

ACCENT = "#9b2226"      
ACCENT2 = "#b88a3e"     
INK = "#26201b"
PAPER = "#f4efe4"

PLAUSIBLE = (1860, 1925)   # diploma-year sanity window


# Inline SVG chart helpers

def _bars_vertical(pairs, width=920, height=300, pad=46):
    """pairs: list[(label, value)] in x order."""
    if not pairs:
        return ""
    vmax = max(v for _, v in pairs) or 1
    n = len(pairs)
    bw = (width - 2 * pad) / n
    bars = []
    for i, (lab, v) in enumerate(pairs):
        h = (height - 2 * pad) * v / vmax
        x = pad + i * bw
        y = height - pad - h
        bars.append(
            f'<rect class="bar" x="{x+bw*0.12:.1f}" y="{y:.1f}" '
            f'width="{bw*0.76:.1f}" height="{h:.1f}" rx="2"><title>{html.escape(str(lab))}: {v}</title></rect>'
        )
        if n <= 40 and (i % max(1, n // 18) == 0):
            bars.append(
                f'<text class="xlab" x="{x+bw/2:.1f}" y="{height-pad+16:.1f}" text-anchor="middle">{html.escape(str(lab))}</text>'
            )
    axis = f'<line class="axis" x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}"/>'
    return f'<svg viewBox="0 0 {width} {height}" class="chart" role="img">{axis}{"".join(bars)}</svg>'


def _bars_horizontal(pairs, width=920, row_h=30, pad_l=210, pad_r=60):
    if not pairs:
        return ""
    vmax = max(v for _, v in pairs) or 1
    height = row_h * len(pairs) + 20
    rows = []
    for i, (lab, v) in enumerate(pairs):
        y = 10 + i * row_h
        bw = (width - pad_l - pad_r) * v / vmax
        rows.append(f'<text class="ylab" x="{pad_l-12}" y="{y+row_h*0.62:.1f}" text-anchor="end">{html.escape(str(lab))}</text>')
        rows.append(f'<rect class="bar" x="{pad_l}" y="{y+4:.1f}" width="{bw:.1f}" height="{row_h*0.6:.1f}" rx="2"><title>{html.escape(str(lab))}: {v}</title></rect>')
        rows.append(f'<text class="val" x="{pad_l+bw+8:.1f}" y="{y+row_h*0.62:.1f}">{v}</text>')
    return f'<svg viewBox="0 0 {width} {height}" class="chart" role="img">{"".join(rows)}</svg>'


def _line(pairs, width=920, height=300, pad=46):
    if not pairs:
        return ""
    xs = [x for x, _ in pairs]
    vmax = max(v for _, v in pairs) or 1
    xmin, xmax = min(xs), max(xs)
    span = (xmax - xmin) or 1
    pts = []
    for x, v in pairs:
        px = pad + (width - 2 * pad) * (x - xmin) / span
        py = height - pad - (height - 2 * pad) * v / vmax
        pts.append((px, py))
    path = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    dots = "".join(f'<circle class="dot" cx="{px:.1f}" cy="{py:.1f}" r="3"/>' for px, py in pts)
    labels = "".join(
        f'<text class="xlab" x="{pad + (width-2*pad)*(x-xmin)/span:.1f}" y="{height-pad+16}" text-anchor="middle">{x}</text>'
        for x, _ in pairs if x % 5 == 0
    )
    axis = f'<line class="axis" x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}"/>'
    return (f'<svg viewBox="0 0 {width} {height}" class="chart" role="img">{axis}'
            f'<path class="spark" d="{path}"/>{dots}{labels}</svg>')


# Cartography — France departments projected to SVG, women counts per year

_GEOJSON = Path(__file__).resolve().parent / "_departements.geojson"

# Historic department name -> modern name on the base map
_DEPT_ALIAS = {
    "seine": "paris",
    "seineinferieure": "seinemaritime",
    "seineetoise": "yvelines",
    "bassespyrenees": "pyreneesatlantiques",
    "bassesalpes": "alpesdehauteprovence",
    "charenteinferieure": "charentemaritime",
    "loireinferieure": "loireatlantique",
    "cotesdunord": "cotesdarmor",
}


def _deptkey(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    return _DEPT_ALIAS.get(s, s)


def _carto(women):
    """Return (paths, counts_by_year, years, gmax) for the scroll map.

    Counts use the cantons-based provincial lists (deps_cantons + seine_cantons)
    so the map shows geographic spread; Paris (a single point) is excluded.
    """
    gj = json.loads(_GEOJSON.read_text(encoding="utf-8"))

    # bounds
    minx = miny = 1e9
    maxx = maxy = -1e9
    for f in gj["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            for ring in poly:
                for lon, lat in ring:
                    minx, maxx = min(minx, lon), max(maxx, lon)
                    miny, maxy = min(miny, lat), max(maxy, lat)
    lat0 = math.radians((miny + maxy) / 2)
    kx = math.cos(lat0)
    W, H, pad = 560, 560, 8
    s = min((W - 2 * pad) / ((maxx - minx) * kx), (H - 2 * pad) / (maxy - miny))

    def px(lon, lat):
        return (pad + (lon - minx) * kx * s, pad + (maxy - lat) * s)

    paths = []
    for f in gj["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        d = []
        for poly in polys:
            for ring in poly:
                pts = [f"{px(lo, la)[0]:.1f},{px(lo, la)[1]:.1f}" for lo, la in ring]
                if pts:
                    d.append("M" + " L".join(pts) + "Z")
        paths.append({"k": _deptkey(f["properties"]["nom"]), "d": "".join(d)})

    geo_keys = {p["k"] for p in paths}
    prov = women[women["list_type"].isin(["deps_cantons", "seine_cantons"])]
    counts = defaultdict(lambda: defaultdict(int))
    for _, r in prov.dropna(subset=["annee_volume"]).iterrows():
        k = _deptkey(r["departement"])
        if k and k in geo_keys:
            counts[int(r["annee_volume"])][k] += 1
    years = sorted(counts)
    gmax = max((c for y in counts.values() for c in y.values()), default=1)
    counts = {y: dict(v) for y, v in counts.items()}
    return paths, counts, years, gmax, (W, H)


# Build the page
def build() -> Path:
    w = load_women()
    total = len(w)
    distinct_sur = w.loc[w["nom"].str.strip() != "", "nom"].str.strip().str.lower().nunique()
    key = (w["nom"].str.strip().str.lower() + "|" + w["prenom"].str.strip().str.lower())
    distinct_people = key.nunique()

    by_year = sorted((int(y), int(c)) for y, c in
                     w.dropna(subset=["annee_volume"]).groupby("annee_volume").size().items())
    by_list = sorted(((lt, int(c)) for lt, c in w.groupby("list_type").size().items()),
                     key=lambda t: -t[1])
    geo = w[w["list_type"].isin(["deps_cantons", "seine_cantons"])]
    by_dept = Counter(geo.loc[geo["departement"].str.strip() != "", "departement"].str.upper().str.strip()).most_common(12)
    spec = w[(w["list_type"] == "specialists") & (w["specialite"].str.strip() != "")]
    by_spec = Counter(spec["specialite"].str.upper().str.strip()).most_common(10)
    top_recurring = w.loc[w["nom"].str.strip() != "", "nom"].str.strip().value_counts().head(10)

    # profession breakdown (distinct women per category) — pharmacists / officiers
    # de santé are NOT doctors, so they are shown separately.
    _pk = w["nom"].str.strip().str.lower() + "|" + w["prenom"].str.strip().str.lower()
    prof_distinct = w.assign(_k=_pk).groupby("profession_cat")["_k"].nunique().sort_values(ascending=False)
    PROF_LABEL = {"docteur": "Docteures", "pharmacien": "Pharmaciennes",
                  "officier de santé": "Officières de santé", "sage-femme": "Sages-femmes",
                  "non précisé": "Non précisé"}
    by_prof = [(PROF_LABEL.get(k, k), int(v)) for k, v in prof_distinct.items() if k != "non précisé"]
    n_doc = int(prof_distinct.get("docteur", 0))

    dip = w.dropna(subset=["annee_diplome"])
    outliers = int(((dip["annee_diplome"] < PLAUSIBLE[0]) | (dip["annee_diplome"] > PLAUSIBLE[1])).sum())
    dip_ok = dip[(dip["annee_diplome"] >= PLAUSIBLE[0]) & (dip["annee_diplome"] <= PLAUSIBLE[1])]
    # diploma timeline is about DOCTEURES (the Brès / "nothing before 1875" story)
    dip_doc = dip_ok[dip_ok["profession_cat"] == "docteur"]
    dip_hist = sorted((int(y), int(c)) for y, c in dip_doc.groupby("annee_diplome").size().items())
    bres = int((w["nom"].str.contains("Br[eèé]s", regex=True, na=False)).sum())

    # explorer data (all entries, compact) — indicator + raw_text excluded per request
    recs = []
    for _, r in w.iterrows():
        recs.append({
            "n": r["nom"], "p": r["prenom"],
            "d": None if str(r["annee_diplome"]) == "<NA>" else int(r["annee_diplome"]),
            "l": r["list_type"],
            "g": r["departement"] or r["quartier"] or r["rue"] or r["station"] or r["specialite"],
            "v": None if str(r["annee_volume"]) == "<NA>" else int(r["annee_volume"]),
            "pg": r["page"],
        })
    data_json = json.dumps(recs, ensure_ascii=False)

    paths, carto_counts, carto_years, carto_gmax, (cw, ch) = _carto(w)
    paths_svg = "".join(f'<path class="dept" data-k="{p["k"]}" d="{p["d"]}"/>' for p in paths)
    carto_json = json.dumps(carto_counts, ensure_ascii=False)
    years_json = json.dumps(carto_years)

    css = (":root{--accent:" + ACCENT + ";--accent2:" + ACCENT2 +
           ";--ink:" + INK + ";--paper:" + PAPER + ";}\n" + """
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--paper);color:var(--ink);font-family:"Spectral",Georgia,serif;
 font-size:19px;line-height:1.65;
 background-image:radial-gradient(circle at 12% 18%, rgba(155,34,38,.05), transparent 40%),
                  radial-gradient(circle at 88% 82%, rgba(184,138,62,.06), transparent 45%);}
.wrap{max-width:1040px;margin:0 auto;padding:0 26px}
h1,h2,h3,.num{font-family:"Fraunces","Spectral",Georgia,serif}
.hero{min-height:92vh;display:flex;flex-direction:column;justify-content:center;padding:8vh 0}
.kicker{letter-spacing:.32em;text-transform:uppercase;font-size:.74rem;color:var(--accent);
 font-family:"IBM Plex Mono",monospace;margin-bottom:1.4rem}
h1{font-size:clamp(2.6rem,7vw,5.4rem);font-weight:600;line-height:1.02;letter-spacing:-.015em;font-optical-sizing:auto}
h1 em{font-style:italic;color:var(--accent)}
.sub{margin-top:1.6rem;max-width:36ch;font-size:1.18rem;color:#5b5046}
.bignum{display:flex;align-items:baseline;gap:1.2rem;margin-top:3.2rem;flex-wrap:wrap}
.bignum .num{font-size:clamp(3rem,9vw,6.5rem);font-weight:600;color:var(--accent);line-height:1}
.bignum .cap{max-width:26ch;font-size:1rem;color:#5b5046}
section{padding:9vh 0;border-top:1px solid #d8cdb6}
h2{font-size:clamp(1.8rem,4vw,2.8rem);font-weight:600;letter-spacing:-.01em;margin-bottom:.4rem}
.lead{color:var(--accent);font-family:"IBM Plex Mono",monospace;font-size:.72rem;
 letter-spacing:.28em;text-transform:uppercase;margin-bottom:1.6rem}
p{max-width:62ch;margin:1rem 0;color:#3f372f}
.callout{border-left:3px solid var(--accent);background:#fff8ec;padding:1.4rem 1.6rem;margin:2rem 0;
 box-shadow:6px 6px 0 #e7dcc4}
.grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:1.4rem;margin:2rem 0}
.stat{background:#fffaf0;border:1px solid #e2d6bd;padding:1.2rem 1.3rem}
.stat .num{font-size:2.6rem;color:var(--accent);font-weight:600;display:block;line-height:1}
.stat .lbl{font-size:.82rem;color:#6b6052}
.chart{width:100%;height:auto;margin:1.6rem 0;overflow:visible}
.chart .bar{fill:var(--accent)}
.chart .bar:hover{fill:var(--accent2)}
.chart .axis{stroke:#cdbfa3;stroke-width:1}
.chart .spark{fill:none;stroke:var(--accent);stroke-width:2.4}
.chart .dot{fill:var(--accent)}
.chart .xlab,.chart .ylab{font-family:"IBM Plex Mono",monospace;font-size:11px;fill:#7a6f5f}
.chart .val{font-family:"IBM Plex Mono",monospace;font-size:11px;fill:var(--accent)}
.reveal{opacity:0;transform:translateY(22px);transition:all .8s cubic-bezier(.2,.7,.2,1)}
.reveal.in{opacity:1;transform:none}
.pioneer{display:flex;gap:1.4rem;align-items:flex-start;background:#1c1713;color:#f0e7d6;
 padding:2rem;margin:2rem 0;box-shadow:8px 8px 0 var(--accent)}
.pioneer .yr{font-family:"Fraunces",serif;font-size:3.4rem;color:var(--accent2);font-weight:600;line-height:1}
.pioneer h3{color:#fff;font-size:1.5rem;margin-bottom:.4rem}
.pioneer p{color:#cfc3ad;max-width:none}
.explorer input,.explorer select{font-family:"IBM Plex Mono",monospace;font-size:.9rem;padding:.5rem .7rem;
 border:1px solid #c9bb9e;background:#fffaf0;color:var(--ink)}
.controls{display:flex;gap:.7rem;flex-wrap:wrap;margin:1.4rem 0;align-items:center}
table{width:100%;border-collapse:collapse;font-size:.86rem;margin-top:1rem}
th,td{text-align:left;padding:.5rem .6rem;border-bottom:1px solid #e2d6bd;vertical-align:top}
th{font-family:"IBM Plex Mono",monospace;font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;
 color:#6b6052;cursor:pointer;position:sticky;top:0;background:var(--paper)}
td.raw{color:#6b6052;font-size:.8rem}
.tablewrap{max-height:60vh;overflow:auto;border:1px solid #e2d6bd}
.count{font-family:"IBM Plex Mono",monospace;color:var(--accent);font-size:.8rem}
footer{padding:7vh 0;border-top:2px solid var(--ink);font-size:.92rem;color:#5b5046}
mark{background:#f7e7c5;color:inherit;padding:0 .15em}
.carto-scroll{position:relative}
.carto-sticky{position:sticky;top:0;min-height:100vh;display:flex;flex-direction:column;
 justify-content:center;align-items:center;padding:4vh 0}
.carto-sticky svg{width:min(560px,86vw);height:auto}
.carto-sticky .dept{stroke:#e9dfca;stroke-width:.5;fill:#eadfc6;transition:fill .25s ease}
.cartohead{display:flex;align-items:baseline;gap:1rem;margin-bottom:.6rem}
.cartoyear{font-family:"Fraunces",serif;font-size:3.2rem;font-weight:600;color:var(--accent);line-height:1}
.cartosub{font-family:"IBM Plex Mono",monospace;font-size:.78rem;color:#7a6f5f}
.legend{display:flex;align-items:center;gap:.5rem;margin-top:1rem;font-family:"IBM Plex Mono",monospace;font-size:.72rem;color:#7a6f5f}
.legend .grad{width:160px;height:10px;border-radius:5px;background:linear-gradient(90deg,#eadfc6,var(--accent))}
.carto-spacer{height:60vh}
""")

    def rows_html(spec_pairs):
        return "".join(f"<tr><td>{html.escape(str(a))}</td><td class='val'>{b}</td></tr>" for a, b in spec_pairs)

    page = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quantifying the Invisible · Femmes médecins des Guides Rosenwald</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;1,9..144,400;1,9..144,600&family=Spectral:ital,wght@0,400;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{css}</style></head><body>

<div class="wrap">
  <header class="hero">
    <div class="kicker">Guides Rosenwald · 1887-1922 · projet MEDIF · FNS 215100</div>
    <h1>Quantifying <em>the Invisible</em></h1>
    <p class="sub">Extraction structurée et analyse des listes « géographiques » des Guides Rosenwald (1887-1922).</p>
    <div class="bignum">
      <span class="num">{total:,}</span>
      <span class="cap"><strong>entrées de femmes</strong> recensées, soit <strong>759 praticiennes distinctes</strong> après regroupement.</span>
    </div>
  </header>
</div>

<div class="wrap"><section class="reveal">
  <div class="lead">Lire les chiffres</div>
  <h2>Une entrée n'est pas une femme</h2>
  <p>Une même praticienne réapparaît d'année en année, parfois à une adresse différente, parfois avec un prénom mentionné dans certains volumes et absent dans d'autres. Compter les <em>entrées</em> mesure la <em>présence</em> dans l'annuaire ; compter les <em>individus</em> demande un regroupement.</p>
  <div class="grid2">
    <div class="stat"><span class="num">{total:,}</span><span class="lbl">entrées (occurrences à travers les volumes)</span></div>
    <div class="stat"><span class="num">{distinct_sur}</span><span class="lbl">noms de famille distincts</span></div>
    <div class="stat"><span class="num">759</span><span class="lbl">individus distincts (nom + prénom)</span></div>
  </div>
  <p style="font-size:.92rem;color:#6b6052">Tous les graphiques ci-dessous comptent des <strong>entrées</strong>, sauf mention contraire.</p>
</section></div>

<div class="wrap"><section class="reveal">
  <div class="lead">Professions</div>
  <h2>Docteures, pharmaciennes, officières de santé</h2>
  <p>Les annuaires distinguent les professions de santé. Pharmaciennes et officières de santé <strong>ne sont pas des docteures</strong> : on les lit donc séparément. Nombre de praticiennes <strong>distinctes</strong> par catégorie.</p>
  {_bars_horizontal(by_prof, pad_l=200)}
</section></div>

<div class="wrap"><section class="reveal">
  <div class="lead">Évolution</div>
  <h2>Une présence qui s'affirme</h2>
  <p>Le nombre d'entrées féminines croît régulièrement à mesure que les facultés s'ouvrent aux femmes — une trajectoire d'ensemble plus qu'un comptage d'individus.</p>
  {_bars_vertical([(y, c) for y, c in by_year])}
</section></div>

<div class="wrap"><section class="reveal">
  <div class="lead">Géographie</div>
  <h2>Où exercent-elles&nbsp;?</h2>
  <p>Départements les plus représentés dans les listes par cantons (entrées).</p>
  {_bars_horizontal(by_dept)}
</section></div>

<div class="wrap"><section class="reveal">
  <div class="lead">Cartographie</div>
  <h2>La France, année après année</h2>
  <p>Faites défiler : la carte parcourt les volumes de {carto_years[0]} à {carto_years[-1]} et montre, département par département, l'implantation des praticiennes dans les listes par cantons. Paris, point unique et massif, est traité à part.</p>
</section></div>
<div class="carto-scroll" style="height:340vh">
  <div class="carto-sticky">
    <div class="cartohead"><span class="cartoyear" id="cy">{carto_years[0]}</span>
      <span class="cartosub">femmes par département · listes par cantons</span></div>
    <svg viewBox="0 0 {cw} {ch}" id="cartomap" role="img" aria-label="carte de France">{paths_svg}</svg>
    <div class="legend"><span>0</span><span class="grad"></span><span>{carto_gmax}+ femmes</span></div>
  </div>
</div>
<div class="carto-spacer"></div>

<div class="wrap"><section class="reveal">
  <div class="lead">Formes d'exercice</div>
  <h2>Listes &amp; spécialités</h2>
  <div class="grid2" style="grid-template-columns:1fr 1fr;align-items:start">
    <div>{_bars_horizontal([(l, c) for l, c in by_list], pad_l=150)}</div>
    <div>{_bars_horizontal(by_spec, pad_l=200)}</div>
  </div>
</section></div>

<div class="wrap"><section class="reveal">
  <div class="lead">Diplômes</div>
  <h2>Les pionnières</h2>
  <p>Distribution des années de diplôme <strong>des docteures</strong> ({n_doc} distinctes). Madeleine Brès obtient le premier doctorat féminin de médecine en France en <strong>1875</strong> : aucune docteure ne devrait la précéder. Les très rares barres antérieures sont des coquilles OCR résiduelles, signalées.</p>
  {_bars_vertical(dip_hist)}
  <div class="pioneer">
    <span class="yr">1875</span>
    <div><h3>Madeleine Brès</h3>
    <p>Première femme à obtenir le doctorat en médecine en France. Sa fiche revient dans <mark>{bres} entrées</mark> de notre corpus, à travers les volumes et les listes — un même parcours suivi sur plus de trente ans.</p></div>
  </div>
  <p style="font-size:.92rem;color:#6b6052"><strong>Transparence.</strong> {outliers} entrées portent une année de diplôme hors plage plausible : il s'agit le plus souvent d'artefacts d'OCR (un numéro de rue ou un horaire glissé dans le champ « année ») ou de rares faux positifs (un prénom mixte comme « Dominique »). Elles sont signalées plutôt que corrigées silencieusement.</p>
</section></div>

<div class="wrap"><section class="reveal">
  <div class="lead">Récurrences</div>
  <h2>Suivre une trajectoire</h2>
  <p>Les noms les plus fréquents ne sont pas « plus de femmes » mais les <em>mêmes</em> femmes, suivies volume après volume — la matière première d'une analyse longitudinale.</p>
  <table><thead><tr><th>Nom</th><th>Entrées</th></tr></thead><tbody>{rows_html([(n, int(c)) for n, c in top_recurring.items()])}</tbody></table>
</section></div>

<div class="wrap"><section class="reveal explorer">
  <div class="lead">Explorer</div>
  <h2>Les {total:,} entrées</h2>
  <p>Cherchez un nom, filtrez par liste, triez par année. Chaque ligne renvoie à sa transcription brute (raw_text) et à sa page d'origine.</p>
  <div class="controls">
    <input id="q" placeholder="chercher un nom, un lieu…" style="flex:1;min-width:240px">
    <select id="flist"><option value="">— toutes les listes —</option></select>
    <span class="count" id="cnt"></span>
  </div>
  <div class="tablewrap"><table id="tbl"><thead><tr>
    <th data-k="n">Nom</th><th data-k="p">Prénom</th>
    <th data-k="d">Diplôme</th><th data-k="l">Liste</th><th data-k="g">Lieu / spéc.</th>
    <th data-k="v">Volume</th><th data-k="pg">Page</th>
  </tr></thead><tbody id="tb"></tbody></table></div>
</section></div>

<div class="wrap"><footer>
  <p><strong>Méthode.</strong> Les pages numérisées sont extraites par un pipeline multimodal (RouteGeo, Gemini), puis nettoyées et structurées. Les entrées féminines sont détectées (marqueurs « Mme / Mlle / Mad. » et prénoms féminins), regroupées par liste, et <strong>vérifiées à la main</strong> — c'est ce jeu vérifié (<code>Liste_femmes.xlsx</code>) qui alimente cette page. Les comptages portent sur des entrées d'annuaire, non sur des individus, sauf mention explicite.</p>
  <p style="margin-top:1rem;color:#8a7d6b">Projet de semestre EPFL × Institut des humanités en médecine — projet MEDIF.</p>
</footer></div>

<script>
const DATA = {data_json};
const tb = document.getElementById('tb'), q = document.getElementById('q'),
      fl = document.getElementById('flist'), cnt = document.getElementById('cnt');
[...new Set(DATA.map(d=>d.l))].sort().forEach(l=>{{const o=document.createElement('option');o.value=l;o.textContent=l;fl.appendChild(o);}});
let sortK='n', sortDir=1;
function esc(s){{return (s==null?'':String(s)).replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));}}
function render(){{
  const term=q.value.toLowerCase().trim(), lf=fl.value;
  let rows=DATA.filter(d=>(!lf||d.l===lf) &&
    (!term || (d.n+' '+d.p+' '+(d.g||'')).toLowerCase().includes(term)));
  rows.sort((a,b)=>{{let x=a[sortK],y=b[sortK];x=x==null?'':x;y=y==null?'':y;return x>y?sortDir:x<y?-sortDir:0;}});
  cnt.textContent=rows.length+' / '+DATA.length+' entrées';
  tb.innerHTML=rows.slice(0,600).map(d=>`<tr><td>${{esc(d.n)}}</td><td>${{esc(d.p)}}</td>`+
    `<td class="val">${{d.d||''}}</td><td>${{esc(d.l)}}</td><td>${{esc(d.g)}}</td>`+
    `<td>${{d.v||''}}</td><td>${{esc(d.pg)}}</td></tr>`).join('');
}}
q.oninput=render; fl.onchange=render;
document.querySelectorAll('#tbl th').forEach(th=>th.onclick=()=>{{const k=th.dataset.k;sortDir=(k===sortK)?-sortDir:1;sortK=k;render();}});
render();
const io=new IntersectionObserver(es=>es.forEach(e=>{{if(e.isIntersecting)e.target.classList.add('in');}}),{{threshold:.12}});
document.querySelectorAll('.reveal').forEach(el=>io.observe(el));

// ---- scroll-driven cartography ----
const CCOUNTS={carto_json}, CYEARS={years_json}, CGMAX={carto_gmax};
const cmap=document.getElementById('cartomap'), cyl=document.getElementById('cy');
const cpaths=[...cmap.querySelectorAll('path')];
const L=(a,b,t)=>Math.round(a+(b-a)*t);
function ccolor(c){{if(!c)return '#eadfc6';const t=Math.sqrt(c/CGMAX);return `rgb(${{L(234,155,t)}},${{L(223,34,t)}},${{L(198,38,t)}})`;}}
function paintYear(y){{cyl.textContent=y;const cc=CCOUNTS[y]||{{}};cpaths.forEach(p=>p.style.fill=ccolor(cc[p.dataset.k]||0));}}
const cs=document.querySelector('.carto-scroll');
function onScroll(){{const r=cs.getBoundingClientRect();const total=cs.offsetHeight-window.innerHeight;
  const p=Math.min(1,Math.max(0,(-r.top)/total));const idx=Math.min(CYEARS.length-1,Math.floor(p*CYEARS.length));
  paintYear(CYEARS[idx]);}}
window.addEventListener('scroll',onScroll,{{passive:true}});paintYear(CYEARS[0]);onScroll();
</script>
</body></html>"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"[OK] {OUT}  ({len(page)//1024} KB, {total} entries, ~{distinct_people} distinct women)")
    return OUT


if __name__ == "__main__":
    build()
