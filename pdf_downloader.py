"""
PDF Download Manager for the Agricultural Economics Research Database.
Downloads open-access PDFs with rate limiting, storage budget enforcement,
and organized directory structure.
"""
import os
import time
import requests
from config import (
    PDF_DIR,
    MAX_PDF_STORAGE_GB,
    PDF_DOWNLOAD_DELAY,
    PDF_DOWNLOAD_TIMEOUT,
    PDF_MAX_RETRIES,
)
from db import (
    get_connection,
    update_paper_pdf,
    get_pdf_storage_used_gb,
)


class PDFDownloader:
    """Download open-access PDFs with storage budget enforcement."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AgEconResearchPipeline/1.0 (academic-research)",
        })

    def _get_save_path(self, paper):
        """Generate the local save path for a PDF. Organizes by tier/year."""
        tier = paper["priority_tier"] or 4
        year = paper["year"] or "unknown"
        tier_names = {1: "01_Canadian", 2: "02_US", 3: "03_OECD", 4: "04_Global"}
        tier_dir = tier_names.get(tier, f"{tier:02d}_Other")

        directory = os.path.join(PDF_DIR, tier_dir, str(year))
        os.makedirs(directory, exist_ok=True)

        # Create a safe filename from paper ID and truncated title
        paper_id = paper["id"]
        title = (paper["title"] or "untitled")[:80]
        # Sanitize filename
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
        safe_title = safe_title.strip()

        filename = f"{paper_id}_{safe_title}.pdf"
        return os.path.join(directory, filename)

    def _download_file(self, url, save_path):
        """Download a single PDF file. Returns (success, file_size_bytes)."""
        for attempt in range(1, PDF_MAX_RETRIES + 1):
            try:
                resp = self.session.get(
                    url,
                    timeout=PDF_DOWNLOAD_TIMEOUT,
                    stream=True,
                    allow_redirects=True,
                )
                resp.raise_for_status()

                # Check content type — make sure it's actually a PDF
                content_type = resp.headers.get("Content-Type", "").lower()
                if "pdf" not in content_type and "octet-stream" not in content_type:
                    # If it's HTML, it's probably a landing page, not a PDF
                    if "html" in content_type:
                        return False, 0

                # Download in chunks to track size
                total_bytes = 0
                with open(save_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                        total_bytes += len(chunk)

                # Verify it's actually a PDF (check magic bytes)
                with open(save_path, "rb") as f:
                    header = f.read(5)
                    if header != b"%PDF-":
                        os.remove(save_path)
                        return False, 0

                return True, total_bytes

            except requests.RequestException as e:
                if attempt < PDF_MAX_RETRIES:
                    wait = 2 ** attempt  # Exponential backoff
                    print(f"    [RETRY {attempt}/{PDF_MAX_RETRIES}] {e} — waiting {wait}s")
                    time.sleep(wait)
                else:
                    # Clean up partial download
                    if os.path.exists(save_path):
                        os.remove(save_path)
                    return False, 0

        return False, 0

    def download_papers(self, limit=None, tier_filter=None):
        """
        Download PDFs for papers that have a pdf_url but no pdf_local_path.
        Respects the storage budget.

        Args:
            limit: Max number of PDFs to download (None = unlimited within budget)
            tier_filter: Only download papers from this tier (1-4)
        """
        conn = get_connection()

        # Check storage budget
        used_gb = get_pdf_storage_used_gb(conn)
        budget_gb = MAX_PDF_STORAGE_GB
        remaining_gb = budget_gb - used_gb

        if MAX_PDF_STORAGE_GB == 0:
            print("[SKIP] PDF downloads disabled (MAX_PDF_STORAGE_GB = 0)")
            conn.close()
            return 0, 0

        print(f"\n{'=' * 70}")
        print(f"PDF Download Manager")
        print(f"Storage: {used_gb:.2f} GB used / {budget_gb} GB budget ({remaining_gb:.2f} GB remaining)")
        print(f"{'=' * 70}")

        if remaining_gb <= 0.1:
            print("[BUDGET] Storage budget exhausted. Increase MAX_PDF_STORAGE_GB in config.py to download more.")
            conn.close()
            return 0, 0

        # Query papers with URLs that haven't been downloaded
        query = """
            SELECT id, title, pdf_url, priority_tier, year
            FROM papers
            WHERE pdf_url IS NOT NULL
              AND pdf_local_path IS NULL
              AND is_open_access = 1
        """
        params = []

        if tier_filter is not None:
            query += " AND priority_tier = ?"
            params.append(tier_filter)

        # Download highest priority (lowest tier number) first, then most cited
        query += " ORDER BY priority_tier ASC, citation_count DESC"

        if limit:
            query += f" LIMIT {int(limit)}"

        papers = conn.execute(query, params).fetchall()
        total = len(papers)
        print(f"[QUEUE] {total} papers with PDF URLs available for download\n")

        downloaded = 0
        failed = 0

        for i, paper in enumerate(papers, 1):
            # Re-check budget
            current_used = get_pdf_storage_used_gb(conn)
            if current_used >= budget_gb:
                print(f"\n[BUDGET] Storage budget reached ({current_used:.2f} GB / {budget_gb} GB)")
                break

            url = paper["pdf_url"]
            if not url or not url.startswith("http"):
                failed += 1
                continue

            save_path = self._get_save_path(paper)

            # Skip if already downloaded (file exists)
            if os.path.exists(save_path):
                downloaded += 1
                continue

            print(f"  [{i}/{total}] Tier {paper['priority_tier']} | {paper['year']} | {paper['title'][:60]}...")

            success, file_size = self._download_file(url, save_path)

            if success:
                update_paper_pdf(conn, paper["id"], save_path, file_size)
                conn.commit()
                downloaded += 1
                size_mb = file_size / (1024 * 1024)
                print(f"    ✓ Downloaded ({size_mb:.1f} MB)")
            else:
                failed += 1
                print(f"    ✗ Failed")

            # Rate limit
            time.sleep(PDF_DOWNLOAD_DELAY)

        conn.close()

        print(f"\n{'=' * 70}")
        print(f"DOWNLOAD COMPLETE: {downloaded} successful, {failed} failed")
        final_used = get_pdf_storage_used_gb(get_connection())
        print(f"Storage used: {final_used:.2f} GB / {budget_gb} GB")
        print(f"{'=' * 70}")

        return downloaded, failed


def download_pdfs(limit=None, tier=None):
    """Main entry point for PDF downloads."""
    downloader = PDFDownloader()
    return downloader.download_papers(limit=limit, tier_filter=tier)


if __name__ == "__main__":
    download_pdfs()
