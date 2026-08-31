"""
Grey Literature Harvester for the Agricultural Economics Research Database.
Scrapes policy papers, reports, and research from Canadian agri-food
think tanks and research organizations.

Phase 1 Sources:
  1. Agri-Food Economic Systems (agrifoodecon.ca)
  2. CAPI — Canadian Agri-Food Policy Institute (capi-icpa.ca)
  3. FCC Economics — Farm Credit Canada (fcc-fac.ca)
"""
import os
import re
import time
import requests
from urllib.parse import urljoin, unquote
from bs4 import BeautifulSoup

from config import (
    GREY_LIT_DIR,
    GREY_LIT_SCRAPE_DELAY,
    PDF_DOWNLOAD_TIMEOUT,
    PDF_MAX_RETRIES,
)
from db import (
    get_connection,
    insert_paper,
    paper_exists_by_title,
    paper_exists_by_url,
    update_paper_pdf,
    start_harvest_log,
    complete_harvest_log,
)
from grey_lit_sources import (
    GREY_LIT_SOURCES,
    detect_paper_type,
    extract_year_from_text,
    passes_keyword_filter,
)


# ── Base Harvester ──────────────────────────────────────────────────────────

class GreyLitHarvester:
    """Base class for grey literature harvesters."""

    def __init__(self, source_key):
        self.source_key = source_key
        self.source = GREY_LIT_SOURCES[source_key]
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AgEconResearchPipeline/1.0 (academic-research; OFA)",
        })

    def _get_page(self, url):
        """Fetch a page and return BeautifulSoup."""
        try:
            resp = self.session.get(url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as e:
            print(f"    [ERROR] Failed to fetch {url}: {e}")
            return None

    def _clean_title(self, raw_title):
        """Clean a scraped title: strip whitespace, remove trailing dates."""
        if not raw_title:
            return None
        title = raw_title.strip()
        # Remove excess whitespace
        title = re.sub(r'\s+', ' ', title)
        return title

    def _get_save_dir(self, org_short_name, year):
        """Get the save directory for a grey lit PDF. Uses short org names."""
        directory = os.path.join(GREY_LIT_DIR, org_short_name, str(year or "unknown"))
        os.makedirs(directory, exist_ok=True)
        return directory

    def _safe_filename(self, title, max_len=35):
        """Create a filesystem-safe filename from a title (short for Windows)."""
        safe = "".join(c if c.isalnum() or c in " -" else "" for c in title)
        safe = safe.strip()
        return safe[:max_len].rstrip()

    def _download_pdf(self, url, save_path):
        """Download a PDF file. Returns (success, file_size_bytes)."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        except OSError:
            return False, 0

        for attempt in range(1, PDF_MAX_RETRIES + 1):
            try:
                resp = self.session.get(
                    url, timeout=PDF_DOWNLOAD_TIMEOUT,
                    stream=True, allow_redirects=True,
                )
                resp.raise_for_status()

                content_type = resp.headers.get("Content-Type", "").lower()
                if "html" in content_type and "pdf" not in content_type:
                    return False, 0

                total_bytes = 0
                try:
                    with open(save_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                            total_bytes += len(chunk)

                    # Verify PDF magic bytes
                    with open(save_path, "rb") as f:
                        header = f.read(5)
                        if header != b"%PDF-":
                            try:
                                os.remove(save_path)
                            except (PermissionError, OSError):
                                pass
                            return False, 0
                except OSError:
                    return False, 0

                return True, total_bytes

            except requests.RequestException as e:
                if attempt < PDF_MAX_RETRIES:
                    wait = 2 ** attempt
                    time.sleep(wait)
                else:
                    if os.path.exists(save_path):
                        try:
                            os.remove(save_path)
                        except (PermissionError, OSError):
                            pass
                    return False, 0

        return False, 0

    def scrape_papers(self):
        """Override in subclass. Returns list of paper dicts."""
        raise NotImplementedError

    def harvest(self):
        """Main entry: scrape papers, insert into DB, download PDFs."""
        source_name = self.source["name"]
        harvest_source = self.source["harvest_source"]
        org_dir = self.source["short_name"]  # Use short name for paths

        print(f"\n{'=' * 70}")
        print(f"Grey Literature Harvester: {source_name}")
        print(f"{'=' * 70}")

        conn = get_connection()
        log_id = start_harvest_log(conn, harvest_source, f"Grey lit: {source_name}")

        # Scrape paper metadata
        papers = self.scrape_papers()
        print(f"[SCRAPED] Found {len(papers)} papers from {source_name}")

        added = 0
        skipped = 0
        downloaded = 0
        failed_dl = 0

        for i, paper in enumerate(papers, 1):
            title = paper.get("title")
            pdf_url = paper.get("pdf_url")

            if not title:
                skipped += 1
                continue

            # Dedup check
            if paper_exists_by_url(conn, pdf_url) or paper_exists_by_title(conn, title):
                skipped += 1
                continue

            # Detect metadata
            year = paper.get("year") or extract_year_from_text(title)
            paper_type = paper.get("paper_type") or detect_paper_type(
                title, self.source.get("default_paper_type", "report")
            )

            # Insert into DB
            paper_data = {
                "title": title,
                "abstract": paper.get("abstract"),
                "year": year,
                "citation_count": 0,
                "paper_type": paper_type,
                "is_open_access": True,
                "pdf_url": pdf_url,
                "source_name": source_name,
                "priority_tier": self.source.get("priority_tier", 1),
                "harvest_source": harvest_source,
            }

            paper_id = insert_paper(conn, paper_data)
            if paper_id is None:
                skipped += 1
                continue

            added += 1
            print(f"  [{i}/{len(papers)}] + {title[:65]}...")

            # Download PDF if URL available and looks like a real PDF
            if pdf_url and pdf_url.startswith("http") and pdf_url.lower().endswith(".pdf"):
                save_dir = self._get_save_dir(org_dir, year)
                safe_title = self._safe_filename(title)
                filename = f"{paper_id}_{safe_title}.pdf"
                save_path = os.path.join(save_dir, filename)

                if not os.path.exists(save_path):
                    success, file_size = self._download_pdf(pdf_url, save_path)
                    if success:
                        update_paper_pdf(conn, paper_id, save_path, file_size)
                        downloaded += 1
                        size_mb = file_size / (1024 * 1024)
                        print(f"      ✓ PDF ({size_mb:.1f} MB)")
                    else:
                        failed_dl += 1
                        print(f"      ✗ PDF download failed")

                    time.sleep(1)  # Rate limit PDF downloads

            conn.commit()

        complete_harvest_log(conn, log_id, added, skipped)
        conn.close()

        print(f"\n{'=' * 70}")
        print(f"HARVEST COMPLETE: {source_name}")
        print(f"  Papers added:    {added}")
        print(f"  Papers skipped:  {skipped} (duplicates)")
        print(f"  PDFs downloaded: {downloaded}")
        print(f"  PDFs failed:     {failed_dl}")
        print(f"{'=' * 70}")

        return added, skipped


# ── Source 1: Agri-Food Economic Systems ────────────────────────────────────

class AgrifoodeconHarvester(GreyLitHarvester):
    """Scrape Agri-Food Economic Systems (agrifoodecon.ca)."""

    def __init__(self):
        super().__init__("agrifoodecon")

    def scrape_papers(self):
        papers = []
        seen_urls = set()

        for url in self.source["scrape_urls"]:
            print(f"  [SCRAPE] {url}")
            soup = self._get_page(url)
            if not soup:
                continue

            # Find all links to PDFs
            for link in soup.find_all("a", href=True):
                href = link["href"].strip()
                full_url = urljoin(url, href)

                # Only grab PDF links and BNN/TVO/external video links are skipped
                if not (href.endswith(".pdf") or "/files/" in href):
                    continue
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                # Extract title from link text
                raw_title = link.get_text(strip=True)
                if not raw_title or len(raw_title) < 10:
                    # Try to get title from filename
                    raw_title = unquote(os.path.basename(href))
                    raw_title = raw_title.replace(".pdf", "").replace("%20", " ")
                    raw_title = re.sub(r'\(\d+\)$', '', raw_title).strip()

                title = self._clean_title(raw_title)
                if not title:
                    continue

                # Determine source org (George Morris archive vs AES)
                source_name = self.source["name"]
                if "georgemorris.org" in full_url:
                    source_name = "George Morris Centre (Archive)"

                papers.append({
                    "title": title,
                    "pdf_url": full_url,
                    "year": extract_year_from_text(title),
                    "paper_type": detect_paper_type(title, "policy-note"),
                    "source_override": source_name,
                })

            time.sleep(GREY_LIT_SCRAPE_DELAY)

        # Deduplicate by title (some papers appear on multiple pages)
        unique = {}
        for p in papers:
            key = p["title"].lower().strip()
            if key not in unique:
                unique[key] = p
        papers = list(unique.values())

        print(f"  [DEDUP] {len(papers)} unique papers after deduplication")
        return papers


# ── Source 2: CAPI ──────────────────────────────────────────────────────────

class CAPIHarvester(GreyLitHarvester):
    """Scrape Canadian Agri-Food Policy Institute (capi-icpa.ca)."""

    def __init__(self):
        super().__init__("capi")

    def _scrape_resource_page(self, url):
        """Scrape a single resources page. Returns list of papers."""
        papers = []
        soup = self._get_page(url)
        if not soup:
            return papers

        # CAPI uses <article class="archive-item resource"> for each card
        articles = soup.find_all("article", class_="archive-item")
        if not articles:
            # Fallback: try h3 tags
            articles = soup.find_all("h3")

        for article in articles:
            # Title: h3 > a.permalink
            h3 = article.find("h3") if article.name != "h3" else article
            if not h3:
                continue
            title_link = h3.find("a")
            if not title_link:
                continue

            title = self._clean_title(title_link.get_text(strip=True))
            if not title:
                continue

            detail_url = urljoin(url, title_link.get("href", ""))

            # Date: span.date.smaller (format: DD.MM.YYYY)
            year = None
            date_span = article.find("span", class_="date") if article.name != "h3" else None
            if date_span:
                date_text = date_span.get_text(strip=True)
                # Parse DD.MM.YYYY
                date_match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', date_text)
                if date_match:
                    year = int(date_match.group(3))
            if not year:
                year = extract_year_from_text(title)

            # Abstract: div.excerpt > p
            abstract = None
            excerpt_div = article.find("div", class_="excerpt") if article.name != "h3" else None
            if excerpt_div:
                p = excerpt_div.find("p")
                if p:
                    abstract_text = p.get_text(strip=True)
                    if abstract_text and len(abstract_text) > 20:
                        abstract = abstract_text[:1000]

            # PDF link: inside div.more, look for <a> with href ending .pdf
            pdf_url = None
            more_div = article.find("div", class_="more") if article.name != "h3" else None
            if more_div:
                pdf_link = more_div.find("a", href=re.compile(r'\.pdf', re.I))
                if pdf_link:
                    pdf_url = urljoin(url, pdf_link["href"])

            # Also search for "Download PDF" text anywhere in the article
            if not pdf_url and article.name != "h3":
                pdf_link = article.find("a", string=re.compile(r'Download\s*PDF', re.I))
                if pdf_link and pdf_link.get("href"):
                    pdf_url = urljoin(url, pdf_link["href"])

            papers.append({
                "title": title,
                "pdf_url": pdf_url,
                "abstract": abstract,
                "year": year,
                "paper_type": detect_paper_type(title, "report"),
                "detail_url": detail_url,
            })

        return papers

    def scrape_papers(self):
        all_papers = []
        seen_titles = set()
        base_url = self.source["scrape_urls"][0]
        max_pages = 20  # Safety limit (288 / 20 = ~15 pages)

        for page_num in range(1, max_pages + 1):
            if page_num == 1:
                url = base_url
            else:
                url = f"{base_url}?_paged={page_num}"

            print(f"  [SCRAPE] Page {page_num}: {url}")
            papers = self._scrape_resource_page(url)

            if not papers:
                print(f"  [DONE] No more resources on page {page_num}")
                break

            new_count = 0
            for p in papers:
                key = p["title"].lower().strip()
                if key not in seen_titles:
                    seen_titles.add(key)
                    all_papers.append(p)
                    new_count += 1

            print(f"    Found {len(papers)} resources ({new_count} new)")
            time.sleep(GREY_LIT_SCRAPE_DELAY)

        print(f"  [TOTAL] {len(all_papers)} unique CAPI resources found")
        return all_papers


# ── Source 3: FCC Economics ─────────────────────────────────────────────────

# FCC's website is fully JS-rendered — requests returns empty pages.
# This catalog was extracted via browser scraping on 2026-04-01.
# To update: run a browser subagent against https://www.fcc-fac.ca/en/knowledge/economics
# and paginate through all pages to collect article URLs.
FCC_ARTICLE_CATALOG = [
    {"title": "2026 Food and Beverage Report: Are higher selling prices enough to support the industry?", "url": "https://www.fcc-fac.ca/en/knowledge/economics/2026-food-beverage-report"},
    {"title": "Farmland values held strong again in 2025", "url": "https://www.fcc-fac.ca/en/knowledge/economics/2025-farmland-values-held-strong"},
    {"title": "How will the commodity price surge affect Canada?", "url": "https://www.fcc-fac.ca/en/knowledge/economics/commodity-price-surge-affect-canada"},
    {"title": "Concerns about fertilizer availability amid turmoil in the Middle East", "url": "https://www.fcc-fac.ca/en/knowledge/economics/fertilizer-availability-amid-turmoil-middle-east"},
    {"title": "2026 Broiler and egg outlook: Soaring demand for protein, high beef prices underpin sector outlook", "url": "https://www.fcc-fac.ca/en/knowledge/economics/2026-broiler-egg-outlook"},
    {"title": "2026 Dairy outlook: The protein craze makes waves in the dairy sector", "url": "https://www.fcc-fac.ca/en/knowledge/economics/2026-dairy-outlook"},
    {"title": "2026 FCC Economic Outlook", "url": "https://www.fcc-fac.ca/en/knowledge/economics/2026-economic-outlook"},
    {"title": "2026 Hog outlook: Second consecutive year of strong margins", "url": "https://www.fcc-fac.ca/en/knowledge/economics/2026-hog-outlook"},
    {"title": "2026 Crop outlook: Export momentum key to prices given abundant supplies", "url": "https://www.fcc-fac.ca/en/knowledge/2026-crop-outlook"},
    {"title": "Top economic charts to monitor in 2026", "url": "https://www.fcc-fac.ca/en/knowledge/economics/2026-economic-charts-to-monitor"},
    {"title": "Farm equipment outlook 2026: used equipment and livestock support modest sales growth", "url": "https://www.fcc-fac.ca/en/knowledge/economics/farm-equipment-outlook-2026"},
    {"title": "Canada's economy poised to decelerate in 2026", "url": "https://www.fcc-fac.ca/en/knowledge/economics/canada-economy-deceleration-2026"},
    {"title": "Cattle outlook 2026: Is this the year when the herd size finally expands?", "url": "https://www.fcc-fac.ca/en/knowledge/economics/cattle-outlook-2026"},
    {"title": "Propelling agricultural productivity in Canada: Sustainable growth to feed the world", "url": "https://www.fcc-fac.ca/en/knowledge/economics/agricultural-productivity-canada-sustainable-growth"},
    {"title": "What's your beef? A comment on beef trade dynamics", "url": "https://www.fcc-fac.ca/en/knowledge/economics/beef-trade-dynamics"},
    {"title": "The future of agriculture: Empowering the next generation of Canadian farmers", "url": "https://www.fcc-fac.ca/en/knowledge/economics/future-of-agriculture"},
    {"title": "Why delayed investment threatens food and beverage manufacturing productivity", "url": "https://www.fcc-fac.ca/en/knowledge/economics/delayed-investment-threatens-food-beverage-productivity"},
    {"title": "How beef-on-dairy is changing Canada's beef supply", "url": "https://www.fcc-fac.ca/en/knowledge/beef-on-dairy-changing-canadas-beef-supply"},
    {"title": "Here's how agricultural productivity benefits all Canadians", "url": "https://www.fcc-fac.ca/en/knowledge/economics/agricultural-productivity-benefits-canadians"},
    {"title": "Abundant supplies and improved livestock sectors boosting Canadian feed demand", "url": "https://www.fcc-fac.ca/en/knowledge/economics/boosting-canadian-feed-demand"},
    {"title": "Canada's farmland values in focus: 2025 mid-year report on growth drivers and regional dynamics", "url": "https://www.fcc-fac.ca/en/knowledge/economics/2025-farmland-values-mid-year-update"},
    {"title": "Food and beverage manufacturing sales losing momentum: 2025 mid-year update", "url": "https://www.fcc-fac.ca/en/knowledge/economics/2025-food-beverage-mid-year-report"},
    {"title": "Economic Update - Navigating today's economic environment", "url": "https://www.fcc-fac.ca/en/knowledge/economic-update-navigating-todays-economic-environment"},
    {"title": "The $12-billion trade shift: Canada's opportunity to diversify food exports beyond the U.S.", "url": "https://www.fcc-fac.ca/en/knowledge/economics/trade-shift-diversify-food-exports"},
    {"title": "Short-term Canadian outlook is lacklustre, but nation-building plan bodes well for long term prosperity", "url": "https://www.fcc-fac.ca/en/knowledge/economics/canada-economic-outlook-long-term-growth"},
    {"title": "Preliminary outlook: Possible cost pressures in 2026 reinforce drive to find efficiencies", "url": "https://www.fcc-fac.ca/en/knowledge/economics/cost-pressures-reinforce-efficiencies"},
    {"title": "Anything but American food movement in Canada", "url": "https://www.fcc-fac.ca/en/knowledge/economics/food-movement-in-canada"},
    {"title": "U.S. policy impacting biofuel potential in Canada", "url": "https://www.fcc-fac.ca/en/knowledge/economics/us-policy-impacting-biofuel-potential-canada"},
    {"title": "New crop outlook has improved since the start of the year", "url": "https://www.fcc-fac.ca/en/knowledge/economics/new-crop-outlook-improved"},
    {"title": "Managing costs key to protecting margins for food and beverage manufacturing", "url": "https://www.fcc-fac.ca/en/knowledge/economics/managing-costs-protecting-margins-food-beverage-manufacturing"},
    {"title": "Can Canadian agriculture handle trade and supply chain disruptions?", "url": "https://www.fcc-fac.ca/en/knowledge/economics/trade-supply-chain-disruptions"},
    {"title": "What's driving Canadian interest rates?", "url": "https://www.fcc-fac.ca/en/knowledge/economics/driving-interest-rates"},
    {"title": "Canada sees rising interest in controlled environment agriculture", "url": "https://www.fcc-fac.ca/en/knowledge/economics/rising-interest-agriculture"},
    {"title": "Cultivating value: A review of 2024 fruit land price trends", "url": "https://www.fcc-fac.ca/en/knowledge/economics/2024-fruit-land-price-trends"},
    {"title": "Relatively young fleet may allow farmers to delay equipment purchases amid tariffs", "url": "https://www.fcc-fac.ca/en/knowledge/economics/farm-equipment-purchase-delay-amid-tariffs"},
    {"title": "2024 Farmland rental rates - Renting or purchasing depends on many factors", "url": "https://www.fcc-fac.ca/en/knowledge/economics/2024-farmland-rental-rates"},
    {"title": "Margin uncertainty impacting Canadian seeding decisions", "url": "https://www.fcc-fac.ca/en/knowledge/economics/margin-uncertainty-impacting-seeding"},
    {"title": "2025 FCC Food and Beverage Report: Lower input costs should help improve margins", "url": "https://www.fcc-fac.ca/en/knowledge/economics/2025-food-beverage-report-lower-input-costs-improve-margins"},
    {"title": "Canadian farmland affordability trending down", "url": "https://www.fcc-fac.ca/en/knowledge/economics/canadian-farmland-affordability"},
    {"title": "2024 farmland values in Canada: Continued, steady growth", "url": "https://www.fcc-fac.ca/en/knowledge/economics/2024-farmland-values-canada-steady-growth"},
    {"title": "Q1 2025 economic snapshot: Long-term opportunities for the Canadian economy despite short-term drag from trade disruptions", "url": "https://www.fcc-fac.ca/en/knowledge/economics/q1-2025-economic-snapshot"},
    {"title": "2025 Hog outlook: Recovery under threat due to potential trade barriers", "url": "https://www.fcc-fac.ca/en/knowledge/economics/2025-hog-outlook"},
    {"title": "What do tariffs mean for the Canadian dollar?", "url": "https://www.fcc-fac.ca/en/knowledge/economics/tariffs-canadian-dollar"},
    {"title": "2025 Dairy outlook: Cautious optimism amid trade uncertainty", "url": "https://www.fcc-fac.ca/en/knowledge/economics/2025-dairy-outlook"},
    {"title": "Cultivating prosperity: How plant science innovations are driving Canada's agricultural success", "url": "https://www.fcc-fac.ca/en/knowledge/economics/plant-science-innovations"},
    {"title": "Which Canadian Ag sectors are the most exposed to U.S. tariffs?", "url": "https://www.fcc-fac.ca/en/knowledge/economics/canadian-ag-sectors-most-exposed-us-tariffs"},
    {"title": "Potential trade disruptions dampen strong cattle outlook", "url": "https://www.fcc-fac.ca/en/knowledge/economics/potential-trade-disruptions-cattle-outlook"},
    {"title": "What are tariffs, and why is it tricky to gauge their impacts?", "url": "https://www.fcc-fac.ca/en/knowledge/economics/what-are-tariffs"},
    {"title": "Reigniting agricultural productivity in Canada Report", "url": "https://www.fcc-fac.ca/en/reports/agricultural-productivity-canada"},
]


class FCCHarvester(GreyLitHarvester):
    """
    Harvest Farm Credit Canada Economics articles.

    FCC's site is fully JS-rendered, so we use a pre-scraped catalog of
    known article URLs. Each article page is fetched to extract abstracts
    and any available PDF links. The catalog was built via browser scraping
    on 2026-04-01 and should be refreshed periodically.
    """

    def __init__(self):
        super().__init__("fcc")

    def _extract_meta_from_page(self, url):
        """Try to extract abstract and PDF URL from an FCC article page."""
        abstract = None
        pdf_url = None

        try:
            resp = self.session.get(url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Try meta description for abstract
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                desc = meta_desc["content"].strip()
                if len(desc) > 20:
                    abstract = desc[:1000]

            # Try og:description as fallback
            if not abstract:
                og_desc = soup.find("meta", attrs={"property": "og:description"})
                if og_desc and og_desc.get("content"):
                    desc = og_desc["content"].strip()
                    if len(desc) > 20:
                        abstract = desc[:1000]

            # Check for direct PDF links on the page
            for link in soup.find_all("a", href=True):
                href = link["href"].strip()
                if href.endswith(".pdf"):
                    pdf_url = urljoin(url, href)
                    break

        except requests.RequestException as e:
            print(f"      [WARN] Could not fetch article page: {e}")

        return abstract, pdf_url

    def scrape_papers(self):
        papers = []

        print(f"  [CATALOG] {len(FCC_ARTICLE_CATALOG)} known FCC articles")

        for i, entry in enumerate(FCC_ARTICLE_CATALOG, 1):
            title = entry["title"]
            article_url = entry["url"]

            print(f"  [{i}/{len(FCC_ARTICLE_CATALOG)}] {title[:65]}...")

            # Try to get abstract and PDF from the article page
            abstract, pdf_url = self._extract_meta_from_page(article_url)
            if abstract:
                print(f"      ✓ Got abstract ({len(abstract)} chars)")
            if pdf_url:
                print(f"      ✓ Found PDF: {pdf_url}")

            papers.append({
                "title": title,
                "pdf_url": pdf_url or article_url,  # Use article URL as reference
                "abstract": abstract,
                "year": extract_year_from_text(title),
                "paper_type": detect_paper_type(title, "report"),
                "detail_url": article_url,
            })

            time.sleep(GREY_LIT_SCRAPE_DELAY)

        print(f"  [TOTAL] {len(papers)} FCC articles processed")
        return papers


# ── Source 5: C.D. Howe Institute ──────────────────────────────────────────

class CDHoweHarvester(GreyLitHarvester):
    """
    Scrape C.D. Howe Institute publications filtered to agriculture/food.

    Uses the search endpoint (?s=agriculture, ?s=food+policy, etc.) to
    pre-filter results. The site is JS-rendered with AJAX "Load More"
    pagination, but the initial server-rendered HTML contains the first
    batch of results which we can scrape with requests.
    Each article page may have a "Download Files" button with a PDF link.
    """

    def __init__(self):
        super().__init__("cdhowe")

    def _scrape_search_page(self, url):
        """Scrape one C.D. Howe search results page."""
        papers = []
        soup = self._get_page(url)
        if not soup:
            return papers

        # CDH uses h3 headings with links for each result
        for heading in soup.find_all(["h2", "h3"]):
            link = heading.find("a", href=True)
            if not link:
                continue

            title = self._clean_title(link.get_text(strip=True))
            article_url = urljoin(url, link["href"])

            if not title or len(title) < 10:
                continue
            # Only capture actual publications (not nav/footer links)
            if "/publication/" not in article_url:
                continue

            papers.append({
                "title": title,
                "pdf_url": None,
                "year": extract_year_from_text(title),
                "paper_type": detect_paper_type(title, "report"),
                "detail_url": article_url,
            })

        return papers

    def _try_get_pdf_and_abstract(self, url):
        """Visit an article page to find PDF link and abstract."""
        abstract = None
        pdf_url = None

        try:
            resp = self.session.get(url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Abstract from meta description
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if not meta_desc:
                meta_desc = soup.find("meta", attrs={"property": "og:description"})
            if meta_desc and meta_desc.get("content"):
                desc = meta_desc["content"].strip()
                if len(desc) > 20:
                    abstract = desc[:1000]

            # Look for PDF links
            for link in soup.find_all("a", href=True):
                href = link["href"].strip()
                if href.endswith(".pdf"):
                    pdf_url = urljoin(url, href)
                    break

        except requests.RequestException:
            pass

        return abstract, pdf_url

    def scrape_papers(self):
        all_papers = []
        seen_titles = set()

        for search_url in self.source["scrape_urls"]:
            # Scrape up to 15 pages per search term
            for page_num in range(1, 16):
                if page_num == 1:
                    url = search_url
                else:
                    # CDH uses /page/N/?s=term format
                    from urllib.parse import urlparse, parse_qs
                    parsed = urlparse(search_url)
                    url = f"{parsed.scheme}://{parsed.netloc}/page/{page_num}/{parsed.path}?{parsed.query}"

                if page_num == 1:
                    print(f"  [SEARCH] {search_url}")

                papers = self._scrape_search_page(url)
                if not papers:
                    break

                new_count = 0
                for p in papers:
                    key = p["title"].lower().strip()
                    if key not in seen_titles:
                        seen_titles.add(key)
                        all_papers.append(p)
                        new_count += 1

                if page_num == 1:
                    print(f"    Page 1: {len(papers)} results ({new_count} new)")
                time.sleep(GREY_LIT_SCRAPE_DELAY)

            print(f"    Scraped {page_num} page(s) for this search")
            time.sleep(GREY_LIT_SCRAPE_DELAY)

        # Apply keyword filter and fetch detail pages
        filtered = []
        for p in all_papers:
            # Quick title check first
            if passes_keyword_filter(p["title"]):
                # Get abstract and PDF from article page
                if p.get("detail_url"):
                    print(f"    [DETAIL] {p['title'][:60]}...")
                    abstract, pdf_url = self._try_get_pdf_and_abstract(p["detail_url"])
                    p["abstract"] = abstract
                    if pdf_url:
                        p["pdf_url"] = pdf_url
                    else:
                        p["pdf_url"] = p["detail_url"]
                    time.sleep(GREY_LIT_SCRAPE_DELAY)
                filtered.append(p)

        print(f"  [TOTAL] {len(filtered)} C.D. Howe papers after keyword filter (from {len(all_papers)} candidates)")
        return filtered


# ── Source 6: IISD ─────────────────────────────────────────────────────────

class IISDHarvester(GreyLitHarvester):
    """
    Scrape IISD publications, keyword-filtered for food & agriculture.

    IISD has 263+ pages of publications. We scrape all pages (10 per page)
    and apply the keyword filter to only keep ag/food papers.
    Each publication page typically has a PDF download link.
    """

    def __init__(self):
        super().__init__("iisd")

    def _scrape_publications_page(self, url):
        """Scrape one page of IISD publications."""
        papers = []
        soup = self._get_page(url)
        if not soup:
            return papers

        # IISD uses h3 headings with links for each publication
        for heading in soup.find_all("h3"):
            link = heading.find("a", href=True)
            if not link:
                continue

            title = self._clean_title(link.get_text(strip=True))
            detail_url = urljoin(url, link["href"])

            if not title or len(title) < 10:
                continue
            if "/publications/" not in detail_url:
                continue

            papers.append({
                "title": title,
                "pdf_url": None,
                "year": extract_year_from_text(title),
                "paper_type": detect_paper_type(title, "report"),
                "detail_url": detail_url,
            })

        return papers

    def _get_pdf_and_abstract(self, url):
        """Visit an IISD publication page to get PDF and abstract."""
        abstract = None
        pdf_url = None

        try:
            resp = self.session.get(url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Abstract from meta description
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                desc = meta_desc["content"].strip()
                if len(desc) > 20:
                    abstract = desc[:1000]

            # Look for PDF download links
            for link in soup.find_all("a", href=True):
                href = link["href"].strip()
                if href.endswith(".pdf"):
                    pdf_url = urljoin(url, href)
                    break

        except requests.RequestException:
            pass

        return abstract, pdf_url

    def scrape_papers(self):
        all_papers = []
        seen_titles = set()
        max_pages = 263  # All pages

        for page_num in range(0, max_pages):
            if page_num == 0:
                url = self.source["scrape_urls"][0]
            else:
                url = f"{self.source['scrape_urls'][0]}?page={page_num}"

            if page_num % 20 == 0:
                print(f"  [SCRAPE] Page {page_num + 1}: {url}")

            papers = self._scrape_publications_page(url)
            if not papers:
                print(f"  [DONE] No more publications on page {page_num + 1}")
                break

            for p in papers:
                title = p["title"]
                key = title.lower().strip()
                if key not in seen_titles:
                    seen_titles.add(key)
                    # Apply keyword filter on title
                    if passes_keyword_filter(title):
                        all_papers.append(p)

            time.sleep(GREY_LIT_SCRAPE_DELAY)

        # Fetch details for matching papers
        print(f"  [FILTER] {len(all_papers)} papers match keyword filter")
        for i, p in enumerate(all_papers, 1):
            if p.get("detail_url"):
                print(f"    [{i}/{len(all_papers)}] {p['title'][:60]}...")
                abstract, pdf_url = self._get_pdf_and_abstract(p["detail_url"])
                p["abstract"] = abstract
                if pdf_url:
                    p["pdf_url"] = pdf_url
                else:
                    p["pdf_url"] = p["detail_url"]
                time.sleep(GREY_LIT_SCRAPE_DELAY)

        print(f"  [TOTAL] {len(all_papers)} IISD ag/food publications")
        return all_papers


# ── Source 7: Smart Prosperity Institute ────────────────────────────────────

class SmartProsperityHarvester(GreyLitHarvester):
    """
    Scrape Smart Prosperity Institute library, keyword-filtered.

    Uses institute.smartprosperity.ca/library with ?page=N pagination.
    Each card has a title, date, and short description.
    PDFs are in an "Attachments" section on the article page.
    """

    def __init__(self):
        super().__init__("smartprosperity")

    def _scrape_library_page(self, url):
        """Scrape one page of the Smart Prosperity library."""
        papers = []
        soup = self._get_page(url)
        if not soup:
            return papers

        base_domain = "institute.smartprosperity.ca"
        skip_paths = ["/library", "/blog", "/about", "/our-work", "/events",
                      "/initiatives", "/media", "/get-to-know", "/privacy",
                      "/equity-diversity"]

        # Smart Prosperity uses h1 headings inside <a> tags for each publication
        for heading in soup.find_all("h1"):
            # The heading's parent or grandparent should be an <a> tag
            parent_link = heading.find_parent("a", href=True)
            if not parent_link:
                continue

            href = parent_link["href"].strip()
            full_url = urljoin(url, href)

            # Must be on the SP domain
            if base_domain not in full_url:
                continue
            # Skip navigation/section links
            if any(full_url.rstrip("/").endswith(sp.rstrip("/")) for sp in skip_paths):
                continue
            if "?page=" in full_url:
                continue

            title = self._clean_title(heading.get_text(strip=True))
            if not title or len(title) < 10:
                continue

            # Extract abstract/date from the full link text
            full_text = parent_link.get_text(separator="\n", strip=True)
            abstract = None
            year = extract_year_from_text(full_text)

            # Extract description text (lines after title and date)
            lines = [l.strip() for l in full_text.split("\n") if l.strip()]
            for line in lines:
                if line != title and len(line) > 30 and not any(m in line.lower() for m in ["research paper", "policy brief", "report", "working paper", "multimedia"]):
                    # Skip month/year lines
                    import re
                    if not re.match(r'^[A-Z][a-z]+ \d{4}$', line):
                        abstract = line[:500]
                        break

            papers.append({
                "title": title,
                "pdf_url": None,
                "abstract": abstract,
                "year": year,
                "paper_type": detect_paper_type(title, "report"),
                "detail_url": full_url,
            })

        return papers

    def _get_pdf_from_detail(self, url):
        """Visit article page to find PDF in Attachments section."""
        try:
            resp = self.session.get(url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Get abstract from meta
            abstract = None
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                desc = meta_desc["content"].strip()
                if len(desc) > 20:
                    abstract = desc[:1000]

            # Find PDF link
            for link in soup.find_all("a", href=True):
                href = link["href"].strip()
                if href.endswith(".pdf"):
                    return abstract, urljoin(url, href)

            return abstract, None
        except requests.RequestException:
            return None, None

    def scrape_papers(self):
        all_papers = []
        seen_titles = set()
        max_pages = 50  # Safety limit

        for page_num in range(0, max_pages):
            if page_num == 0:
                url = self.source["scrape_urls"][0]
            else:
                url = f"{self.source['scrape_urls'][0]}?page={page_num}"

            print(f"  [SCRAPE] Page {page_num + 1}: {url}")
            papers = self._scrape_library_page(url)

            if not papers:
                print(f"  [DONE] No more on page {page_num + 1}")
                break

            for p in papers:
                key = p["title"].lower().strip()
                if key not in seen_titles:
                    seen_titles.add(key)
                    if passes_keyword_filter(p["title"], p.get("abstract")):
                        all_papers.append(p)

            time.sleep(GREY_LIT_SCRAPE_DELAY)

        # Fetch PDF links from detail pages
        print(f"  [FILTER] {len(all_papers)} papers match keyword filter")
        for i, p in enumerate(all_papers, 1):
            if p.get("detail_url"):
                print(f"    [{i}/{len(all_papers)}] {p['title'][:60]}...")
                abstract, pdf_url = self._get_pdf_from_detail(p["detail_url"])
                if abstract and not p.get("abstract"):
                    p["abstract"] = abstract
                if pdf_url:
                    p["pdf_url"] = pdf_url
                else:
                    p["pdf_url"] = p["detail_url"]
                time.sleep(GREY_LIT_SCRAPE_DELAY)

        print(f"  [TOTAL] {len(all_papers)} Smart Prosperity ag/food papers")
        return all_papers


# ── Source 8: Canada West Foundation ────────────────────────────────────────

class CanadaWestHarvester(GreyLitHarvester):
    """
    Scrape Canada West Foundation agriculture publications.

    Uses the dedicated agriculture topic page (cwf.ca/topic/agriculture/)
    which is already pre-filtered. Supports /page/N/ pagination.
    Each publication card links to a detail page with PDF downloads.
    """

    def __init__(self):
        super().__init__("canadawest")

    def _scrape_topic_page(self, url):
        """Scrape one page of CWF agriculture publications."""
        papers = []
        soup = self._get_page(url)
        if not soup:
            return papers

        # CWF uses h1 headings for each publication card
        for heading in soup.find_all(["h1", "h2", "h3"]):
            link = heading.find("a", href=True)
            if not link:
                continue

            title = self._clean_title(link.get_text(strip=True))
            detail_url = urljoin(url, link["href"])

            if not title or len(title) < 10:
                continue
            if "/research/publications/" not in detail_url:
                continue

            papers.append({
                "title": title,
                "pdf_url": None,
                "year": extract_year_from_text(title),
                "paper_type": detect_paper_type(title, "report"),
                "detail_url": detail_url,
            })

        return papers

    def _get_pdf_and_abstract(self, url):
        """Visit a CWF article page to get PDF and abstract."""
        try:
            resp = self.session.get(url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Abstract from meta description
            abstract = None
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if not meta_desc:
                meta_desc = soup.find("meta", attrs={"property": "og:description"})
            if meta_desc and meta_desc.get("content"):
                desc = meta_desc["content"].strip()
                if len(desc) > 20:
                    abstract = desc[:1000]

            # Find PDF link
            for link in soup.find_all("a", href=True):
                href = link["href"].strip()
                if href.endswith(".pdf"):
                    return abstract, urljoin(url, href)

            return abstract, None
        except requests.RequestException:
            return None, None

    def scrape_papers(self):
        all_papers = []
        seen_titles = set()
        base_url = self.source["scrape_urls"][0]
        max_pages = 20  # Safety limit

        for page_num in range(1, max_pages + 1):
            if page_num == 1:
                url = base_url
            else:
                url = f"{base_url}page/{page_num}/"

            print(f"  [SCRAPE] Page {page_num}: {url}")
            papers = self._scrape_topic_page(url)

            if not papers:
                print(f"  [DONE] No more on page {page_num}")
                break

            new_count = 0
            for p in papers:
                key = p["title"].lower().strip()
                if key not in seen_titles:
                    seen_titles.add(key)
                    all_papers.append(p)
                    new_count += 1

            print(f"    Found {len(papers)} publications ({new_count} new)")
            time.sleep(GREY_LIT_SCRAPE_DELAY)

        # Fetch details
        for i, p in enumerate(all_papers, 1):
            if p.get("detail_url"):
                print(f"    [{i}/{len(all_papers)}] {p['title'][:60]}...")
                abstract, pdf_url = self._get_pdf_and_abstract(p["detail_url"])
                p["abstract"] = abstract
                if pdf_url:
                    p["pdf_url"] = pdf_url
                else:
                    p["pdf_url"] = p["detail_url"]
                time.sleep(GREY_LIT_SCRAPE_DELAY)

        print(f"  [TOTAL] {len(all_papers)} CWF agriculture publications")
        return all_papers


# ── Source 9: Agriculture and Agri-Food Canada (AAFC) ──────────────────────

class AAFCHarvester(GreyLitHarvester):
    """
    Scrape AAFC publications.
    Visits the base urls and looks for PDF links.
    """
    def __init__(self):
        super().__init__("aafc")

    def scrape_papers(self):
        papers = []
        seen_urls = set()

        for url in self.source["scrape_urls"]:
            print(f"  [SCRAPE] {url}")
            soup = self._get_page(url)
            if not soup:
                continue

            # Find PDF links on the main page
            for link in soup.find_all("a", href=True):
                href = link["href"].strip()
                if not href.lower().endswith(".pdf"):
                    continue
                    
                full_url = urljoin(url, href)
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)
                
                title = self._clean_title(link.get_text(strip=True) or link.get("title", ""))
                if not title or len(title) < 5:
                    title = unquote(os.path.basename(href)).replace(".pdf", "").replace("-", " ")
                    title = self._clean_title(title)
                
                papers.append({
                    "title": title,
                    "pdf_url": full_url,
                    "year": extract_year_from_text(title),
                    "paper_type": detect_paper_type(title, "report"),
                    "detail_url": url,
                })
                
            time.sleep(GREY_LIT_SCRAPE_DELAY)
            
        print(f"  [TOTAL] {len(papers)} AAFC papers found")
        return papers


# ── Source 10: Statistics Canada ────────────────────────────────────────────

class StatCanAgHarvester(GreyLitHarvester):
    """
    Scrape Statistics Canada agriculture publications.
    Visits catalog pages and looks for PDF links, applying keyword filters.
    """
    def __init__(self):
        super().__init__("statcan_ag")

    def scrape_papers(self):
        papers = []
        seen_urls = set()

        for url in self.source["scrape_urls"]:
            print(f"  [SCRAPE] {url}")
            soup = self._get_page(url)
            if not soup:
                continue

            # First, look for direct PDF links
            pdf_links = []
            for link in soup.find_all("a", href=True):
                href = link["href"].strip()
                if href.lower().endswith(".pdf"):
                    pdf_links.append((link, urljoin(url, href)))
                
            # If no PDFs, try to find links that look like publication detail pages and scrape them
            # For StatCan, these often look like /pub/ or /n1/pub/
            detail_links = []
            for link in soup.find_all("a", href=True):
                href = link["href"].strip()
                if "/pub/" in href or "catalogue" in href or "article" in href:
                    full_url = urljoin(url, href)
                    if full_url not in seen_urls:
                        detail_links.append((link, full_url))
            
            # Extract from direct PDF links
            for link, full_url in pdf_links:
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)
                title = self._clean_title(link.get_text(strip=True))
                if not title or len(title) < 5:
                    title = unquote(os.path.basename(full_url)).replace(".pdf", "")
                
                if passes_keyword_filter(title):
                    papers.append({
                        "title": title,
                        "pdf_url": full_url,
                        "year": extract_year_from_text(title),
                        "paper_type": detect_paper_type(title, "report"),
                        "detail_url": url,
                    })

            # Check detail links (limit to 10 to avoid scraping too much on catalog pages)
            count = 0
            for link, detail_url in detail_links:
                if detail_url in seen_urls or count >= 10:
                    continue
                seen_urls.add(detail_url)
                
                title = self._clean_title(link.get_text(strip=True))
                if not title or len(title) < 5 or not passes_keyword_filter(title):
                    continue
                    
                print(f"    [DETAIL] {title[:60]}...")
                detail_soup = self._get_page(detail_url)
                if detail_soup:
                    for d_link in detail_soup.find_all("a", href=True):
                        d_href = d_link["href"].strip()
                        if d_href.lower().endswith(".pdf"):
                            d_full_url = urljoin(detail_url, d_href)
                            if d_full_url not in seen_urls:
                                seen_urls.add(d_full_url)
                                papers.append({
                                    "title": title,
                                    "pdf_url": d_full_url,
                                    "year": extract_year_from_text(title),
                                    "paper_type": detect_paper_type(title, "report"),
                                    "detail_url": detail_url,
                                })
                                count += 1
                                break # Found the PDF for this article
                time.sleep(GREY_LIT_SCRAPE_DELAY)

        print(f"  [TOTAL] {len(papers)} StatCan agriculture papers found")
        return papers


# ── Main Entry Point ────────────────────────────────────────────────────────

HARVESTERS = {
    "agrifoodecon": AgrifoodeconHarvester,
    "capi": CAPIHarvester,
    "fcc": FCCHarvester,
    "cdhowe": CDHoweHarvester,
    "iisd": IISDHarvester,
    "smartprosperity": SmartProsperityHarvester,
    "canadawest": CanadaWestHarvester,
    "aafc": AAFCHarvester,
    "statcan_ag": StatCanAgHarvester,
}


def harvest_grey_lit(sources=None):
    """
    Run grey literature harvesters.

    Args:
        sources: List of source keys to harvest, or None for all.
                 Valid keys: 'agrifoodecon', 'capi', 'fcc', 'cdhowe',
                             'iisd', 'smartprosperity', 'canadawest'
    """
    if sources is None:
        sources = list(HARVESTERS.keys())

    total_added = 0
    total_skipped = 0

    for key in sources:
        if key not in HARVESTERS:
            print(f"[WARN] Unknown source: {key}")
            continue

        harvester = HARVESTERS[key]()
        added, skipped = harvester.harvest()
        total_added += added
        total_skipped += skipped

    print(f"\n{'=' * 70}")
    print(f"ALL GREY LIT HARVESTING COMPLETE")
    print(f"  Total papers added:   {total_added}")
    print(f"  Total papers skipped: {total_skipped}")
    print(f"{'=' * 70}")

    return total_added, total_skipped


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Run specific sources
        sources = sys.argv[1:]
        harvest_grey_lit(sources)
    else:
        harvest_grey_lit()
