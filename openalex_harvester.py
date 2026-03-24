"""
OpenAlex API harvester for agricultural economics papers.
Queries by journal (priority-ordered) and by topic keywords.
Uses cursor-based pagination for efficient large-scale harvesting.
"""
import time
import requests
from config import (
    OPENALEX_BASE_URL,
    OPENALEX_EMAIL,
    OPENALEX_PER_PAGE,
    OPENALEX_RATE_LIMIT,
    PRIORITY_JOURNALS,
    AG_ECON_SEARCH_TERMS,
    REQUEST_TIMEOUT,
)
from db import (
    get_connection,
    insert_paper,
    get_or_create_author,
    link_paper_author,
    get_or_create_topic,
    link_paper_topic,
    start_harvest_log,
    complete_harvest_log,
)


class OpenAlexHarvester:
    """Harvest agricultural economics papers from the OpenAlex API."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"AgEconResearchPipeline/1.0 (mailto:{OPENALEX_EMAIL})",
        })
        self.base_params = {
            "mailto": OPENALEX_EMAIL,
            "per_page": OPENALEX_PER_PAGE,
        }
        self.request_count = 0
        self.rate_limit_window_start = time.time()

    def _rate_limit(self):
        """Enforce rate limiting."""
        self.request_count += 1
        elapsed = time.time() - self.rate_limit_window_start
        if self.request_count >= OPENALEX_RATE_LIMIT:
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)
            self.request_count = 0
            self.rate_limit_window_start = time.time()

    def _get(self, endpoint, params=None):
        """Make a rate-limited GET request to the OpenAlex API."""
        self._rate_limit()
        url = f"{OPENALEX_BASE_URL}/{endpoint}"
        all_params = {**self.base_params, **(params or {})}
        try:
            resp = self.session.get(url, params=all_params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            print(f"  [ERROR] API request failed: {e}")
            return None

    def _resolve_source_id(self, journal_info):
        """Resolve a journal's OpenAlex source ID from its ISSN if not already known."""
        if journal_info.get("openalex_source_id"):
            return journal_info["openalex_source_id"]

        for issn in journal_info.get("issns", []):
            data = self._get(f"sources/issn:{issn}")
            if data and data.get("id"):
                source_id = data["id"].replace("https://openalex.org/", "")
                journal_info["openalex_source_id"] = source_id
                print(f"  [RESOLVED] {journal_info['name']} → {source_id}")
                return source_id

        print(f"  [WARN] Could not resolve source ID for {journal_info['name']}")
        return None

    def _extract_abstract(self, work):
        """Extract abstract from OpenAlex inverted index format."""
        abstract_inv = work.get("abstract_inverted_index")
        if not abstract_inv:
            return None

        # Reconstruct from inverted index
        word_positions = []
        for word, positions in abstract_inv.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort()
        return " ".join(word for _, word in word_positions)

    def _extract_pdf_url(self, work):
        """Get the best open-access PDF URL from a work."""
        # Check best OA location first
        best_oa = work.get("best_oa_location")
        if best_oa:
            pdf = best_oa.get("pdf_url")
            if pdf:
                return pdf
            landing = best_oa.get("landing_page_url")
            if landing:
                return landing

        # Check primary location
        primary = work.get("primary_location") or {}
        pdf = primary.get("pdf_url")
        if pdf:
            return pdf

        # Check all locations
        for loc in work.get("locations", []):
            if loc.get("pdf_url"):
                return loc["pdf_url"]

        return None

    def _determine_tier(self, work, default_tier=4):
        """Determine the priority tier for a paper based on its source journal."""
        primary_loc = work.get("primary_location") or {}
        source = primary_loc.get("source") or {}
        source_id = (source.get("id") or "").replace("https://openalex.org/", "")
        source_issn = source.get("issn_l", "")

        for journal in PRIORITY_JOURNALS:
            if journal.get("openalex_source_id") == source_id:
                return journal["tier"]
            if source_issn in journal.get("issns", []):
                return journal["tier"]

        # Fallback: check author countries for Canadian/US classification
        authorships = work.get("authorships", [])
        countries = set()
        for auth in authorships:
            for inst in auth.get("institutions", []):
                cc = inst.get("country_code")
                if cc:
                    countries.add(cc)

        if "CA" in countries:
            return max(1, default_tier)  # Bump to tier 1 if Canadian authors
        if "US" in countries:
            return max(2, default_tier)

        oecd_codes = {"GB", "DE", "FR", "AU", "NZ", "JP", "KR", "IT", "NL", "SE",
                      "NO", "DK", "FI", "BE", "AT", "CH", "IE", "ES", "PT", "IL"}
        if countries & oecd_codes:
            return max(3, default_tier)

        return default_tier

    def _process_work(self, work, conn, default_tier=4):
        """Process a single OpenAlex work into the database. Returns True if inserted."""
        openalex_id = work.get("id", "").replace("https://openalex.org/", "")
        doi = work.get("doi")
        if doi and doi.startswith("https://doi.org/"):
            doi = doi[16:]  # Strip prefix

        title = work.get("title") or work.get("display_name")
        if not title:
            return False

        primary_loc = work.get("primary_location") or {}
        source = primary_loc.get("source") or {}

        paper_data = {
            "openalex_id": openalex_id,
            "doi": doi,
            "title": title,
            "abstract": self._extract_abstract(work),
            "year": work.get("publication_year"),
            "citation_count": work.get("cited_by_count", 0),
            "paper_type": work.get("type"),
            "is_open_access": work.get("open_access", {}).get("is_oa", False),
            "pdf_url": self._extract_pdf_url(work),
            "source_name": source.get("display_name"),
            "source_issn": source.get("issn_l"),
            "priority_tier": self._determine_tier(work, default_tier),
            "harvest_source": "openalex",
        }

        paper_id = insert_paper(conn, paper_data)
        if paper_id is None:
            return False  # Duplicate

        # Process authors
        for i, authorship in enumerate(work.get("authorships", []), 1):
            author_info = authorship.get("author", {})
            author_name = author_info.get("display_name")
            if not author_name:
                continue

            author_oa_id = (author_info.get("id") or "").replace("https://openalex.org/", "")
            institutions = authorship.get("institutions", [])
            inst_name = institutions[0].get("display_name") if institutions else None
            country = institutions[0].get("country_code") if institutions else None

            author_id = get_or_create_author(
                conn, author_name, author_oa_id or None, inst_name, country
            )
            link_paper_author(conn, paper_id, author_id, position=i)

        # Process topics
        for topic_info in work.get("topics", []):
            topic_name = topic_info.get("display_name")
            if not topic_name:
                continue

            topic_oa_id = (topic_info.get("id") or "").replace("https://openalex.org/", "")
            topic_id = get_or_create_topic(
                conn,
                name=topic_name,
                openalex_id=topic_oa_id or None,
                subfield=topic_info.get("subfield", {}).get("display_name"),
                field=topic_info.get("field", {}).get("display_name"),
                domain=topic_info.get("domain", {}).get("display_name"),
            )
            link_paper_topic(conn, paper_id, topic_id, score=topic_info.get("score"))

        return True

    def harvest_by_journal(self, journal_info, max_papers=None):
        """
        Harvest all papers from a specific journal.
        Returns (added_count, skipped_count).
        """
        source_id = self._resolve_source_id(journal_info)
        if not source_id:
            return 0, 0

        journal_name = journal_info["name"]
        tier = journal_info["tier"]
        print(f"\n[HARVEST] {journal_name} (Tier {tier}, Source: {source_id})")

        conn = get_connection()
        log_id = start_harvest_log(conn, "openalex", f"Journal: {journal_name}")

        added = 0
        skipped = 0
        cursor = "*"
        page = 0

        try:
            while cursor:
                page += 1
                params = {
                    "filter": f"primary_location.source.id:{source_id}",
                    "sort": "cited_by_count:desc",
                    "cursor": cursor,
                }

                data = self._get("works", params)
                if not data or "results" not in data:
                    print(f"  [WARN] No results on page {page}")
                    break

                results = data["results"]
                if not results:
                    break

                for work in results:
                    if self._process_work(work, conn, default_tier=tier):
                        added += 1
                    else:
                        skipped += 1

                conn.commit()

                total = data.get("meta", {}).get("count", "?")
                print(f"  Page {page}: +{len(results)} works | Total in API: {total} | DB added: {added}, skipped: {skipped}")

                cursor = data.get("meta", {}).get("next_cursor")

                if max_papers and added >= max_papers:
                    print(f"  [LIMIT] Reached max_papers={max_papers}")
                    break

        except Exception as e:
            print(f"  [ERROR] Harvest failed: {e}")
            complete_harvest_log(conn, log_id, added, skipped, "failed", str(e))
            conn.close()
            return added, skipped

        complete_harvest_log(conn, log_id, added, skipped, "completed")
        conn.close()
        print(f"  [DONE] {journal_name}: {added} added, {skipped} skipped")
        return added, skipped

    def harvest_by_search(self, search_term, max_papers=2000):
        """
        Harvest papers matching a search term across all sources.
        Returns (added_count, skipped_count).
        """
        print(f"\n[SEARCH] '{search_term}' (max {max_papers})")

        conn = get_connection()
        log_id = start_harvest_log(conn, "openalex", f"Search: {search_term}")

        added = 0
        skipped = 0
        cursor = "*"
        page = 0

        try:
            while cursor:
                page += 1
                params = {
                    "search": search_term,
                    "filter": "type:journal-article",
                    "sort": "cited_by_count:desc",
                    "cursor": cursor,
                }

                data = self._get("works", params)
                if not data or "results" not in data:
                    break

                results = data["results"]
                if not results:
                    break

                for work in results:
                    if self._process_work(work, conn):
                        added += 1
                    else:
                        skipped += 1

                conn.commit()

                total = data.get("meta", {}).get("count", "?")
                print(f"  Page {page}: +{len(results)} | Total: {total} | Added: {added}, Skipped: {skipped}")

                cursor = data.get("meta", {}).get("next_cursor")

                if added >= max_papers:
                    print(f"  [LIMIT] Reached max_papers={max_papers}")
                    break

        except Exception as e:
            print(f"  [ERROR] Search harvest failed: {e}")
            complete_harvest_log(conn, log_id, added, skipped, "failed", str(e))
            conn.close()
            return added, skipped

        complete_harvest_log(conn, log_id, added, skipped, "completed")
        conn.close()
        print(f"  [DONE] '{search_term}': {added} added, {skipped} skipped")
        return added, skipped

    def harvest_all_journals(self, max_per_journal=None):
        """Harvest from all priority journals in tier order."""
        total_added = 0
        total_skipped = 0

        sorted_journals = sorted(PRIORITY_JOURNALS, key=lambda j: j["tier"])

        for journal in sorted_journals:
            added, skipped = self.harvest_by_journal(journal, max_papers=max_per_journal)
            total_added += added
            total_skipped += skipped

        print(f"\n[SUMMARY] All journals: {total_added} papers added, {total_skipped} skipped")
        return total_added, total_skipped

    def harvest_all_search_terms(self, max_per_term=2000):
        """Harvest papers by searching for each ag econ search term."""
        total_added = 0
        total_skipped = 0

        for term in AG_ECON_SEARCH_TERMS:
            added, skipped = self.harvest_by_search(term, max_papers=max_per_term)
            total_added += added
            total_skipped += skipped

        print(f"\n[SUMMARY] All search terms: {total_added} papers added, {total_skipped} skipped")
        return total_added, total_skipped


def harvest_openalex(max_per_journal=None, max_per_search=2000, journals_only=False):
    """Main entry point for OpenAlex harvesting."""
    harvester = OpenAlexHarvester()

    print("=" * 70)
    print("OpenAlex Harvest — Agricultural Economics Papers")
    print("=" * 70)

    # Phase 1: Priority journals (these are the most targeted)
    j_added, j_skipped = harvester.harvest_all_journals(max_per_journal)

    s_added, s_skipped = 0, 0
    if not journals_only:
        # Phase 2: Broader topic searches (fills in working papers, etc.)
        s_added, s_skipped = harvester.harvest_all_search_terms(max_per_search)

    total_added = j_added + s_added
    total_skipped = j_skipped + s_skipped

    print("\n" + "=" * 70)
    print(f"HARVEST COMPLETE: {total_added} papers added, {total_skipped} duplicates skipped")
    print("=" * 70)

    return total_added, total_skipped


if __name__ == "__main__":
    from db import init_db
    init_db()
    harvest_openalex()
