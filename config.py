"""
Configuration for the Agricultural Economics Research Database Pipeline.
"""
import os

# ── Base Paths ──────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ag_econ_research.db")
PDF_DIR = os.path.join(BASE_DIR, "papers")

# ── Storage Budget ──────────────────────────────────────────────────────────
# Maximum GB to use for PDF downloads. Set to 0 to skip PDF downloads entirely.
# Metadata (SQLite DB) is always collected regardless — it's tiny (~500 MB for 200K papers).
MAX_PDF_STORAGE_GB = 20  # Conservative default; user has ~92 GB free

# ── OpenAlex API ────────────────────────────────────────────────────────────
OPENALEX_BASE_URL = "https://api.openalex.org"
# Polite pool: providing an email gives you faster, more reliable access
OPENALEX_EMAIL = "ag.econ.research.pipeline@example.com"
OPENALEX_PER_PAGE = 200  # Max allowed by API
OPENALEX_RATE_LIMIT = 10  # Requests per second (polite pool)

# ── Priority Journals ──────────────────────────────────────────────────────
# Tier 1: Canadian
# Tier 2: US
# Tier 3: OECD / European
# Tier 4: Global / Other
PRIORITY_JOURNALS = [
    # ── Tier 1: Canadian ────────────────────────────────────────────────
    {
        "name": "Canadian Journal of Agricultural Economics",
        "issns": ["0008-3976", "1744-7976"],
        "openalex_source_id": "S179517972",
        "tier": 1,
    },
    # ── Tier 2: US ──────────────────────────────────────────────────────
    {
        "name": "American Journal of Agricultural Economics",
        "issns": ["0002-9092", "1467-8276"],
        "tier": 2,
    },
    {
        "name": "Journal of Agricultural and Resource Economics",
        "issns": ["1068-5502"],
        "tier": 2,
    },
    {
        "name": "Applied Economic Perspectives and Policy",
        "issns": ["2040-5790", "2040-5804"],
        "tier": 2,
    },
    {
        "name": "Food Policy",
        "issns": ["0306-9192"],
        "tier": 2,
    },
    # ── Tier 3: OECD / European ─────────────────────────────────────────
    {
        "name": "European Review of Agricultural Economics",
        "issns": ["0165-1587", "1464-3618"],
        "tier": 3,
    },
    {
        "name": "Journal of Agricultural Economics",
        "issns": ["0021-857X", "1477-9552"],
        "tier": 3,
    },
    {
        "name": "Australian Journal of Agricultural and Resource Economics",
        "issns": ["1364-985X", "1467-8489"],
        "tier": 3,
    },
    # ── Tier 4: Global ──────────────────────────────────────────────────
    {
        "name": "Agricultural Economics",
        "issns": ["0169-5150", "1574-0862"],
        "tier": 4,
    },
    {
        "name": "World Development",
        "issns": ["0305-750X"],
        "tier": 4,
    },
    {
        "name": "Journal of Development Economics",
        "issns": ["0304-3878"],
        "tier": 4,
    },
]

# ── OpenAlex Topic Filters ─────────────────────────────────────────────────
# These are used for the broader topic-based search (beyond specific journals).
# OpenAlex topic IDs for agricultural economics and related fields.
AG_ECON_SEARCH_TERMS = [
    "agricultural economics",
    "farm income",
    "agricultural policy",
    "agricultural trade",
    "food security",
    "rural development",
    "crop insurance",
    "farm management",
    "land use economics",
    "agribusiness",
    "supply management",
    "business risk management agriculture",
]

# ── AgEcon Search (OAI-PMH) ────────────────────────────────────────────────
AGECONSEARCH_OAI_URL = "http://ageconsearch.umn.edu/oai2d"
AGECONSEARCH_METADATA_PREFIX = "marcxml"

# ── Download Settings ───────────────────────────────────────────────────────
PDF_DOWNLOAD_DELAY = 1.0    # Seconds between downloads (be respectful)
PDF_DOWNLOAD_TIMEOUT = 30   # Seconds before timeout per file
PDF_MAX_RETRIES = 3         # Max retry attempts per file
REQUEST_TIMEOUT = 30        # Seconds for API requests
