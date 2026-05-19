"""
Source registry for grey literature harvesters.
Defines the Canadian agri-food research organizations to scrape.
"""

# ── Source Definitions ──────────────────────────────────────────────────────

GREY_LIT_SOURCES = {
    "agrifoodecon": {
        "name": "Agri-Food Economic Systems",
        "short_name": "AES",
        "harvest_source": "grey_agrifoodecon",
        "base_url": "https://www.agrifoodecon.ca",
        "scrape_urls": [
            "https://www.agrifoodecon.ca/",
            "https://www.agrifoodecon.ca/research-papers-domestic-trade-policy",
            "https://www.agrifoodecon.ca/research-papers-farm-food-products-marketing",
            "https://www.agrifoodecon.ca/research-papers-management-economics",
            "https://www.agrifoodecon.ca/research-papers-economics-sustainability",
        ],
        "org_type": "research_firm",
        "default_paper_type": "policy-note",
        "default_authors": ["Al Mussell"],
        "needs_keyword_filter": False,
        "priority_tier": 1,
        "description": "Independent agri-food economic research (Al Mussell, formerly George Morris Centre)",
    },
    "capi": {
        "name": "Canadian Agri-Food Policy Institute",
        "short_name": "CAPI",
        "harvest_source": "grey_capi",
        "base_url": "https://capi-icpa.ca",
        "scrape_urls": [
            "https://capi-icpa.ca/explore/resources/",
        ],
        "org_type": "think_tank",
        "default_paper_type": "report",
        "default_authors": [],
        "needs_keyword_filter": False,
        "priority_tier": 1,
        "description": "Canada's leading agri-food policy think tank (288+ resources)",
    },
    "fcc": {
        "name": "Farm Credit Canada",
        "short_name": "FCC",
        "harvest_source": "grey_fcc",
        "base_url": "https://www.fcc-fac.ca",
        "scrape_urls": [
            "https://www.fcc-fac.ca/en/knowledge/economics",
        ],
        "org_type": "crown_corporation",
        "default_paper_type": "report",
        "default_authors": [],
        "needs_keyword_filter": False,
        "priority_tier": 1,
        "description": "FCC Economics: farmland values, food & beverage reports, economic analyses",
    },
    "cdhowe": {
        "name": "C.D. Howe Institute",
        "short_name": "CDHowe",
        "harvest_source": "grey_cdhowe",
        "base_url": "https://www.cdhowe.org",
        "scrape_urls": [
            "https://www.cdhowe.org/?s=agriculture",
            "https://www.cdhowe.org/?s=food+policy",
            "https://www.cdhowe.org/?s=agri-food",
            "https://www.cdhowe.org/?s=supply+management",
            "https://www.cdhowe.org/?s=farmland",
        ],
        "org_type": "think_tank",
        "default_paper_type": "report",
        "default_authors": [],
        "needs_keyword_filter": True,
        "priority_tier": 1,
        "description": "Leading economic policy think tank — filtered to ag/food topics",
    },
    "iisd": {
        "name": "International Institute for Sustainable Development",
        "short_name": "IISD",
        "harvest_source": "grey_iisd",
        "base_url": "https://www.iisd.org",
        "scrape_urls": [
            "https://www.iisd.org/publications",
        ],
        "org_type": "think_tank",
        "default_paper_type": "report",
        "default_authors": [],
        "needs_keyword_filter": True,
        "priority_tier": 1,
        "description": "IISD publications — keyword-filtered for food & agriculture",
    },
    "smartprosperity": {
        "name": "Smart Prosperity Institute",
        "short_name": "SmartProsperity",
        "harvest_source": "grey_smartprosperity",
        "base_url": "https://institute.smartprosperity.ca",
        "scrape_urls": [
            "https://institute.smartprosperity.ca/library",
        ],
        "org_type": "think_tank",
        "default_paper_type": "report",
        "default_authors": [],
        "needs_keyword_filter": True,
        "priority_tier": 1,
        "description": "Clean growth + ag research (soil health, BMP, circular ag)",
    },
    "canadawest": {
        "name": "Canada West Foundation",
        "short_name": "CWF",
        "harvest_source": "grey_canadawest",
        "base_url": "https://cwf.ca",
        "scrape_urls": [
            "https://cwf.ca/topic/agriculture/",
        ],
        "org_type": "think_tank",
        "default_paper_type": "report",
        "default_authors": [],
        "needs_keyword_filter": False,  # Using ag topic page = pre-filtered
        "priority_tier": 1,
        "description": "Western Canada ag infrastructure, trade, labour, food policy",
    },

    # ── Federal Government Sources ────────────────────────────────────────────

    "aafc": {
        "name": "Agriculture and Agri-Food Canada",
        "short_name": "AAFC",
        "harvest_source": "grey_aafc",
        "base_url": "https://publications.gc.ca",
        "scrape_urls": [
            # Search the federal publications portal for AAFC (department code A38)
            "https://publications.gc.ca/collections/published-works/agr-eng.html",
            # AAFC's own research publications index
            "https://agriculture.canada.ca/en/science/publications",
            # Open Government AAFC publications dataset
            "https://open.canada.ca/data/en/dataset?organization=aafc-aac&res_format=PDF",
        ],
        "org_type": "federal_government",
        "default_paper_type": "report",
        "default_authors": ["Agriculture and Agri-Food Canada"],
        "needs_keyword_filter": False,  # All AAFC outputs are ag-related by definition
        "priority_tier": 1,
        "description": (
            "Agriculture and Agri-Food Canada — federal departmental reports, "
            "sector outlooks, farm income forecasts, agri-food trade analyses, "
            "policy evaluations, and program assessments."
        ),
    },

    "statcan_ag": {
        "name": "Statistics Canada — Agriculture & Agri-Food Series",
        "short_name": "StatCan-Ag",
        "harvest_source": "grey_statcan_ag",
        "base_url": "https://www150.statcan.gc.ca",
        "scrape_urls": [
            # Farm and agriculture subject page (pre-filtered to ag topic)
            "https://www150.statcan.gc.ca/n1/en/subjects/agriculture_and_food",
            # Economic and Social Reports (cat. 36-28-0001) — contains frequent ag research
            "https://www150.statcan.gc.ca/n1/en/catalogue/36280001",
            # Agriculture Economic Statistics (cat. 21-004-X)
            "https://www150.statcan.gc.ca/n1/en/catalogue/21004X",
            # Insights on Canadian Society — ag / rural themes
            "https://www150.statcan.gc.ca/n1/en/catalogue/75006X",
            # Survey of Financial Security / Farm Financial Survey releases
            "https://www150.statcan.gc.ca/n1/en/subjects/agriculture_and_food/farm_finances",
        ],
        "org_type": "federal_government",
        "default_paper_type": "report",
        "default_authors": ["Statistics Canada"],
        "needs_keyword_filter": True,   # Series covers many topics; filter to ag/food/rural
        "priority_tier": 1,
        "description": (
            "Statistics Canada agriculture & agri-food publications — farm income, "
            "farmland prices, TFW labour, food price inflation, Census of Agriculture "
            "analyses, and agri-food trade statistics."
        ),
    },

    "omafra": {
        "name": "Ontario Ministry of Agriculture, Food and Rural Affairs",
        "short_name": "OMAFRA",
        "harvest_source": "grey_omafra",
        "base_url": "https://www.ontario.ca",
        "scrape_urls": [
            "https://www.ontario.ca/page/agriculture-and-rural-affairs",
            "https://www.ontario.ca/page/agricultural-information",
            # OMAFRA publication landing pages
            "https://www.ontario.ca/search/land-use-planning?keyword=agriculture",
            "https://www.ontario.ca/page/omafra-strategic-agriculture",
        ],
        "org_type": "provincial_government",
        "default_paper_type": "report",
        "default_authors": ["OMAFRA"],
        "needs_keyword_filter": False,  # Pre-filtered to ag/rural
        "priority_tier": 1,
        "description": (
            "Ontario OMAFRA — provincial agricultural policy reports, "
            "field crop budgets (Publication 60), hedgerow/BMP guidelines, "
            "farm income surveys, and rural affairs analyses."
        ),
    },

    "pbo": {
        "name": "Parliamentary Budget Officer",
        "short_name": "PBO",
        "harvest_source": "grey_pbo",
        "base_url": "https://www.pbo-dpb.ca",
        "scrape_urls": [
            "https://www.pbo-dpb.ca/en/publications",
        ],
        "org_type": "federal_government",
        "default_paper_type": "report",
        "default_authors": ["Parliamentary Budget Officer"],
        "needs_keyword_filter": True,   # Broad mandate; filter to ag/food/rural topics
        "priority_tier": 1,
        "description": (
            "Parliamentary Budget Officer — keyword-filtered for agriculture, agri-food, "
            "supply management, farm income, food prices, and rural Canada reports."
        ),
    },
}


