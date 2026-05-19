"""
Scheduled Monthly Harvest — Agricultural Economics Research Database

This script is designed to run unattended via Windows Task Scheduler on the
1st Tuesday of each month at 9:00 AM EST.  It executes the full data pipeline
(OpenAlex → AgEcon Search → Grey Literature → PDF downloads) and writes a
timestamped report to the `reports/` subfolder.

Usage (manual):
    python scheduled_harvest.py          # Full pipeline + report
    python scheduled_harvest.py --dry    # Report only, no harvest
"""
import os
import sys
import time
import json
import sqlite3
import traceback
from datetime import datetime, timedelta
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

# ── Resolve paths relative to this script ────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

REPORTS_DIR = os.path.join(SCRIPT_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

DB_PATH = os.path.join(SCRIPT_DIR, "ag_econ_research.db")


# ── Helpers ──────────────────────────────────────────────────────────────

def get_db_snapshot():
    """Capture current database metrics for before/after comparison."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    snapshot = {}

    # Total papers
    cur.execute("SELECT COUNT(*) FROM papers")
    snapshot["total_papers"] = cur.fetchone()[0]

    # Papers by source
    cur.execute("SELECT harvest_source, COUNT(*) FROM papers GROUP BY harvest_source")
    snapshot["by_source"] = dict(cur.fetchall())

    # PDFs available
    cur.execute("SELECT COUNT(*) FROM papers WHERE pdf_local_path IS NOT NULL AND pdf_local_path != ''")
    snapshot["total_pdfs"] = cur.fetchone()[0]

    # PDF storage
    cur.execute("SELECT COALESCE(SUM(pdf_size_bytes), 0) FROM papers WHERE pdf_size_bytes > 0")
    snapshot["pdf_bytes"] = cur.fetchone()[0]

    # Papers with abstracts
    cur.execute("SELECT COUNT(*) FROM papers WHERE abstract IS NOT NULL AND abstract != ''")
    snapshot["with_abstracts"] = cur.fetchone()[0]

    # Papers with full text
    cur.execute("SELECT COUNT(*) FROM papers WHERE full_text_extracted = 1")
    snapshot["with_full_text"] = cur.fetchone()[0]

    conn.close()
    return snapshot


def run_phase(name, func, *args, **kwargs):
    """Run a pipeline phase, capturing stdout and timing it."""
    result = {
        "name": name,
        "status": "success",
        "duration_sec": 0,
        "output": "",
        "error": None,
    }

    stdout_capture = StringIO()
    start = time.time()

    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stdout_capture):
            func(*args, **kwargs)
    except Exception as e:
        result["status"] = "FAILED"
        result["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    finally:
        result["duration_sec"] = round(time.time() - start, 1)
        result["output"] = stdout_capture.getvalue()

    return result


def generate_report(before, after, phases, run_start, run_end):
    """Generate a human-readable harvest report."""
    timestamp = run_start.strftime("%Y-%m-%d_%H%M")
    report_filename = f"harvest_report_{timestamp}.txt"
    report_path = os.path.join(REPORTS_DIR, report_filename)

    lines = []
    lines.append("=" * 78)
    lines.append("  AGRICULTURAL ECONOMICS RESEARCH DATABASE — MONTHLY HARVEST REPORT")
    lines.append("=" * 78)
    lines.append("")
    lines.append(f"  Run Started:   {run_start.strftime('%Y-%m-%d %H:%M:%S')} EST")
    lines.append(f"  Run Completed: {run_end.strftime('%Y-%m-%d %H:%M:%S')} EST")
    lines.append(f"  Total Runtime: {(run_end - run_start).total_seconds() / 60:.1f} minutes")
    lines.append("")

    # ── Summary ──
    new_papers = after["total_papers"] - before["total_papers"]
    new_pdfs = after["total_pdfs"] - before["total_pdfs"]
    new_abstracts = after["with_abstracts"] - before["with_abstracts"]

    overall_status = "✓ SUCCESS" if all(p["status"] == "success" for p in phases) else "✗ PARTIAL FAILURE"
    lines.append(f"  OVERALL STATUS: {overall_status}")
    lines.append("")
    lines.append("  ── New Content Added ──")
    lines.append(f"    New papers:        {new_papers:>+6,}")
    lines.append(f"    New PDFs:          {new_pdfs:>+6,}")
    lines.append(f"    New abstracts:     {new_abstracts:>+6,}")
    lines.append("")

    # ── Database Totals ──
    lines.append("  ── Database Totals (After) ──")
    lines.append(f"    Total papers:      {after['total_papers']:>8,}")
    lines.append(f"    Total PDFs:        {after['total_pdfs']:>8,}")
    lines.append(f"    With abstracts:    {after['with_abstracts']:>8,}")
    lines.append(f"    With full text:    {after['with_full_text']:>8,}")
    lines.append(f"    PDF storage:       {after['pdf_bytes'] / (1024**3):>7.2f} GB")
    lines.append("")

    # ── Source-level changes ──
    lines.append("  ── Papers by Source (Before → After) ──")
    all_sources = sorted(set(list(before["by_source"].keys()) + list(after["by_source"].keys())))
    for src in all_sources:
        b = before["by_source"].get(src, 0)
        a = after["by_source"].get(src, 0)
        delta = a - b
        indicator = f"+{delta}" if delta > 0 else str(delta) if delta < 0 else "  ─"
        lines.append(f"    {src or 'unknown':30s}  {b:>6,} → {a:>6,}  ({indicator})")
    lines.append("")

    # ── Phase Details ──
    lines.append("─" * 78)
    lines.append("  PHASE-BY-PHASE DETAILS")
    lines.append("─" * 78)

    for i, phase in enumerate(phases, 1):
        status_icon = "✓" if phase["status"] == "success" else "✗"
        lines.append("")
        lines.append(f"  Phase {i}: {phase['name']}  [{status_icon} {phase['status'].upper()}]")
        lines.append(f"  Duration: {phase['duration_sec']:.1f}s")

        if phase["error"]:
            lines.append(f"  ERROR:")
            for err_line in phase["error"].split("\n")[:10]:
                lines.append(f"    {err_line}")

        # Include key output lines (skip verbose per-paper logs)
        if phase["output"]:
            key_lines = []
            for line in phase["output"].split("\n"):
                line = line.strip()
                if any(kw in line for kw in [
                    "TOTAL", "COMPLETE", "HARVEST", "Found", "added",
                    "skipped", "downloaded", "failed", "ERROR", "WARN",
                    "Phase", "STEP", "papers", "records"
                ]):
                    key_lines.append(line)
            if key_lines:
                lines.append("  Key Output:")
                for kl in key_lines[-20:]:  # Last 20 key lines
                    lines.append(f"    {kl}")

    lines.append("")
    lines.append("=" * 78)
    lines.append(f"  Report saved to: {report_path}")
    lines.append("=" * 78)
    lines.append("")

    report_text = "\n".join(lines)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    return report_path, report_text


# ── Main Execution ───────────────────────────────────────────────────────

def main():
    dry_run = "--dry" in sys.argv

    run_start = datetime.now()
    lookback_date = (run_start - timedelta(days=60)).strftime('%Y-%m-%d')
    print(f"\n{'=' * 70}")
    print(f"  SCHEDULED MONTHLY HARVEST")
    print(f"  {run_start.strftime('%Y-%m-%d %H:%M:%S')} EST")
    print(f"  Incremental Lookback Date: {lookback_date}")
    print(f"{'=' * 70}\n")

    # Snapshot before
    before = get_db_snapshot()
    print(f"  Database before: {before['total_papers']:,} papers, {before['total_pdfs']:,} PDFs\n")

    phases = []

    if not dry_run:
        # ── Phase 1: OpenAlex ──
        print("  [1/4] OpenAlex harvest...")
        from db import init_db
        init_db()

        def run_openalex():
            from openalex_harvester import harvest_openalex
            harvest_openalex(max_per_journal=None, max_per_search=2000, journals_only=False, from_date=lookback_date)

        phases.append(run_phase("OpenAlex Harvest", run_openalex))
        print(f"         → {phases[-1]['status']} ({phases[-1]['duration_sec']:.0f}s)")

        # ── Phase 2: AgEcon Search ──
        print("  [2/4] AgEcon Search harvest...")

        def run_ageconsearch():
            from ageconsearch_harvester import harvest_ageconsearch
            harvest_ageconsearch(max_records=None, from_date=lookback_date)

        phases.append(run_phase("AgEcon Search Harvest", run_ageconsearch))
        print(f"         → {phases[-1]['status']} ({phases[-1]['duration_sec']:.0f}s)")

        # ── Phase 3: Grey Literature ──
        print("  [3/4] Grey Literature harvest...")

        def run_grey_lit():
            from grey_lit_harvester import harvest_grey_lit
            harvest_grey_lit()

        phases.append(run_phase("Grey Literature Harvest", run_grey_lit))
        print(f"         → {phases[-1]['status']} ({phases[-1]['duration_sec']:.0f}s)")

        # ── Phase 4: PDF Downloads ──
        print("  [4/4] PDF downloads...")

        def run_pdf_downloads():
            from config import MAX_PDF_STORAGE_GB
            if MAX_PDF_STORAGE_GB > 0:
                from pdf_downloader import download_pdfs
                download_pdfs(limit=None)
            else:
                print("PDF downloads disabled (MAX_PDF_STORAGE_GB = 0)")

        phases.append(run_phase("PDF Downloads", run_pdf_downloads))
        print(f"         → {phases[-1]['status']} ({phases[-1]['duration_sec']:.0f}s)")

    else:
        print("  [DRY RUN] Skipping harvest — report only\n")

    # Snapshot after
    after = get_db_snapshot()
    run_end = datetime.now()

    # Generate report
    report_path, report_text = generate_report(before, after, phases, run_start, run_end)

    print(f"\n{report_text}")
    print(f"  Report saved to: {report_path}")

    # Return exit code based on overall status
    if any(p["status"] != "success" for p in phases):
        sys.exit(1)


if __name__ == "__main__":
    main()
