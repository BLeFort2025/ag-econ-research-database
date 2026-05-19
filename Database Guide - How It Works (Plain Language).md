# How to Access & View the Ag Econ Research Database
## A Plain-Language Guide to Everything We Built

*Created: March 24, 2026*
*For: Ben LeF — Ontario Federation of Agriculture*

---

## What Is This System?

Think of this as your **personal library of agricultural economics research** — except instead of shelves of books, it's a searchable digital database containing **54,071 academic papers** about agricultural economics. You can ask it questions in plain English and it will find the most relevant papers, summarize them, and cite its sources.

Here's what makes it special:
- **It understands meaning**, not just keywords. Search for "impact of trade wars on Canadian farmers" and it finds papers about tariffs, NAFTA, retaliatory duties — even if those exact words aren't in the title.
- **It prioritizes Canadian research** — papers from the *Canadian Journal of Agricultural Economics* are ranked higher than generic global papers.
- **It can write literature reviews for you** using Google's AI (Gemini), grounded entirely in the papers in your database — no hallucinated sources.

---

## The Building Blocks (What Each File Does)

Here's your project folder, explained like a kitchen:

```
📁 Ag Economic Research Database/
│
├── 🗄️ ag_econ_research.db          ← THE DATABASE (the pantry - all 54,071 papers stored here)
├── 📁 chroma_db/                    ← THE SEARCH ENGINE (an index that understands meaning)
├── 📁 pdfs/                         ← THE FULL PAPERS (actual PDF files, up to 20 GB)
│
├── 🔧 openalex_harvester.py         ← Harvester #1: grabs papers from OpenAlex (global academic database)
├── 🔧 ageconsearch_harvester.py     ← Harvester #2: grabs papers from AgEcon Search (USDA/university archive)
├── 🔧 pdf_downloader.py             ← Downloads the actual PDF files for papers that have open access
├── 🔧 embeddings.py                 ← Converts paper abstracts into "meaning vectors" for smart search
├── 🔧 pipeline.py                   ← The "run everything" button — orchestrates harvesting + embedding
├── 🔧 config.py                     ← Settings: which journals to prioritize, storage limits, API keys
├── 🔧 db.py                         ← Database blueprint: defines the tables and prevents duplicates
│
├── 🌐 research_app.py               ← THE APP — the Streamlit web interface you interact with
├── 📄 requirements.txt              ← List of Python packages needed to run everything
├── 📄 README.md                     ← Quick start guide
└── 📄 .gitignore                    ← Tells GitHub to skip the big files (database, PDFs)
```

---

## How to Access the Database

### Option 1: The Streamlit App (Recommended — No Coding Required)

This is the **easiest way** to search and explore the database. It gives you a web interface in your browser.

**Steps:**
1. Open a terminal (Command Prompt or PowerShell)
2. Navigate to the project folder:
   ```
   cd "c:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Ben Desktop Files\Economic Analyst Position\Economic papers\Ag Economic Research Database"
   ```
3. Run the app:
   ```
   streamlit run research_app.py
   ```
4. Your browser will open to `http://localhost:8501`

**What you'll see:**
- **Search bar** — type any research question in plain English
- **Filter options** — narrow by year range, journal tier, or topic
- **Results** — ranked by relevance, showing title, abstract, journal, and year
- **AI Synthesis** — click to generate a literature review using Google Gemini (requires API key in `config.py`)
- **Export** — download results as CSV for use in Excel or other tools

### Option 2: Direct Database Access (DB Browser for SQLite)

If you want to browse the raw data like a spreadsheet:

1. Download **DB Browser for SQLite** (free): https://sqlitebrowser.org/
2. Open the file: `ag_econ_research.db`
3. Click "Browse Data" and select the `papers` table
4. You'll see columns for: title, abstract, year, journal, citation count, tier, DOI, etc.

This is useful for:
- Seeing exactly how many papers you have from each journal
- Filtering by year or tier
- Exporting specific subsets to CSV

