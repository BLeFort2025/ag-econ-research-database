"""
Pipeline orchestrator for the Agricultural Economics Research Database.
CLI entry point for running harvests, downloading PDFs, and checking status.

Usage:
    python pipeline.py harvest-openalex [--journals-only] [--max-per-journal N]
    python pipeline.py harvest-ageconsearch [--max-records N]
    python pipeline.py download-pdfs [--limit N] [--tier N]
    python pipeline.py status
    python pipeline.py full [--max-per-journal N] [--max-search N]
"""
import sys
import os
import argparse
from datetime import datetime


def cmd_harvest_openalex(args):
    """Run the OpenAlex metadata harvest."""
    from db import init_db
    from openalex_harvester import harvest_openalex

    init_db()
    harvest_openalex(
        max_per_journal=args.max_per_journal,
        max_per_search=args.max_search,
        journals_only=args.journals_only,
    )


def cmd_harvest_ageconsearch(args):
    """Run the AgEcon Search OAI-PMH harvest."""
    from db import init_db
    from ageconsearch_harvester import harvest_ageconsearch

    init_db()
    harvest_ageconsearch(max_records=args.max_records)


def cmd_download_pdfs(args):
    """Download available open-access PDFs."""
    from pdf_downloader import download_pdfs

    download_pdfs(limit=args.limit, tier=args.tier)


def cmd_status(args):
    """Print database statistics."""
    from db import init_db, get_connection, get_stats
    from config import MAX_PDF_STORAGE_GB

    init_db()
    conn = get_connection()
    stats = get_stats(conn)
    conn.close()

    print("\n" + "=" * 70)
    print("  AGRICULTURAL ECONOMICS RESEARCH DATABASE — STATUS")
    print("=" * 70)

    print(f"\n  Total Papers: {stats['total_papers']:,}")
    yr = stats["year_range"]
    if yr[0]:
        print(f"  Year Range:   {yr[0]} — {yr[1]}")
    print(f"  Open Access:  {stats['open_access']:,}")
    print(f"  Authors:      {stats['unique_authors']:,}")
    print(f"  Topics:       {stats['unique_topics']:,}")

    print(f"\n  ── Papers by Priority Tier ──")
    for tier, count in stats["by_tier"].items():
        bar = "█" * min(count // 50, 40)
        print(f"    {tier:12s}: {count:>6,}  {bar}")

    print(f"\n  ── Papers by Harvest Source ──")
    for source, count in stats["by_source"].items():
        print(f"    {source or 'unknown':18s}: {count:>6,}")

    print(f"\n  ── Top 10 Journals ──")
    for journal, count in stats["top_journals"]:
        name = (journal or "Unknown")[:45]
        print(f"    {name:47s} {count:>5,}")

    print(f"\n  ── PDF Storage ──")
    print(f"    Downloaded:   {stats['pdfs_downloaded']:,} PDFs")
    print(f"    Storage Used: {stats['pdf_storage_gb']:.2f} GB / {MAX_PDF_STORAGE_GB} GB budget")

    if stats["recent_harvests"]:
        print(f"\n  ── Recent Harvests ──")
        for h in stats["recent_harvests"]:
            print(f"    {h['started_at'][:16]}  {h['source']:15s}  +{h['records_added']:,} records  [{h['status']}]")
            if h.get("query_desc"):
                print(f"      └─ {h['query_desc'][:60]}")

    print("\n" + "=" * 70)


def cmd_full(args):
    """Run the full pipeline: OpenAlex → AgEcon Search → PDF downloads."""
    from db import init_db

    init_db()

    print("\n" + "=" * 70)
    print("  FULL PIPELINE RUN")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Phase 1: OpenAlex
    print("\n" + "─" * 70)
    print("  PHASE 1: OpenAlex Harvest")
    print("─" * 70)
    from openalex_harvester import harvest_openalex
    harvest_openalex(
        max_per_journal=args.max_per_journal,
        max_per_search=args.max_search,
        journals_only=args.journals_only,
    )

    # Phase 2: AgEcon Search
    print("\n" + "─" * 70)
    print("  PHASE 2: AgEcon Search Harvest")
    print("─" * 70)
    from ageconsearch_harvester import harvest_ageconsearch
    harvest_ageconsearch(max_records=args.max_ageconsearch)

    # Phase 3: PDF Downloads (if budget > 0)
    from config import MAX_PDF_STORAGE_GB
    if MAX_PDF_STORAGE_GB > 0:
        print("\n" + "─" * 70)
        print("  PHASE 3: PDF Downloads")
        print("─" * 70)
        from pdf_downloader import download_pdfs
        download_pdfs(limit=args.pdf_limit)
    else:
        print("\n[SKIP] PDF downloads disabled (MAX_PDF_STORAGE_GB = 0)")

    # Status
    print("\n" + "─" * 70)
    print("  FINAL STATUS")
    print("─" * 70)
    cmd_status(args)


def main():
    parser = argparse.ArgumentParser(
        description="Agricultural Economics Research Database Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pipeline.py status                    Show database stats
  python pipeline.py harvest-openalex          Harvest from OpenAlex API
  python pipeline.py harvest-ageconsearch      Harvest from AgEcon Search
  python pipeline.py download-pdfs --limit 50  Download 50 PDFs
  python pipeline.py full                      Run everything
        """,
    )
    sub = parser.add_subparsers(dest="command", help="Command to run")

    # harvest-openalex
    p_oa = sub.add_parser("harvest-openalex", help="Harvest from OpenAlex API")
    p_oa.add_argument("--max-per-journal", type=int, default=None, help="Max papers per journal")
    p_oa.add_argument("--max-search", type=int, default=2000, help="Max papers per search term")
    p_oa.add_argument("--journals-only", action="store_true", help="Skip topic-based search")
    p_oa.set_defaults(func=cmd_harvest_openalex)

    # harvest-ageconsearch
    p_ag = sub.add_parser("harvest-ageconsearch", help="Harvest from AgEcon Search OAI-PMH")
    p_ag.add_argument("--max-records", type=int, default=None, help="Max records to harvest")
    p_ag.set_defaults(func=cmd_harvest_ageconsearch)

    # download-pdfs
    p_dl = sub.add_parser("download-pdfs", help="Download open-access PDFs")
    p_dl.add_argument("--limit", type=int, default=None, help="Max PDFs to download")
    p_dl.add_argument("--tier", type=int, choices=[1, 2, 3, 4], help="Only download from this tier")
    p_dl.set_defaults(func=cmd_download_pdfs)

    # status
    p_st = sub.add_parser("status", help="Show database statistics")
    p_st.set_defaults(func=cmd_status)

    # full
    p_full = sub.add_parser("full", help="Run full pipeline")
    p_full.add_argument("--max-per-journal", type=int, default=None, help="Max papers per journal")
    p_full.add_argument("--max-search", type=int, default=2000, help="Max papers per search term")
    p_full.add_argument("--max-ageconsearch", type=int, default=None, help="Max AgEcon Search records")
    p_full.add_argument("--journals-only", action="store_true", help="Skip topic-based search")
    p_full.add_argument("--pdf-limit", type=int, default=None, help="Max PDFs to download")
    p_full.set_defaults(func=cmd_full)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
