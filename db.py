"""
Database layer for the Agricultural Economics Research Database.
SQLite-backed storage for paper metadata, authors, topics, and harvest tracking.
"""
import sqlite3
import os
from datetime import datetime
from config import DB_PATH


def get_connection():
    """Get a database connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS papers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            openalex_id     TEXT UNIQUE,
            doi             TEXT,
            title           TEXT NOT NULL,
            abstract        TEXT,
            year            INTEGER,
            citation_count  INTEGER DEFAULT 0,
            paper_type      TEXT,          -- journal-article, working-paper, etc.
            is_open_access  INTEGER DEFAULT 0,
            pdf_url         TEXT,
            pdf_local_path  TEXT,
            pdf_size_bytes  INTEGER,
            source_name     TEXT,          -- Journal or repository name
            source_issn     TEXT,
            priority_tier   INTEGER DEFAULT 4,  -- 1=Canadian, 2=US, 3=OECD, 4=Global
            harvest_source  TEXT,          -- 'openalex', 'ageconsearch', 'usda', etc.
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
        CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
        CREATE INDEX IF NOT EXISTS idx_papers_tier ON papers(priority_tier);
        CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source_name);
        CREATE INDEX IF NOT EXISTS idx_papers_oa ON papers(is_open_access);

        CREATE TABLE IF NOT EXISTS authors (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            openalex_id     TEXT UNIQUE,
            institution     TEXT,
            country         TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_authors_country ON authors(country);

        CREATE TABLE IF NOT EXISTS paper_authors (
            paper_id        INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
            author_id       INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
            position        INTEGER,  -- Author position (1=first, 2=second, etc.)
            PRIMARY KEY (paper_id, author_id)
        );

        CREATE TABLE IF NOT EXISTS topics (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            openalex_id     TEXT UNIQUE,
            subfield        TEXT,
            field           TEXT,
            domain          TEXT
        );

        CREATE TABLE IF NOT EXISTS paper_topics (
            paper_id        INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
            topic_id        INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
            score           REAL,  -- Relevance score from OpenAlex
            PRIMARY KEY (paper_id, topic_id)
        );

        CREATE TABLE IF NOT EXISTS harvest_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source          TEXT NOT NULL,
            query_desc      TEXT,
            started_at      TEXT DEFAULT (datetime('now')),
            completed_at    TEXT,
            records_added   INTEGER DEFAULT 0,
            records_skipped INTEGER DEFAULT 0,
            status          TEXT DEFAULT 'running',  -- running, completed, failed
            error_message   TEXT
        );
    """)

    conn.commit()
    conn.close()
    print(f"[DB] Database initialized at {DB_PATH}")


# ── Paper CRUD ──────────────────────────────────────────────────────────────

def paper_exists(conn, openalex_id=None, doi=None):
    """Check if a paper already exists by OpenAlex ID or DOI."""
    if openalex_id:
        row = conn.execute(
            "SELECT id FROM papers WHERE openalex_id = ?", (openalex_id,)
        ).fetchone()
        if row:
            return row["id"]
    if doi:
        row = conn.execute(
            "SELECT id FROM papers WHERE doi = ?", (doi,)
        ).fetchone()
        if row:
            return row["id"]
    return None