# ── Paper Type Detection ────────────────────────────────────────────────────

PAPER_TYPE_PATTERNS = [
    ("policy-note", ["policy note", "policy advisory", "briefing note"]),
    ("policy-brief", ["policy brief", "policy concepts"]),
    ("perspective-paper", ["perspective", "commentary"]),
    ("report", ["report", "analysis", "survey", "assessment", "study"]),
    ("working-paper", ["working paper", "discussion paper"]),
]


def detect_paper_type(title, default="report"):
    """Detect paper type from title text."""
    title_lower = title.lower()
    for paper_type, patterns in PAPER_TYPE_PATTERNS:
        for pattern in patterns:
            if pattern in title_lower:
                return paper_type
    return default


# ── Year Extraction ─────────────────────────────────────────────────────────

import re

MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
]

def extract_year_from_text(text):
    """Extract a publication year from title or description text."""
    if not text:
        return None
    # Look for 4-digit year patterns, prefer later in text (usually date)
    years = re.findall(r'\b(20[0-2]\d|19\d{2})\b', text)
    if years:
        # Return the last year found (usually the publication date)
        return int(years[-1])
    # Check for short year like "Mar-26" or "Nov-21"
    short_year = re.findall(r'[/-](\d{2})\b', text)
    if short_year:
        yr = int(short_year[-1])
        return 2000 + yr if yr < 50 else 1900 + yr
    return None


