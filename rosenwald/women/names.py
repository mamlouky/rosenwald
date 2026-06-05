"""
Name parsing for Rosenwald entries.

A raw name field in the Guides Rosenwald can take many forms.
`parse_name` normalises these into (surname, given, civil) so downstream code
(women workbook, analysis) always works on the same three fields rather than
re-implementing ad-hoc string surgery.
"""
from __future__ import annotations

import re
from typing import NamedTuple


class ParsedName(NamedTuple):
    surname: str   
    given: str     
    civil: str    


# Civil-status tokens.
# Ordered LONGEST-FIRST so that "Mme Vve" matches before "Mme" and
# "Mad. née" before "Mad.".  OCR variants ("Mile" for "Mlle") are included
# because they appear verbatim in the scanned source.
_CIVIL_TOKENS = [
    "Mme Vve", "Mme née", "Mad. née", "Mad née",
    "Mademoiselle", "Madame",
    "Mlle.", "Mlle", "Mile", "Melle",
    "Mad.", "Mad",
    "Mme", "Vve", "Dame", "née", "Sœur", "Soeur",
]

# Profession / title prefixes that can precede the surname, optionally followed
# by a street number (e.g. "Dr 12 Bohn").  Stripped before surname detection.
_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"Dr\.?|Drs\.?|Pr\.?|Prof\.?|M\.|MM\.|"
    r"Ph\.?|Off\.?|"
    r"Sage-?Femme|Sage-?femme"
    r")\b\.?\s*\d*\s*",
    re.IGNORECASE,
)

# A civil token appearing at the very start ("Mme Peltier")
_LEADING_CIVIL_RE = re.compile(
    r"^\s*(" + "|".join(re.escape(t) for t in _CIVIL_TOKENS) + r")\b\.?\s+",
    re.IGNORECASE,
)


# Canonical surface form per civil token (OCR variant "Mile" is kept distinct,
# matching the hand-curated reference workbook).
_CANONICAL = {
    "mme": "Mme", "mme vve": "Mme Vve", "mme née": "Mme née", "mme nee": "Mme née",
    "mad": "Mad.", "mad. née": "Mad. née", "mad née": "Mad. née",
    "madame": "Madame",
    "mlle": "Mlle", "mile": "Mile", "melle": "Melle", "mademoiselle": "Mademoiselle",
    "vve": "Vve", "dame": "Dame", "née": "née", "nee": "née",
    "sœur": "Sœur", "soeur": "Sœur",
}


def _normalise_civil(raw: str) -> str:
    """Map a matched civil substring back to its canonical surface form."""
    low = raw.strip().lower().rstrip(".")
    return _CANONICAL.get(low, raw.strip())


def _split_parenthetical(inside: str) -> tuple[str, str]:
    """
    Split the content of a (...) group into (civil, given).

    "Mme Hél." -> ("Mme", "Hél.")
    "L."       -> ("",    "L.")
    "Mme Vve"  -> ("Mme Vve", "")
    """
    inside = inside.strip()
    if not inside:
        return "", ""

    # Try the longest civil token first at the start of the group
    for tok in _CIVIL_TOKENS:
        m = re.match(re.escape(tok) + r"\b\.?", inside, re.IGNORECASE)
        if m:
            civil = _normalise_civil(m.group(0))
            given = inside[m.end():].strip(" .,")
            # A trailing "Vve"/"née" stays part of civil, not given
            if given.lower() in ("vve", "née", "nee"):
                civil = f"{civil} {given}".strip()
                given = ""
            return civil, given

    # No civil token -> the whole group is a given name / initials
    return "", inside.strip(" .,")


def parse_name(raw_name: str) -> ParsedName:
    """Parse a raw name field into (surname, given, civil)."""
    if not raw_name:
        return ParsedName("", "", "")

    text = raw_name.strip()

    # 0. Strip a leading bare street number
    text = re.sub(r"^\s*\d{1,3}\s+", "", text)

    # 1. Strip a leading profession/title prefix (Dr, Ph., Sage-Femme, "Dr 12"…)
    text = _PREFIX_RE.sub("", text).strip()

    # 2. Civil token written BEFORE the surname ("Mme Peltier")
    civil_lead = ""
    m = _LEADING_CIVIL_RE.match(text)
    if m:
        civil_lead = _normalise_civil(m.group(1))
        text = text[m.end():].strip()

    # 3. Parenthetical group "(Mme Hél.)"
    civil_paren = ""
    given = ""
    pm = re.search(r"\(([^)]*)\)", text)
    if pm:
        civil_paren, given = _split_parenthetical(pm.group(1))
        surname = text[: pm.start()].strip(" ,.")
    else:
        surname = text.strip(" ,.")

    civil = civil_lead or civil_paren

    # 4. Surname cleanup: drop a trailing diploma year if it leaked in
    surname = re.sub(r"\s+\d{4}.*$", "", surname).strip(" ,.")

    return ParsedName(surname, given, civil)
