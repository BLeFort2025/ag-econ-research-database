"""
AgEcon Search OAI-PMH harvester.
Harvests full metadata from the University of Minnesota AgEcon Search repository,
which contains 100,000+ open-access agricultural economics papers.
"""
import time
import re
import requests
from lxml import etree
from config import (
    AGECONSEARCH_OAI_URL,
    REQUEST_TIMEOUT,
)
from db import (
    get_connection,
    insert_paper,
    paper_exists,
    get_or_create_author,
    link_paper_author,
    start_harvest_log,
    complete_harvest_log,
)


# MARC21 XML namespace
MARC_NS = "http://www.loc.gov/MARC21/slim"
OAI_NS = "http://www.openarchives.org/OAI/2.0/"

NSMAP = {
    "oai": OAI_NS,
    "marc": MARC_NS,
}


class AgEconSearchHarvester:
    """Harvest papers from AgEcon Search via OAI-PMH protocol."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AgEconResearchPipeline/1.0",
        })
        self.base_url = AGECONSEARCH_OAI_URL

    def _oai_request(self, verb, **kwargs):
        """Make an OAI-PMH request and return the parsed XML tree."""
        params = {"verb": verb, **kwargs}
        try:
            resp = self.session.get(
                self.base_url, params=params, timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            return etree.fromstring(resp.content)
        except requests.RequestException as e:
            print(f"  [ERROR] OAI-PMH request failed: {e}")
            return None
        except etree.XMLSyntaxError as e:
            print(f"  [ERROR] XML parse error: {e}")
            return None

    def _get_marc_field(self, record, tag, subfield_code="a"):
        """Extract a MARC field value from a record."""
        xpath = f".//marc:datafield[@tag='{tag}']/marc:subfield[@code='{subfield_code}']"
        elem = record.find(xpath, NSMAP)
        return elem.text.strip() if elem is not None and elem.text else None

    def _get_marc_fields(self, record, tag, subfield_code="a"):
        """Extract all values for a repeating MARC field."""
        xpath = f".//marc:datafield[@tag='{tag}']/marc:subfield[@code='{subfield_code}']"
        elems = record.findall(xpath, NSMAP)
        return [e.text.strip() for e in elems if e.text and e.text.strip()]

    def _extract_year(self, record):
        """Extract publication year from MARC record."""
        # Try 260$c (publication date) or 264$c
        for tag in ["260", "264"]:
            date_str = self._get_marc_field(record, tag, "c")
            if date_str:
                match = re.search(r"(\d{4})", date_str)
                if match:
                    return int(match.group(1))

        # Try 008 fixed field (positions 7-10)
        field_008 = record.find(".//marc:controlfield[@tag='008']", NSMAP)
        if field_008 is not None and field_008.text and len(field_008.text) >= 11:
            year_str = field_008.text[7:11]
            if year_str.isdigit():
                return int(year_str)

        return None

    def _extract_pdf_url(self, record):
        """Extract PDF URL from MARC 856 field."""
        # Find all 856 fields (electronic location)
        datafields = record.findall(
            f".//marc:datafield[@tag='856']", NSMAP
        )
        for df in datafields:
            url_elem = df.find(f"marc:subfield[@code='u']", NSMAP)
            if url_elem is not None and url_elem.text:
                url = url_elem.text.strip()
                if url.lower().endswith(".pdf"):
                    return url
                # AgEcon Search record pages — these link to the PDF landing page
                if "ageconsearch.umn.edu" in url:
                    return url
        return None

    def _extract_doi(self, record):
        """Extract DOI from MARC 024 field."""
        datafields = record.findall(
            f".//marc:datafield[@tag='024']", NSMAP
        )
        for df in datafields:
            ind1 = df.get("ind1", "")
            if ind1 == "7":  # DOI indicator
                val = df.find(f"marc:subfield[@code='a']", NSMAP)
                if val is not None and val.text:
                    doi = val.text.strip()
                    # Clean up DOI
                    if doi.startswith("10."):
                        return doi
                    match = re.search(r"(10\.\d{4,}/\S+)", doi)
                    if match:
                        return match.group(1)
        return None

    def _extract_abstract(self, record):
        """Extract abstract from MARC 520 field."""
        return self._get_marc_field(record, "520", "a")

    def _extract_authors(self, record):
        """Extract author names from MARC 100 and 700 fields."""
        authors = []

        # Primary author (100)
        primary = self._get_marc_field(record, "100", "a")
        if primary:
            authors.append(primary.rstrip(",. "))

        # Additional authors (700)
        additional = self._get_marc_fields(record, "700", "a")
        for name in additional:
            authors.append(name.rstrip(",. "))

        return authors

    def _extract_source(self, record):
        """Extract source/journal name from MARC fields."""
        # 773$t = host item title (journal name for articles)
        source = self._get_marc_field(record, "773", "t")
        if source:
            return source

        # 490$a = series statement
        source = self._get_marc_field(record, "490", "a")
        if source:
            return source

        # 710$a = corporate author (often the publishing institution)
        source = self._get_marc_field(record, "710", "a")
        return source

    def _classify_tier(self, record, source_name):
        """Classify the paper into a priority tier based on available metadata."""
        source_lower = (source_name or "").lower()

        # Tier 1: Canadian
        canadian_keywords = ["canad", "cjae", "ontario", "alberta", "saskatchewan",
                            "manitoba", "quebec", "british columbia"]
        for kw in canadian_keywords:
            if kw in source_lower:
                return 1

        # Check author affiliations in 100$u or 700$u
        for tag in ["100", "700"]:
            affiliation = self._get_marc_field(record, tag, "u")
            if affiliation and any(kw in affiliation.lower() for kw in canadian_keywords):
                return 1

        # Tier 2: US
        us_keywords = ["american", "usda", "ajae", "united states"]
        for kw in us_keywords:
            if kw in source_lower:
                return 2

        # Tier 3: OECD
        oecd_keywords = ["european", "oecd", "australia", "uk", "british"]
        for kw in oecd_keywords:
            if kw in source_lower:
                return 3

        # Default to Tier 4
        return 4

    def _process_record(self, record_elem, conn):
        """Process a single OAI-PMH record. Returns True if inserted."""
        # Get the MARC record inside the metadata element
        marc_record = record_elem.find(
            ".//oai:metadata/marc:record", NSMAP
        )
        if marc_record is None:
            return False

        # Extract title from MARC 245
        title = self._get_marc_field(marc_record, "245", "a")
        subtitle = self._get_marc_field(marc_record, "245", "b")
        if subtitle:
            title = f"{title} {subtitle}" if title else subtitle
        if not title:
            return False

        title = title.rstrip(" /,.:;")

        doi = self._extract_doi(marc_record)
        source_name = self._extract_source(marc_record)

        # Check for duplicates by DOI
        if doi and paper_exists(conn, doi=doi):
            return False

        paper_data = {
            "doi": doi,
            "title": title,
            "abstract": self._extract_abstract(marc_record),
            "year": self._extract_year(marc_record),
            "paper_type": "working-paper",  # AgEcon Search is mostly working papers
            "is_open_access": True,  # AgEcon Search is open access
            "pdf_url": self._extract_pdf_url(marc_record),
            "source_name": source_name,
            "priority_tier": self._classify_tier(marc_record, source_name),
            "harvest_source": "ageconsearch",
        }

        paper_id = insert_paper(conn, paper_data)
        if paper_id is None:
            return False

        # Process authors
        authors = self._extract_authors(marc_record)
        for i, author_name in enumerate(authors, 1):
            author_id = get_or_create_author(conn, author_name)
            link_paper_author(conn, paper_id, author_id, position=i)

        return True

    def harvest(self, max_records=None, from_date=None):
        """
        Harvest all records from AgEcon Search via OAI-PMH.
        Uses resumption tokens for paginated retrieval.
        Returns (added_count, skipped_count).
        """
        print("\n" + "=" * 70)
        print("AgEcon Search Harvest (OAI-PMH)")
        print("=" * 70)

        conn = get_connection()
        log_id = start_harvest_log(conn, "ageconsearch", "Full OAI-PMH harvest")

        added = 0
        skipped = 0
        batch = 0
        resumption_token = None
        fail_count = 0

        try:
            while True:
                batch += 1

                if resumption_token:
                    tree = self._oai_request(
                        "ListRecords", resumptionToken=resumption_token
                    )
                else:
                    kwargs = {"metadataPrefix": "marcxml"}
                    if from_date:
                        kwargs["from"] = from_date
                    tree = self._oai_request(
                        "ListRecords", **kwargs
                    )

                if tree is None:
                    print(f"  [ERROR] Failed to get response on batch {batch}")
                    fail_count += 1
                    if fail_count > 3:
                        print("  [ERROR] Too many consecutive failures. Aborting harvest.")
                        break
                    # Wait and retry
                    time.sleep(5)
                    continue
                else:
                    fail_count = 0

                # Check for OAI-PMH errors
                error = tree.find(f".//oai:error", NSMAP)
                if error is not None:
                    error_code = error.get("code", "unknown")
                    error_msg = error.text or ""
                    print(f"  [OAI ERROR] {error_code}: {error_msg}")
                    if error_code == "noRecordsMatch":
                        break
                    # For transient errors, wait and retry
                    fail_count += 1
                    if fail_count > 3:
                        print("  [ERROR] Too many consecutive OAI errors. Aborting.")
                        break
                    time.sleep(10)
                    continue
                else:
                    fail_count = 0

                # Process records
                records = tree.findall(f".//oai:record", NSMAP)
                batch_added = 0
                for rec in records:
                    # Skip deleted records
                    header = rec.find(f"oai:header", NSMAP)
                    if header is not None and header.get("status") == "deleted":
                        skipped += 1
                        continue

                    if self._process_record(rec, conn):
                        added += 1
                        batch_added += 1
                    else:
                        skipped += 1

                conn.commit()
                print(f"  Batch {batch}: {len(records)} records | +{batch_added} new | Total: {added} added, {skipped} skipped")

                # Check for resumption token
                token_elem = tree.find(f".//oai:resumptionToken", NSMAP)
                if token_elem is not None and token_elem.text:
                    resumption_token = token_elem.text.strip()
                    # Some repos include list size info
                    complete_size = token_elem.get("completeListSize")
                    if complete_size:
                        print(f"  Repository reports {complete_size} total records")
                else:
                    print("  [INFO] No more resumption tokens — harvest complete")
                    break

                if max_records and added >= max_records:
                    print(f"  [LIMIT] Reached max_records={max_records}")
                    break

                # Be polite
                time.sleep(1)

        except KeyboardInterrupt:
            print("\n  [INTERRUPTED] Saving progress...")
            conn.commit()
            complete_harvest_log(conn, log_id, added, skipped, "interrupted")
            conn.close()
            return added, skipped
        except Exception as e:
            print(f"  [ERROR] Harvest failed: {e}")
            import traceback
            traceback.print_exc()
            complete_harvest_log(conn, log_id, added, skipped, "failed", str(e))
            conn.close()
            return added, skipped

        complete_harvest_log(conn, log_id, added, skipped, "completed")
        conn.close()

        print(f"\n  [DONE] AgEcon Search: {added} papers added, {skipped} skipped")
        return added, skipped


def harvest_ageconsearch(max_records=None, from_date=None):
    """Main entry point for AgEcon Search harvesting."""
    harvester = AgEconSearchHarvester()
    return harvester.harvest(max_records=max_records, from_date=from_date)


if __name__ == "__main__":
    from db import init_db
    init_db()
    harvest_ageconsearch()
