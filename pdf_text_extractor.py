"""
PDF Text Extractor for the Agricultural Economics Research Database.
Uses PyMuPDF (fitz) to extract full text from downloaded PDFs and store
it in the SQLite database for enhanced semantic search.
"""
import os
import re
import time
import sys
from db import get_connection, update_paper_full_text, init_db


def clean_extracted_text(raw_text):
    """Clean up raw PDF text extraction artifacts."""
    if not raw_text:
        return None

    text = raw_text

    # Fix common ligature artifacts
    ligature_map = {
        "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
    }
    for lig, replacement in ligature_map.items():
        text = text.replace(lig, replacement)

    # Collapse excessive whitespace (but preserve paragraph breaks)
    text = re.sub(r"[ \t]+", " ", text)  # Multiple spaces/tabs → single space
    text = re.sub(r"\n{4,}", "\n\n\n", text)  # 4+ newlines → 3
    text = re.sub(r"(\n\s*){3,}", "\n\n", text)  # Excessive blank lines → double

    # Remove page number lines (common pattern: standalone numbers)
    text = re.sub(r"\n\s*\d{1,3}\s*\n", "\n", text)

    # Strip leading/trailing whitespace
    text = text.strip()

    return text if len(text) > 50 else None  # Reject very short extractions


def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file using PyMuPDF. Returns cleaned text or None."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("[ERROR] PyMuPDF not installed. Run: pip install PyMuPDF")
        sys.exit(1)

    try:
        doc = fitz.open(pdf_path)
        pages_text = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text("text")
            if page_text:
                pages_text.append(page_text)

        doc.close()

        full_text = "\n\n".join(pages_text)
        return clean_extracted_text(full_text)

    except Exception as e:
        print(f"    [ERROR] Failed to extract text: {e}")
        return None


def extract_all(limit=None, tier_filter=None, force=False):
    """
    Extract full text from all downloaded PDFs that haven't been processed yet.

    Args:
        limit: Max number of PDFs to process (None = all)
        tier_filter: Only process papers from this tier (1-4)
        force: Re-extract even if already extracted
    """
    conn = get_connection()

    # Build query for papers with downloaded PDFs
    query = """
        SELECT id, title, pdf_local_path, priority_tier, year
        FROM papers
        WHERE pdf_local_path IS NOT NULL
    """
    params = []

    if not force:
        query += " AND (full_text_extracted = 0 OR full_text_extracted IS NULL)"

    if tier_filter is not None:
        query += " AND priority_tier = ?"
        params.append(tier_filter)

    # Process highest-priority papers first
    query += " ORDER BY priority_tier ASC, citation_count DESC"

    if limit:
        query += f" LIMIT {int(limit)}"

    papers = conn.execute(query, params).fetchall()
    total = len(papers)

    print(f"\n{'=' * 70}")
    print(f"  PDF TEXT EXTRACTION")
    print(f"{'=' * 70}")
    print(f"  Papers to process: {total}")
    if tier_filter:
        tier_names = {1: "Canadian", 2: "US", 3: "OECD", 4: "Global"}
        print(f"  Filter: Tier {tier_filter} ({tier_names.get(tier_filter, '?')}) only")
    print()

    if total == 0:
        print("  [DONE] No papers need text extraction.")
        conn.close()
        return 0, 0

    extracted = 0
    failed = 0
    total_chars = 0
    start_time = time.time()

    for i, paper in enumerate(papers, 1):
        pdf_path = paper["pdf_local_path"]

        # Check file exists
        if not os.path.exists(pdf_path):
            print(f"  [{i}/{total}] MISSING: {pdf_path}")
            update_paper_full_text(conn, paper["id"], None, status=-1)
            failed += 1
            continue

        # Extract text
        full_text = extract_text_from_pdf(pdf_path)

        if full_text:
            update_paper_full_text(conn, paper["id"], full_text, status=1)
            extracted += 1
            total_chars += len(full_text)

            # Progress report every 10 papers
            if i % 10 == 0 or i == total:
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                eta = (total - i) / rate if rate > 0 else 0
                avg_chars = total_chars // extracted if extracted > 0 else 0
                print(
                    f"  [{i}/{total}] Extracted: {extracted} | Failed: {failed} | "
                    f"Avg: {avg_chars:,} chars | {rate:.1f} papers/sec | ETA: {eta:.0f}s"
                )
        else:
            update_paper_full_text(conn, paper["id"], None, status=-1)
            failed += 1

        # Commit every 50 papers
        if i % 50 == 0:
            conn.commit()

    conn.commit()
    conn.close()

    elapsed = time.time() - start_time
    avg_chars = total_chars // extracted if extracted > 0 else 0

    print(f"\n{'=' * 70}")
    print(f"  TEXT EXTRACTION COMPLETE")
    print(f"  Extracted: {extracted:,} papers ({total_chars:,} total characters)")
    print(f"  Average: {avg_chars:,} chars per paper")
    print(f"  Failed: {failed:,}")
    print(f"  Time: {elapsed:.1f}s")
    print(f"{'=' * 70}")

    return extracted, failed


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Extract text from downloaded PDFs")
    parser.add_argument("--limit", type=int, default=None, help="Max PDFs to process")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4], help="Process only this tier")
    parser.add_argument("--force", action="store_true", help="Re-extract already-processed PDFs")
    args = parser.parse_args()

    init_db()
    extract_all(limit=args.limit, tier_filter=args.tier, force=args.force)
