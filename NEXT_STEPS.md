# Ag Econ Research Database — Next Steps

## Completed ✓
- Semantic Search Engine (vector-based natural language queries)
- AI-Powered Literature Review Assistant (Streamlit app)

## Future Enhancements

### 3. Topic Clustering & Trend Analysis
- Research trend visualization by decade (growing/declining topics)
- Citation network analysis (most influential papers/authors)
- Gap analysis (under-researched areas with high citation rates)
- Could be a Streamlit dashboard page

### 4. Canadian Content Enrichment
- **AAFC publication scraper** (government reports, public domain)
- **Statistics Canada working papers** on agriculture
- **University repository APIs** (U of Guelph, U of Saskatchewan, U of Alberta — OAI-PMH endpoints)
- Would significantly boost Tier 1 Canadian content

### 5. Automated Paper Summarization
- Batch-process PDFs through an LLM for structured summaries
- Key findings, methodology, data sources, policy implications
- Store in `paper_summaries` table for browsing without reading full papers

### 6. Export & Integration Tools
- **BibTeX/RIS export** for citation managers
- **Excel/CSV export** filtered by tier, topic, year
- **Zotero integration** for bulk import

### 7. Keyword Alert System
- Define keywords of interest (e.g., "carbon tax agriculture", "BRM programs")
- Weekly/monthly OpenAlex harvest with date filters
- Digest of new papers matching your interests
