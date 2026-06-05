
from __future__ import annotations

from typing import NamedTuple, Set

from rosenwald.women.names import parse_name, _CIVIL_TOKENS, _normalise_civil


class WomanEvidence(NamedTuple):
    is_woman: bool
    evidence: str   # the triggering token, e.g. "Mme", "Mlle", "marie", "Sœur"
    source: str     # one of: marker_field, name_civil, first_name, maiden, sister


# Civil-status cues that, on their own, identify a woman.
# (A subset of names._CIVIL_TOKENS — "née"/"Vve" alone are weaker and handled
#  as the `maiden` source so they can be reviewed separately.)
_FEMALE_CIVIL = {
    "mme", "mme vve", "mme née", "mme nee",
    "mad.", "mad", "mad. née", "mad née", "madame",
    "mlle", "mlle.", "mile", "melle", "mademoiselle",
}
_SISTER = {"sœur", "soeur"}
_MAIDEN = {"vve", "née", "nee", "veuve"}


def _civil_in(text: str) -> str:
    """Return the canonical civil token found in `text`, or ''."""
    low = f" {text.lower().strip()} "
    for tok in _CIVIL_TOKENS:  # longest-first
        t = tok.lower()
        if f" {t} " in low or low.strip().startswith(t + " ") or low.strip() == t:
            if t in _FEMALE_CIVIL:
                return _normalise_civil(tok)
    return ""


def _first_name_hit(parsed_given: str, full_name: str, fem_names: Set[str]) -> str:
    """Return the matched feminine first name (lowercased), or ''."""
    candidates = []
    if parsed_given:
        candidates.extend(parsed_given.split())
    # Also scan the whole name in case the given part was not parenthesised
    candidates.extend(full_name.split())
    seen = set()
    for w in candidates:
        cand = w.strip(".,()-").capitalize()
        if cand and cand not in seen:
            seen.add(cand)
            if cand in fem_names:
                return cand.lower()
    return ""


def classify(row: dict, fem_names: Set[str]) -> WomanEvidence:
    """
    Decide whether a merged-TSV row is a woman, and record the evidence.

    Detection cascade (highest-confidence cue first):
      1. dedicated gender-marker field   -> source=marker_field
      2. civil token inside the name      -> source=name_civil
      3. feminine first name              -> source=first_name
      4. maiden / widow marker (Vve, née) -> source=maiden
      5. "Sœur" (nun)                      -> source=sister
    """
    gm = (row.get("gender_marker_raw") or "").strip()
    name = (row.get("full_name_raw") or "").strip()
    maiden = (row.get("maiden_name_raw") or "").strip()
    notes = (row.get("notes_raw") or "").strip()

    # 1. Explicit gender-marker field extracted by the model
    civ = _civil_in(gm)
    if civ:
        return WomanEvidence(True, civ, "marker_field")

    # 2. Civil token embedded in the name field
    parsed = parse_name(name)
    if parsed.civil and parsed.civil.lower() in _FEMALE_CIVIL:
        return WomanEvidence(True, parsed.civil, "name_civil")
    civ = _civil_in(name)
    if civ:
        return WomanEvidence(True, civ, "name_civil")

    # 3. Feminine first name (from the curated first-name list)
    fn = _first_name_hit(parsed.given, name, fem_names)
    if fn:
        return WomanEvidence(True, fn, "first_name")

    # 4. Widow / maiden marker (weaker — flagged for review)
    blob = f"{gm} {name} {maiden} {notes}".lower()
    for tok in _MAIDEN:
        if f" {tok} " in f" {blob} " or maiden:
            return WomanEvidence(True, "née" if "née" in blob or "nee" in blob else "Vve", "maiden")

    # 5. Nun
    for tok in _SISTER:
        if tok in blob:
            return WomanEvidence(True, "Sœur", "sister")

    return WomanEvidence(False, "", "")
