# 📚 Agricultural Economics Research Database

A Python-powered research platform for aggregating, searching, and synthesizing agricultural economics papers. Built for the Ontario Federation of Agriculture.

## What It Does

- **Harvests 50,000+ papers** from OpenAlex (11 priority journals) and AgEcon Search (213K+ open-access papers)
- **Semantic search** over paper abstracts using sentence-transformers + ChromaDB
- **AI literature review** — Gemini-powered synthesis from search results
- **Streamlit research assistant** — full UI with filters, export, and live search

## Priority Tiers

| Tier | Focus | Key Journals |
|------|-------|-------------|
| 1 | 🇨🇦 Canadian | Canadian Journal of Agricultural Economics |
| 2 | 🇺🇸 US | American Journal of Ag Economics, Food Policy |
| 3 | 🌍 OECD | European Review of Ag Economics, Journal of Ag Economics |
| 4 | 🌐 Global | Agricultural Economics, World Development |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database and harvest papers
python pipeline.py harvest-openalex --journals-only
python pipeline.py harvest-ageconsearch --max-records 20000

# Build search embeddings (~30 min first run)
python embeddings.py

# Launch the research assistant
streamlit run research_app.py

# Check database stats
python pipeline.py status
```

## Architecture

```
pipeline.py          → CLI orchestrator
├── config.py        → Journal list, API settings, storage budget
├── db.py            → SQLite database (papers, authors, topics)
├── openalex_harvester.py    → OpenAlex API (metadata + abstracts)
├── ageconsearch_harvester.py → AgEcon Search OAI-PMH (open-access papers)
├── pdf_downloader.py        → Budget-enforced PDF downloads
├── embeddings.py    → sentence-transformers + ChromaDB vector store
└── research_app.py  → Streamlit semantic search + AI lit review UI
```

## Storage

| Component | Typical Size |
|-----------|-------------|
| SQLite database (metadata) | ~100 MB |
| ChromaDB embeddings | ~200 MB |
| PDFs (optional, capped) | Up to 20 GB (configurable) |

Adjust `MAX_PDF_STORAGE_GB` in `config.py` to control PDF storage.

## AI Literature Review

The research assistant can generate AI-powered literature review syntheses using Google Gemini. Get a free API key from [Google AI Studio](https://aistudio.google.com/apikey) and enter it in the Streamlit sidebar.
