"""
Restructure raw TSV files via Gemini (Vertex AI) into clean TSVs.

Reads from:  data/tsv_raw/{year}/{list_type}/page-XXXX.tsv
Writes to:   data/tsv_clean/{year}/{list_type}/page-XXXX.tsv

The LLM receives all rows of a page (minus the year/pdf_page columns)
and returns them restructured into the target column schema.
year and page are then re-attached from the original data.

Usage:
    python -m rosenwald.postprocess.restructure_tsv --dry-run          # cost estimate from first 10 files
    python -m rosenwald.postprocess.restructure_tsv                    # full run
    python -m rosenwald.postprocess.restructure_tsv --year 1897
    python -m rosenwald.postprocess.restructure_tsv --year 1897 --list-type deps_cantons
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

from rosenwald.config import Settings

settings = Settings()

# Pricing  (Gemini 2.5 Flash, thinkingBudget=0)
PRICE_INPUT_PER_TOKEN  = 0.15 / 1_000_000   # $0.15 per MTok
PRICE_OUTPUT_PER_TOKEN = 0.60 / 1_000_000   # $0.60 per MTok
SAFETY_CAP_USD = 80.0

# Target column schemas — what the LLM must produce (WITHOUT year/page)
# year and page are re-attached from source after LLM call
LLM_COLS: dict[str, list[str]] = {
    "paris_quartiers":  ["arrondissement", "quartier", "profession", "nom", "annee", "notes", "adresse", "horaires", "sexe"],
    "paris_rues":       ["rue", "nom", "annee", "notes", "adresse", "horaires", "sexe"],
    "deps_cantons":     ["departement", "arrondissement_dept", "canton", "profession", "nom", "annee", "notes", "adresse", "horaires", "sexe"],
    "seine_cantons":    ["departement", "arrondissement_dept", "canton", "profession", "nom", "annee", "notes", "adresse", "horaires", "sexe"],
    "specialists":      ["specialite", "nom", "annee", "notes", "adresse", "horaires", "sexe"],
    "thermal_spas":     ["station", "nom", "annee", "notes", "adresse", "horaires", "sexe"],
    "bienfaisance":     ["institution", "arrondissement", "nom"],
    "prefecture_seine": ["categorie", "nom"],
}

# Full output columns = LLM cols + year + page at end
OUTPUT_COLS: dict[str, list[str]] = {
    lt: cols + ["year", "page"] for lt, cols in LLM_COLS.items()
}

# Prompt templates per list_type
_BASE_RULES = """\
Rules:
- Output ONLY tab-separated lines, one per input entry. No header, no markdown, no explanation.
- If a field is missing or not present, leave it empty (just a tab between adjacent fields).
- Do NOT invent data. Only use what is in the input.
- The 'notes' column: titles, decorations (O, *, croix), positions (AGR., M.A.M., CH.H., Anc. Int. des Hop., Laur. de la Fac., Ex-Int., Med. du Bur. de Bienf.), hospital affiliations, academic titles, and any other qualifications.
- The 'annee' column: ONLY a 4-digit diploma year (e.g. 1885). Empty if absent.
- The 'adresse' column: street names with numbers (rue, boulevard, avenue, place + number).
- The 'horaires' column: consultation days/hours (e.g. Lun. Mer. Ven. 2 a 4, M.J.S. 1 a 3).
- The 'sexe' column: put Mme, Mlle, or Mad. ONLY if the person is explicitly female. Leave empty for males.
- The 'profession' column: DOCTEURS, PHARMACIENS, or OFFICIERS_DE_SANTE.
- Keep all original French text as-is. Do not translate or correct spelling.
- Output exactly ONE line per input line, in the same order.
"""


def _build_prompt(lt: str, raw_content: str) -> str:
    cols = LLM_COLS[lt]
    col_line = "\t".join(cols)
    n = len(cols)

    return (
        "You are restructuring data extracted from a 19th/early 20th century French medical "
        "directory (Guide Rosenwald).\n"
        "Each line below is one entry for a medical professional. "
        "The data may have columns in the wrong order or missing columns.\n\n"
        f"Your task: restructure each line into EXACTLY these {n} tab-separated columns:\n"
        f"{col_line}\n\n"
        + _BASE_RULES
        + "\nRaw data to restructure:\n"
        + raw_content
    )


# Vertex AI auth — shared token with thread-safe refresh
_token_lock   = threading.Lock()
_access_token = ""


def _get_token() -> str:
    global _access_token
    with _token_lock:
        if not _access_token:
            _access_token = _fetch_token()
    return _access_token


def _fetch_token() -> str:
    r = subprocess.run(
        "gcloud auth print-access-token",
        capture_output=True, text=True, check=True, shell=True,
    )
    return r.stdout.strip()


def _refresh_token() -> str:
    global _access_token
    with _token_lock:
        _access_token = _fetch_token()
    return _access_token


# Thread-safe cost counter
_cost_lock          = threading.Lock()
_total_cost_usd     = 0.0
_total_input_tok    = 0
_total_output_tok   = 0
_cap_reached        = False


def _add_cost(input_tok: int, output_tok: int) -> float:
    global _total_cost_usd, _total_input_tok, _total_output_tok
    cost = input_tok * PRICE_INPUT_PER_TOKEN + output_tok * PRICE_OUTPUT_PER_TOKEN
    with _cost_lock:
        _total_cost_usd   += cost
        _total_input_tok  += input_tok
        _total_output_tok += output_tok
        total = _total_cost_usd
    return total


def _check_cap() -> bool:
    with _cost_lock:
        return _total_cost_usd >= SAFETY_CAP_USD


# Gemini REST call
def _call_gemini(prompt: str, timeout_s: int = 120) -> tuple[str, int, int]:
    """Returns (text, input_tokens, output_tokens)."""
    loc   = settings.gcp_location
    proj  = settings.gcp_project
    model = settings.model
    url = (
        f"https://{loc}-aiplatform.googleapis.com/v1"
        f"/projects/{proj}/locations/{loc}"
        f"/publishers/google/models/{model}:generateContent"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }

    for attempt in range(3):
        token = _get_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        try:
            r = requests.post(
                url, headers=headers,
                data=json.dumps(payload), timeout=timeout_s,
            )
        except requests.exceptions.Timeout:
            if attempt < 2:
                time.sleep(15)
                continue
            raise RuntimeError(f"Timeout after {timeout_s}s")

        if r.status_code == 429:
            wait = 60 * (attempt + 1)
            time.sleep(wait)
            continue

        if r.status_code == 401:
            _refresh_token()
            continue

        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:400]}")

        data = r.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text  = "\n".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
        except Exception:
            raise RuntimeError(f"Bad response structure: {json.dumps(data)[:400]}")

        usage = data.get("usageMetadata", {})
        in_tok  = usage.get("promptTokenCount",     0)
        out_tok = usage.get("candidatesTokenCount", 0)
        return text, in_tok, out_tok

    raise RuntimeError("All 3 attempts failed")


# Per-file processing
def process_file(
    tsv_path: Path,
    lt: str,
    out_dir: Path,
    dry_run: bool = False,
) -> dict:
    """
    Process one TSV file. Returns a result dict with stats.
    """
    result = {
        "path": tsv_path,
        "status": "ok",
        "input_rows": 0,
        "output_rows": 0,
        "input_tok": 0,
        "output_tok": 0,
        "cost_usd": 0.0,
        "error": "",
    }

    raw_text = tsv_path.read_text(encoding="utf-8", errors="ignore")
    raw_lines = [l for l in raw_text.splitlines() if l.strip()]
    if not raw_lines:
        result["status"] = "empty"
        return result

    result["input_rows"] = len(raw_lines)

    # Extract year/page from first two columns of first row (same for all rows on page)
    first_parts = raw_lines[0].split("\t")
    year_val = first_parts[0] if first_parts else ""
    page_val = first_parts[1] if len(first_parts) > 1 else ""

    # Strip year/page before sending to LLM
    data_lines = ["\t".join(l.split("\t")[2:]) for l in raw_lines]
    raw_content = "\n".join(data_lines)

    if dry_run:
        # Estimate tokens: ~4 chars per token
        est_in  = len(_build_prompt(lt, raw_content)) // 4
        est_out = len(raw_content) // 4
        result["input_tok"]  = est_in
        result["output_tok"] = est_out
        result["cost_usd"]   = est_in * PRICE_INPUT_PER_TOKEN + est_out * PRICE_OUTPUT_PER_TOKEN
        result["output_rows"] = len(raw_lines)
        return result

    # Check safety cap before calling
    if _check_cap():
        result["status"] = "cap_reached"
        return result

    out_path = out_dir / tsv_path.name

    # Skip already processed
    if out_path.exists() and out_path.stat().st_size > 5:
        result["status"] = "skipped"
        return result

    prompt = _build_prompt(lt, raw_content)
    n_expected = len(LLM_COLS[lt])

    try:
        llm_text, in_tok, out_tok = _call_gemini(prompt)
    except Exception as e:
        # Fallback: save raw rows as-is (padded to target col count)
        result["status"]    = "error_fallback"
        result["error"]     = str(e)
        fallback_lines = []
        for line in raw_lines:
            parts = line.split("\t")[2:]   # strip year/page from raw
            parts = parts[:n_expected] + [""] * max(0, n_expected - len(parts))
            fallback_lines.append("\t".join(parts) + f"\t{year_val}\t{page_val}")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(fallback_lines), encoding="utf-8")
        return result

    # Parse LLM output
    out_lines = [l for l in llm_text.splitlines() if l.strip()]
    result["output_rows"] = len(out_lines)

    if len(out_lines) < len(raw_lines):
        result["status"] = "row_mismatch"
        result["error"]  = f"expected {len(raw_lines)} rows, got {len(out_lines)}"

    # Re-attach year/page, pad/trim to expected col count
    final_lines = []
    for line in out_lines:
        parts = line.split("\t")
        parts = parts[:n_expected] + [""] * max(0, n_expected - len(parts))
        final_lines.append("\t".join(parts) + f"\t{year_val}\t{page_val}")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(final_lines), encoding="utf-8")

    total_cost = _add_cost(in_tok, out_tok)
    result["input_tok"]  = in_tok
    result["output_tok"] = out_tok
    result["cost_usd"]   = in_tok * PRICE_INPUT_PER_TOKEN + out_tok * PRICE_OUTPUT_PER_TOKEN

    return result


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--year",      type=int, default=0)
    parser.add_argument("--list-type", default="")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Process first 10 files and extrapolate total cost")
    args = parser.parse_args()

    tsv_raw_root   = _PROJECT_ROOT / "data" / "tsv_raw"
    tsv_clean_root = _PROJECT_ROOT / "data" / "tsv_clean"

    if not tsv_raw_root.exists():
        print(f"[ERROR] Not found: {tsv_raw_root}")
        sys.exit(1)

    # Collect all files to process
    all_tasks: list[tuple[Path, str, Path]] = []   # (tsv_path, lt, out_dir)

    years = sorted(tsv_raw_root.iterdir())
    if args.year:
        years = [y for y in years if y.name == str(args.year)]

    for year_dir in years:
        if not year_dir.is_dir():
            continue
        lt_dirs = sorted(year_dir.iterdir())
        if args.list_type:
            lt_dirs = [d for d in lt_dirs if d.name == args.list_type]

        for lt_dir in lt_dirs:
            if not lt_dir.is_dir():
                continue
            lt = lt_dir.name
            if lt not in LLM_COLS:
                continue
            out_dir = tsv_clean_root / year_dir.name / lt
            for tsv in sorted(lt_dir.glob("*.tsv")):
                all_tasks.append((tsv, lt, out_dir))

    total_files = len(all_tasks)
    print(f"\nTotal files to process: {total_files}")

    if args.dry_run:
        sample = all_tasks[:10]
        print(f"[DRY RUN] Sampling {len(sample)} files to estimate cost...\n")
        sample_cost = 0.0
        for tsv_path, lt, out_dir in sample:
            r = process_file(tsv_path, lt, out_dir, dry_run=True)
            sample_cost += r["cost_usd"]
            print(f"  {tsv_path.parent.parent.name}/{lt}/{tsv_path.name}: "
                  f"~{r['input_tok']} in / ~{r['output_tok']} out  "
                  f"= ${r['cost_usd']:.4f}")

        avg_cost = sample_cost / len(sample) if sample else 0
        total_est = avg_cost * total_files
        print(f"\n  Sample avg cost/file : ${avg_cost:.4f}")
        print(f"  Estimated total cost : ${total_est:.2f}  ({total_files} files)")
        print(f"  Safety cap           : ${SAFETY_CAP_USD:.0f}")
        if total_est > SAFETY_CAP_USD:
            print(f"  [WARNING] Estimated cost exceeds safety cap of ${SAFETY_CAP_USD:.0f}")
        return

    # Pre-fetch token once before parallel execution
    print("Fetching access token...")
    _get_token()

    # Full run with parallel workers
    print(f"Processing {total_files} files with 10 parallel workers...\n")

    done = skipped = errors = fallbacks = row_mismatches = 0
    log_errors: list[str] = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_task = {
            executor.submit(process_file, tsv_path, lt, out_dir, False): (tsv_path, lt)
            for tsv_path, lt, out_dir in all_tasks
        }

        for i, future in enumerate(as_completed(future_to_task), start=1):
            tsv_path, lt = future_to_task[future]
            try:
                r = future.result()
            except Exception as e:
                errors += 1
                log_errors.append(f"{tsv_path}: unexpected exception: {e}")
                continue

            if r["status"] == "cap_reached":
                print(f"\n[SAFETY CAP REACHED] ${SAFETY_CAP_USD:.0f} limit hit. Stopping.")
                executor.shutdown(wait=False, cancel_futures=True)
                break
            elif r["status"] == "skipped":
                skipped += 1
            elif r["status"] == "empty":
                skipped += 1
            elif r["status"] == "error_fallback":
                fallbacks += 1
                log_errors.append(f"FALLBACK {tsv_path.parent.parent.name}/{lt}/{tsv_path.name}: {r['error']}")
            elif r["status"] == "row_mismatch":
                row_mismatches += 1
                done += 1
                log_errors.append(f"ROW_MISMATCH {tsv_path.parent.parent.name}/{lt}/{tsv_path.name}: {r['error']}")
            else:
                done += 1

            # Print progress every 50 files or on errors
            if i % 50 == 0 or r["status"] not in ("ok", "skipped", "empty"):
                with _cost_lock:
                    cost_now = _total_cost_usd
                print(f"  [{i}/{total_files}] done={done} skip={skipped} "
                      f"err={errors+fallbacks} | "
                      f"running cost: ${cost_now:.3f}")

    # Final summary
    with _cost_lock:
        final_cost = _total_cost_usd
        final_in   = _total_input_tok
        final_out  = _total_output_tok

    print("\n" + "=" * 60)
    print(f"  Files processed : {done}")
    print(f"  Skipped         : {skipped}")
    print(f"  Fallbacks       : {fallbacks}")
    print(f"  Row mismatches  : {row_mismatches}")
    print(f"  Errors          : {errors}")
    print(f"  Input tokens    : {final_in:,}")
    print(f"  Output tokens   : {final_out:,}")
    print(f"  Total cost      : ${final_cost:.4f}")
    print("=" * 60)

    if log_errors:
        log_path = _PROJECT_ROOT / "data" / "restructure_errors.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(log_errors), encoding="utf-8")
        print(f"\n  Error log: {log_path}  ({len(log_errors)} entries)")


if __name__ == "__main__":
    main()