# ── Agri-Food Keyword Filter ───────────────────────────────────────────────

AGRI_FOOD_KEYWORDS = [
    # Core agriculture
    "agricultur", "agri-food", "agrifood", "farming", "farm ",
    "livestock", "crop", "dairy", "poultry", "beef", "pork",
    "grain", "oilseed", "canola", "wheat", "corn", "soybean",
    "horticultur", "greenhouse", "aquaculture", "apiculture",
    # Food system
    "food policy", "food security", "food system", "food supply",
    "food processing", "food price", "food inflation",
    "food value chain", "food manufacturing", "agri-food sector",
    # Canadian ag policy & programs
    "supply management", "business risk management", "BRM",
    "AgriStability", "AgriInvest", "AgriInsurance", "AgriRecovery",
    "Sustainable Canadian Agricultural Partnership", "SCAP",
    "Canadian Agricultural Partnership", "Growing Forward",
    "farmland", "farm income", "farm tax", "farm gate",
    # Labour & SAWP
    "temporary foreign worker", "TFW",
    "Seasonal Agricultural Worker", "SAWP",
    "farm labour", "agricultural worker", "migrant worker",
    # Trade
    "agricultural trade", "agri-food trade", "CUSMA", "USMCA",
    "agricultural tariff", "supply chain", "agri-food export",
    "agri-food import",
    # Rural
    "rural development", "rural econom", "rural community",
    "rural Canada", "rural Ontario",
    # Environment-ag intersection
    "soil health", "beneficial management practice", "BMP",
    "agricultural sustainab", "carbon farming", "agroforestry",
    "fertilizer", "pesticide", "neonicotinoid",
    "greenhouse gas", "net-zero agriculture",
    # AAFC / StatCan / OMAFRA report language
    "farm financial", "farm debt", "net farm income",
    "Census of Agriculture", "Farm Financial Survey",
    "farm operating expense", "farm capital",
    "agri-food GDP", "food and beverage",
]


def passes_keyword_filter(title, abstract=None):
    """Check if a paper's title + abstract contains at least one agri-food keyword."""
    text = (title or "").lower()
    if abstract:
        text += " " + abstract.lower()
    return any(kw.lower() in text for kw in AGRI_FOOD_KEYWORDS)