def insert_paper(conn, paper_data):
    """
    Insert a paper record. Returns the paper ID.
    paper_data is a dict with keys matching column names.
    Skips if already exists (by openalex_id or doi).
    """
    existing = paper_exists(
        conn,
        openalex_id=paper_data.get("openalex_id"),
        doi=paper_data.get("doi"),
    )
    if existing:
        return None  # Already exists

    cur = conn.execute(
        """INSERT INTO papers
           (openalex_id, doi, title, abstract, year, citation_count,
            paper_type, is_open_access, pdf_url, source_name, source_issn,
            priority_tier, harvest_source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            paper_data.get("openalex_id"),
            paper_data.get("doi"),
            paper_data.get("title"),
            paper_data.get("abstract"),
            paper_data.get("year"),
            paper_data.get("citation_count", 0),
            paper_data.get("paper_type"),
            1 if paper_data.get("is_open_access") else 0,
            paper_data.get("pdf_url"),
            paper_data.get("source_name"),
            paper_data.get("source_issn"),
            paper_data.get("priority_tier", 4),
            paper_data.get("harvest_source"),
        ),
    )
    return cur.lastrowid


def update_paper_pdf(conn, paper_id, pdf_local_path, pdf_size_bytes):
    """Update a paper's local PDF path and size."""
    conn.execute(
        """UPDATE papers
           SET pdf_local_path = ?, pdf_size_bytes = ?, updated_at = datetime('now')
           WHERE id = ?""",
        (pdf_local_path, pdf_size_bytes, paper_id),
    )


# ── Author CRUD ─────────────────────────────────────────────────────────────

def get_or_create_author(conn, name, openalex_id=None, institution=None, country=None):
    """Get an existing author or create a new one. Returns author ID."""
    if openalex_id:
        row = conn.execute(
            "SELECT id FROM authors WHERE openalex_id = ?", (openalex_id,)
        ).fetchone()
        if row:
            return row["id"]

    # Try matching by name (imperfect but handles non-OpenAlex sources)
    row = conn.execute(
        "SELECT id FROM authors WHERE name = ? AND openalex_id IS NULL",
        (name,)
    ).fetchone()
    if row:
        return row["id"]

    cur = conn.execute(
        "INSERT INTO authors (name, openalex_id, institution, country) VALUES (?, ?, ?, ?)",
        (name, openalex_id, institution, country),
    )
    return cur.lastrowid


def link_paper_author(conn, paper_id, author_id, position=None):
    """Link a paper to an author."""
    try:
        conn.execute(
            "INSERT OR IGNORE INTO paper_authors (paper_id, author_id, position) VALUES (?, ?, ?)",
            (paper_id, author_id, position),
        )
    except sqlite3.IntegrityError:
        pass  # Already linked


# ── Topic CRUD ──────────────────────────────────────────────────────────────

def get_or_create_topic(conn, name, openalex_id=None, subfield=None, field=None, domain=None):
    """Get an existing topic or create a new one. Returns topic ID."""
    if openalex_id:
        row = conn.execute(
            "SELECT id FROM topics WHERE openalex_id = ?", (openalex_id,)
        ).fetchone()
        if row:
            return row["id"]

    cur = conn.execute(
        "INSERT INTO topics (name, openalex_id, subfield, field, domain) VALUES (?, ?, ?, ?, ?)",
        (name, openalex_id, subfield, field, domain),
    )
    return cur.lastrowid


def link_paper_topic(conn, paper_id, topic_id, score=None):
    """Link a paper to a topic."""
    try:
        conn.execute(
            "INSERT OR IGNORE INTO paper_topics (paper_id, topic_id, score) VALUES (?, ?, ?)",
            (paper_id, topic_id, score),
        )
    except sqlite3.IntegrityError:
        pass


# ── Harvest Log ─────────────────────────────────────────────────────────────

def start_harvest_log(conn, source, query_desc=""):
    """Start a harvest log entry. Returns the log ID."""
    cur = conn.execute(
        "INSERT INTO harvest_log (source, query_desc) VALUES (?, ?)",
        (source, query_desc),
    )
    conn.commit()
    return cur.lastrowid


def complete_harvest_log(conn, log_id, records_added, records_skipped=0, status="completed", error=None):
    """Mark a harvest log entry as completed."""
    conn.execute(
        """UPDATE harvest_log
           SET completed_at = datetime('now'), records_added = ?,
               records_skipped = ?, status = ?, error_message = ?
           WHERE id = ?""",
        (records_added, records_skipped, status, error, log_id),
    )
    conn.commit()


# ── Statistics ──────────────────────────────────────────────────────────────

def get_stats(conn):
    """Get summary statistics about the database."""
    stats = {}

    # Total papers
    stats["total_papers"] = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]

    # By tier
    tiers = conn.execute(
        "SELECT priority_tier, COUNT(*) as cnt FROM papers GROUP BY priority_tier ORDER BY priority_tier"
    ).fetchall()
    tier_names = {1: "Canadian", 2: "US", 3: "OECD", 4: "Global"}
    stats["by_tier"] = {tier_names.get(r["priority_tier"], f"Tier {r['priority_tier']}"): r["cnt"] for r in tiers}

    # By source
    sources = conn.execute(
        "SELECT harvest_source, COUNT(*) as cnt FROM papers GROUP BY harvest_source ORDER BY cnt DESC"
    ).fetchall()
    stats["by_source"] = {r["harvest_source"]: r["cnt"] for r in sources}

    # Open access count
    stats["open_access"] = conn.execute(
        "SELECT COUNT(*) FROM papers WHERE is_open_access = 1"
    ).fetchone()[0]

    # Downloaded PDFs
    stats["pdfs_downloaded"] = conn.execute(
        "SELECT COUNT(*) FROM papers WHERE pdf_local_path IS NOT NULL"
    ).fetchone()[0]

    # Total PDF size
    size = conn.execute(
        "SELECT COALESCE(SUM(pdf_size_bytes), 0) FROM papers WHERE pdf_size_bytes IS NOT NULL"
    ).fetchone()[0]
    stats["pdf_storage_gb"] = round(size / (1024 ** 3), 2)

    # Year range
    year_range = conn.execute(
        "SELECT MIN(year), MAX(year) FROM papers WHERE year IS NOT NULL"
    ).fetchone()
    stats["year_range"] = (year_range[0], year_range[1]) if year_range[0] else (None, None)

    # Unique authors
    stats["unique_authors"] = conn.execute("SELECT COUNT(*) FROM authors").fetchone()[0]

    # Unique topics
    stats["unique_topics"] = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]

    # Top journals
    top_journals = conn.execute(
        "SELECT source_name, COUNT(*) as cnt FROM papers WHERE source_name IS NOT NULL GROUP BY source_name ORDER BY cnt DESC LIMIT 10"
    ).fetchall()
    stats["top_journals"] = [(r["source_name"], r["cnt"]) for r in top_journals]

    # Recent harvests
    harvests = conn.execute(
        "SELECT source, query_desc, started_at, records_added, status FROM harvest_log ORDER BY started_at DESC LIMIT 5"
    ).fetchall()
    stats["recent_harvests"] = [dict(r) for r in harvests]

    return stats


def get_pdf_storage_used_gb(conn):
    """Get total PDF storage used in GB."""
    size = conn.execute(
        "SELECT COALESCE(SUM(pdf_size_bytes), 0) FROM papers WHERE pdf_size_bytes IS NOT NULL"
    ).fetchone()[0]
    return size / (1024 ** 3)


if __name__ == "__main__":
    init_db()
