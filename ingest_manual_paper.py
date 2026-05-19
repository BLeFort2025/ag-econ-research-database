"""
Manual Paper Ingestion Script
==============================
Use this script to add a single government or grey-lit PDF directly to the
Research Database, bypassing the automated harvesters.

Usage:
    python ingest_manual_paper.py

Edit the PAPER_METADATA dict below before running.
"""

import os
import sys
import shutil
from datetime import datetime

# ── Make sure we can import our own modules ──────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from db import (
    init_db, get_connection,
    paper_exists_by_title, paper_exists_by_url,
    insert_paper, update_paper_pdf, update_paper_full_text,
    get_or_create_author, link_paper_author,
    get_or_create_topic, link_paper_topic,
    start_harvest_log, complete_harvest_log,
)
from config import GREY_LIT_DIR
from pdf_text_extractor import extract_text_from_pdf


# ═══════════════════════════════════════════════════════════════════════════
#  EDIT THIS SECTION FOR EACH PAPER YOU WANT TO ADD
# ═══════════════════════════════════════════════════════════════════════════

PAPER_METADATA = {
    # --- Source PDF (full path or relative to this script) ---
    "source_pdf_path": r"C:\Users\ben.lefort\Downloads\00001-eng 1.pdf",

    # --- Bibliographic details ---
    "title": (
        "Temporary foreign workers in primary agriculture in Canada: "
        "Transition from temporary residency to permanent residency "
        "and industry retention after transition"
    ),
    "abstract": (
        "This study examines the transition to permanent residency (PR) of temporary foreign "
        "workers (TFWs) in primary agriculture and the retention in the sector among those "
        "who obtained PR. The study focuses on TFWs whose first employment was in primary "
        "agriculture and who entered the sector between 2005 and 2020. Overall, rates of "
        "transition from temporary to permanent residency were low among TFWs who first "
        "entered primary agriculture during the study period. Five years after entry, "
        "slightly more than 10% had obtained PR. After 10 years since workers were first "
        "employed in the sector, the cumulative transition rate reached 16.8%. Transition "
        "rates were considerably lower for TFWs with a designated occupation at a lower "
        "skill level than for those with one at a higher skill level. Rates were lower for "
        "TFWs with permits issued through the Seasonal Agricultural Worker Program than for "
        "those with permits issued through other work permit programs. Most TFWs who entered "
        "primary agriculture left the sector after receiving PR. One year after PR admission, "
        "half of former TFWs or less stayed in the sector; five years after PR admission, "
        "around one-fifth were still employed in the sector."
    ),
    "year": 2024,
    "authors": [
        {"name": "Li Xu",        "institution": "Immigration, Refugees and Citizenship Canada", "country": "CA"},
        {"name": "Yuqian Lu",    "institution": "Statistics Canada", "country": "CA"},
        {"name": "Jianwei Zhong","institution": "Immigration, Refugees and Citizenship Canada", "country": "CA"},
    ],
    "topics": [
        "temporary foreign workers",
        "primary agriculture labour",
        "Seasonal Agricultural Worker Program",
        "permanent residency transition",
        "agricultural labour retention",
    ],
    "doi":           "10.25318/36280001202400300001-eng",
    "pdf_url":       "https://www150.statcan.gc.ca/pub/36-28-0001/2024001/article/00001-eng.pdf",  # canonical HTML: https://www150.statcan.gc.ca/n1/pub/36-28-0001/2024001/article/00001-eng.htm
    "source_name":   "Economic and Social Reports (Statistics Canada)",
    "source_issn":   "2563-8955",
    "paper_type":    "report",          # journal-article | report | working-paper | policy-brief
    "priority_tier": 1,                 # 1=Canadian gov/research, 2=US, 3=OECD, 4=Global
    "harvest_source": "manual_statcan", # tag so we can see where it came from
    "is_open_access": True,
}

# ═══════════════════════════════════════════════════════════════════════════

def _dest_filename(meta):
    """Build a clean filename for the stored PDF."""
    safe_title = meta["title"][:60].replace(" ", "_").replace("/", "-").replace(":", "")
    year = meta.get("year", "XXXX")
    return f"{meta['harvest_source']}_{year}_{safe_title}.pdf"


