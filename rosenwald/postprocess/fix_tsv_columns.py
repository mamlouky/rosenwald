"""
Fix raw TSV column counts.

Root cause: gender_marker_raw + maiden_name_raw were added mid-project.
Years extracted before that have 1-2 columns fewer than expected.

Strategy per row:
  - expected cols     → keep as-is
  - expected - 2 cols → insert 2 empty cols at gender_marker_raw position
  - expected - 1 cols → insert 1 empty col  at maiden_name_raw position
  - too many cols     → last field (entry_raw) likely contained tabs → rejoin tail
  - 1 col / garbage   → discard

Operates IN-PLACE on data/tsv_raw/ (writes back to same files).
Makes a .bak backup of every file it modifies.

Usage:
    python -m rosenwald.postprocess.fix_tsv_columns
    python -m rosenwald.postprocess.fix_tsv_columns --year 1897
    python -m rosenwald.postprocess.fix_tsv_columns --year 1897 --list-type deps_cantons
    python -m rosenwald.postprocess.fix_tsv_columns --dry-run     # report only, no changes
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Schema: expected column count + insertion point for gender cols
SCHEMA: dict[str, dict] = {
    "deps_cantons":    {"expected": 13, "gender_idx": 9},
    "seine_cantons":   {"expected": 13, "gender_idx": 9},
    "paris_quartiers": {"expected": 15, "gender_idx": 11},
    "paris_rues":      {"expected": 15, "gender_idx": 11},
    "specialists":     {"expected": 12, "gender_idx": 8},
    "bienfaisance":    {"expected": 12, "gender_idx": 8},
    "prefecture_seine":{"expected": 12, "gender_idx": 8},
    "thermal_spas":    {"expected": 10, "gender_idx": 6},
}


def fix_row(parts: list[str], expected: int, gender_idx: int) -> list[str] | None:
    """
    Return a corrected row of exactly `expected` fields, or None to discard.

    The last column is always entry_raw. Missing columns were always added
    just before entry_raw as the schema evolved. So for any under-count,
    we insert (expected - n) empty fields before the last column.

    Discard only truly unparseable rows: fewer than 4 fields, or a single
    blob of text with no tabs at all (Gemini prose / error output).
    """
    n = len(parts)

    if n == expected:
        return parts

    # Too many columns, entry_raw contained literal tabs → rejoin tail
    if n > expected:
        head = parts[:expected - 1]
        tail = "\t".join(parts[expected - 1:])
        return head + [tail]

    # Truly garbage: single blob, or fewer than 4 fields
    if n < 4:
        return None

    # Under-count of any size: insert (expected - n) empty cols before last field
    missing = expected - n
    return parts[:-1] + [""] * missing + [parts[-1]]


def fix_file(path: Path, expected: int, gender_idx: int, dry_run: bool, out_dir: Path | None = None) -> tuple[int, int, int]:
    """
    Fix one TSV file. Writes to out_dir/filename (never modifies path in-place).
    Returns (total_rows, fixed_rows, discarded_rows).
    """
    original = path.read_text(encoding="utf-8", errors="ignore")
    lines = original.splitlines()

    out_lines: list[str] = []
    fixed = discarded = 0

    for line in lines:
        if not line.strip():
            continue
        parts = line.split("\t")
        n = len(parts)

        if n == expected:
            out_lines.append(line)
            continue

        result = fix_row(parts, expected, gender_idx)
        if result is None:
            discarded += 1
        elif len(result) == expected:
            out_lines.append("\t".join(result))
            fixed += 1
        else:
            # Fallback: discard malformed
            discarded += 1

    total = len([l for l in lines if l.strip()])

    if not dry_run and out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / path.name
        out_path.write_text("\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8")

    return total, fixed, discarded


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year",      type=int,  default=0)
    parser.add_argument("--list-type", default="")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Report what would change without modifying files")
    args = parser.parse_args()

    tsv_root  = _PROJECT_ROOT / "data" / "tsv_raw"
    tsv_fixed = _PROJECT_ROOT / "data" / "tsv_fixed"   
    if not tsv_root.exists():
        print(f"[ERROR] Not found: {tsv_root}")
        sys.exit(1)

    mode = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{mode}Reading from data/tsv_raw/  ->  writing to data/tsv_fixed/")
    print("  (tsv_raw files are NEVER modified)")
    print("=" * 60)

    grand_total = grand_fixed = grand_discarded = grand_files = 0

    years = sorted(tsv_root.iterdir())
    if args.year:
        years = [y for y in years if y.name == str(args.year)]

    for year_dir in years:
        if not year_dir.is_dir():
            continue

        lt_dirs = sorted(year_dir.iterdir())
        if args.list_type:
            lt_dirs = [d for d in lt_dirs if d.name == args.list_type]

        year_fixed = year_discarded = 0

        for lt_dir in lt_dirs:
            if not lt_dir.is_dir():
                continue
            lt = lt_dir.name
            cfg = SCHEMA.get(lt)
            if not cfg:
                continue

            expected   = cfg["expected"]
            gender_idx = cfg["gender_idx"]

            for tsv in sorted(lt_dir.glob("*.tsv")):
                out_dir = tsv_fixed / year_dir.name / lt if not args.dry_run else None
                total, fixed, discarded = fix_file(
                    tsv, expected, gender_idx, args.dry_run, out_dir=out_dir
                )
                if fixed > 0 or discarded > 0:
                    print(f"  {year_dir.name}/{lt}/{tsv.name}: "
                          f"{fixed} fixed, {discarded} discarded / {total} rows")
                grand_total     += total
                grand_fixed     += fixed
                grand_discarded += discarded
                grand_files     += 1
                year_fixed      += fixed
                year_discarded  += discarded

        if year_fixed or year_discarded:
            print(f"  >> {year_dir.name} subtotal: {year_fixed} fixed, {year_discarded} discarded")

    print("=" * 60)
    print(f"  Files scanned : {grand_files}")
    print(f"  Rows fixed    : {grand_fixed}")
    print(f"  Rows discarded: {grand_discarded}")
    print(f"  Rows total    : {grand_total}")
    if not args.dry_run and grand_fixed:
        print(f"  Output written to: data/tsv_fixed/")
        print("  data/tsv_raw/ was NOT modified.")
    print()


if __name__ == "__main__":
    main()
