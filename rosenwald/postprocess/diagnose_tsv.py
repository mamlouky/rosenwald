"""
Step 0: Diagnostic — scan all raw TSV files and report column counts.

Usage:
    python -m rosenwald.postprocess.diagnose_tsv
    python -m rosenwald.postprocess.diagnose_tsv --year 1897
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

# Expected column counts per list_type (mirrors TSV_SCHEMA in run_year.py)
EXPECTED_COLS: dict[str, int] = {
    "paris_quartiers":  15,
    "paris_rues":       15,
    "deps_cantons":     13,
    "seine_cantons":    13,
    "specialists":      12,
    "bienfaisance":     12,
    "prefecture_seine": 12,
    "thermal_spas":     10,
}

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def count_cols(line: str) -> int:
    return len(line.split("\t"))


def diagnose_file(path: Path, expected: int) -> tuple[int, int, int]:
    """Returns (total_rows, ok_rows, bad_rows)."""
    total = ok = bad = 0
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            total += 1
            if count_cols(line) == expected:
                ok += 1
            else:
                bad += 1
    except Exception:
        pass
    return total, ok, bad


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=0)
    args = parser.parse_args()

    tsv_root = _PROJECT_ROOT / "data" / "tsv_raw"
    if not tsv_root.exists():
        print(f"[ERROR] Not found: {tsv_root}")
        sys.exit(1)

    # Collect stats per list_type
    stats: dict[str, dict] = defaultdict(lambda: {
        "files": 0, "total_rows": 0, "ok_rows": 0, "bad_rows": 0, "bad_files": []
    })

    years = sorted(tsv_root.iterdir())
    if args.year:
        years = [y for y in years if y.name == str(args.year)]

    for year_dir in years:
        if not year_dir.is_dir():
            continue
        for lt_dir in sorted(year_dir.iterdir()):
            if not lt_dir.is_dir():
                continue
            lt = lt_dir.name
            expected = EXPECTED_COLS.get(lt, -1)
            for tsv in sorted(lt_dir.glob("*.tsv")):
                total, ok, bad = diagnose_file(tsv, expected)
                s = stats[lt]
                s["files"] += 1
                s["total_rows"] += total
                s["ok_rows"] += ok
                s["bad_rows"] += bad
                if bad > 0:
                    s["bad_files"].append(f"{year_dir.name}/{lt}/{tsv.name} ({bad} bad rows)")

    print()
    print("=" * 70)
    print("  DIAGNOSTIC SUMMARY")
    print("=" * 70)
    print(f"  {'list_type':<20} {'expected':>8} {'files':>6} {'rows':>8} {'ok':>8} {'bad':>8}  {'bad%':>6}")
    print("-" * 70)

    total_bad = 0
    for lt in sorted(stats):
        s = stats[lt]
        exp = EXPECTED_COLS.get(lt, "?")
        pct = (s["bad_rows"] / s["total_rows"] * 100) if s["total_rows"] else 0
        total_bad += s["bad_rows"]
        flag = " !" if s["bad_rows"] else ""
        print(f"  {lt:<20} {str(exp):>8} {s['files']:>6} {s['total_rows']:>8} {s['ok_rows']:>8} {s['bad_rows']:>8}  {pct:>5.1f}%{flag}")

    print("=" * 70)
    print(f"  Total bad rows: {total_bad}")
    print()

    if total_bad > 0:
        print("  Files with bad rows (first 20):")
        shown = 0
        for lt in sorted(stats):
            for bf in stats[lt]["bad_files"][:5]:
                print(f"    {lt}: {bf}")
                shown += 1
                if shown >= 20:
                    break
            if shown >= 20:
                break
    print()


if __name__ == "__main__":
    main()