### Option 3: Python (For Advanced Queries)

If you're comfortable with Python, you can query the database directly:

```python
import sqlite3

conn = sqlite3.connect("ag_econ_research.db")
cursor = conn.cursor()

# Example: Find all CJAE papers about supply management
cursor.execute("""
    SELECT title, year FROM papers
    WHERE source_name LIKE '%Canadian Journal of Agricultural%'
    AND abstract LIKE '%supply management%'
    ORDER BY year DESC
""")

for row in cursor.fetchall():
    print(f"[{row[1]}] {row[0]}")
```

---

## What's In the Database? (By the Numbers)

| Metric | Value |
|--------|-------|
| Total papers | **54,071** |
| Papers with abstracts (searchable) | **30,405** |
| Database file size | **68.6 MB** |
| Year range | 1911 – 2025 |
| Unique journals/sources | Hundreds |
| Semantic embeddings (smart search vectors) | 30,405 |

### How Papers Are Ranked (The "Tier" System)

| Tier | What It Means | Examples |
|------|---------------|----------|
| **Tier 1** | 🇨🇦 Canadian — highest priority | *Canadian Journal of Agricultural Economics*, *Canadian Public Policy* |
| **Tier 2** | 🇺🇸 US — strong secondary | *American Journal of Agricultural Economics*, *Journal of Agricultural Economics* |
| **Tier 3** | 🌍 OECD/International | *European Review of Agricultural Economics*, *Food Policy* |
| **Tier 4** | 🌐 Everything else | Conference papers, working papers, other sources |

When you search, Tier 1 papers are treated as the most authoritative because they're specifically about the Canadian context.

---

## How the Search Actually Works (The Magic Explained)

### Traditional Search (Like Google)
You type "wheat tariff" → the system looks for documents containing those exact words. Miss papers that say "grain import duties" even though they're about the same thing.

### Our Semantic Search (What We Built)
You type "wheat tariff" → the system converts your question into a **meaning vector** (a list of 384 numbers representing the concept). It then compares this to the meaning vectors of all 30,405 paper abstracts and returns the closest matches **by meaning**, not keywords.

This is why you can search for "impact of trade wars on Canadian cattle ranchers" and find papers titled "NAFTA Termination and Bilateral Agricultural Trade Flows" — they're about the same concept even though they use completely different words.

---

## How the AI Synthesis Works

When you click "Generate Literature Review" in the app:

1. The system runs a semantic search and finds the top 20–50 most relevant papers
2. It sends the abstracts to **Google Gemini AI** (Google's language model)
3. Gemini reads all the abstracts and writes a **structured literature review** — organized by theme, with citations
4. Every claim in the review links back to a specific paper in your database

**Important:** The AI can ONLY cite papers that are actually in your database. It cannot make things up or cite papers that don't exist. This is by design — it's a research tool, not a creative writing tool.

**To set up the AI synthesis**, you need a Google Gemini API key. Add it to `config.py`:
```python
GEMINI_API_KEY = "your-api-key-here"
```
You can get a free API key at: https://aistudio.google.com/app/apikey

---

## How to Add More Papers

The pipeline can be re-run anytime to harvest new papers:

```bash
# Harvest new papers from OpenAlex (priority journals)
python pipeline.py harvest --source openalex

# Harvest from AgEcon Search
python pipeline.py harvest --source ageconsearch

# Generate embeddings for new papers
python pipeline.py embed

# Check current status
python pipeline.py status
```

The system automatically **skips duplicates** — running it again won't create duplicate entries.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "streamlit not found" | Run `pip install streamlit` first |
| App opens but search returns nothing | Run `python pipeline.py embed` to generate search vectors |
| AI synthesis doesn't work | Add your Gemini API key to `config.py` |
| Database is empty | Run `python pipeline.py harvest --source openalex` |
| Want to start fresh | Delete `ag_econ_research.db` and `chroma_db/` folder, then re-harvest |