def ingest(meta):
    init_db()
    conn = get_connection()

    # ── 1. Dedup check ───────────────────────────────────────────────────────
    existing_id = (
        paper_exists_by_url(conn, meta.get("pdf_url"))
        or paper_exists_by_title(conn, meta["title"])
    )
    if existing_id:
        print(f"[SKIP] Paper already in database (id={existing_id}):")
        print(f"       {meta['title'][:80]}")
        conn.close()
        return

    # ── 2. Copy PDF into the grey-lit folder ─────────────────────────────────
    src_pdf = meta.get("source_pdf_path", "")
    pdf_local_path = None
    pdf_size_bytes = None

    if src_pdf and os.path.exists(src_pdf):
        os.makedirs(GREY_LIT_DIR, exist_ok=True)

        # 1) See if a pre-copied version already lives in GREY_LIT_DIR
        pre_copied = None
        for fname in os.listdir(GREY_LIT_DIR):
            if fname.endswith(".pdf") and "statcan" in fname.lower() and meta.get("harvest_source", "") in ["manual_statcan", "grey_statcan_ag"]:
                candidate = os.path.join(GREY_LIT_DIR, fname)
                if os.path.getsize(candidate) == os.path.getsize(src_pdf):
                    pre_copied = candidate
                    break

        if pre_copied:
            pdf_local_path = pre_copied
            pdf_size_bytes = os.path.getsize(pre_copied)
            print(f"[PDF] Using pre-copied file: {pre_copied}")
        else:
            dest_filename = _dest_filename(meta)
            dest_path = os.path.join(GREY_LIT_DIR, dest_filename)
            shutil.copy2(src_pdf, dest_path)
            print(f"[PDF] Copied → {dest_path}")
            pdf_local_path = dest_path
            pdf_size_bytes = os.path.getsize(dest_path)
    else:
        print(f"[WARN] PDF not found at: {src_pdf!r}  — storing metadata only.")

    # ── 3. Insert paper record ────────────────────────────────────────────────
    log_id = start_harvest_log(conn, meta["harvest_source"], f"Manual ingest: {meta['title'][:60]}")

    paper_id = insert_paper(conn, {
        "title":          meta["title"],
        "abstract":       meta.get("abstract"),
        "year":           meta.get("year"),
        "doi":            meta.get("doi"),
        "pdf_url":        meta.get("pdf_url"),
        "source_name":    meta.get("source_name"),
        "source_issn":    meta.get("source_issn"),
        "paper_type":     meta.get("paper_type", "report"),
        "priority_tier":  meta.get("priority_tier", 4),
        "harvest_source": meta.get("harvest_source", "manual"),
        "is_open_access": meta.get("is_open_access", True),
        "citation_count": 0,
    })

    if paper_id is None:
        print("[SKIP] insert_paper returned None — already exists (DOI/title clash).")
        complete_harvest_log(conn, log_id, 0, 1)
        conn.close()
        return

    print(f"[DB]  Paper inserted (id={paper_id})")

    # ── 4. Link authors ───────────────────────────────────────────────────────
    for pos, author_info in enumerate(meta.get("authors", []), start=1):
        author_id = get_or_create_author(
            conn,
            name=author_info["name"],
            institution=author_info.get("institution"),
            country=author_info.get("country"),
        )
        link_paper_author(conn, paper_id, author_id, position=pos)
    print(f"[DB]  Linked {len(meta.get('authors', []))} author(s)")

    # ── 5. Link topics ────────────────────────────────────────────────────────
    for topic_name in meta.get("topics", []):
        topic_id = get_or_create_topic(conn, name=topic_name)
        link_paper_topic(conn, paper_id, topic_id)
    print(f"[DB]  Linked {len(meta.get('topics', []))} topic(s)")

    # ── 6. Attach PDF + extract full text ─────────────────────────────────────
    if pdf_local_path:
        update_paper_pdf(conn, paper_id, pdf_local_path, pdf_size_bytes)

        print("[TXT] Extracting full text from PDF …")
        full_text = extract_text_from_pdf(pdf_local_path)
        if full_text:
            update_paper_full_text(conn, paper_id, full_text, status=1)
            print(f"[TXT] Extracted {len(full_text):,} characters")
        else:
            update_paper_full_text(conn, paper_id, None, status=-1)
            print("[TXT] Extraction failed — check PDF encoding")

    conn.commit()
    complete_harvest_log(conn, log_id, 1, 0)
    conn.close()

    print("\n[DONE] Paper successfully added to the database.")
    print(f"   Title    : {meta['title'][:80]}")
    print(f"   Authors  : {', '.join(a['name'] for a in meta.get('authors', []))}")
    print(f"   Year     : {meta.get('year')}")
    print(f"   DOI      : {meta.get('doi')}")
    print(f"   DB ID    : {paper_id}")


if __name__ == "__main__":
    ingest(PAPER_METADATA)
