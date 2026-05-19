"""
Ag Econ Research Assistant — Streamlit Application
Semantic search + AI-powered literature review over 34,000+ agricultural economics papers.

Run with: streamlit run research_app.py
"""
import os
import sys
import streamlit as st

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_connection, get_stats, init_db
from config import BASE_DIR


# ── Caching Layer ────────────────────────────────────────────────────────────

@st.cache_resource
def get_embedding_model():
    from sentence_transformers import SentenceTransformer
    from embeddings import MODEL_NAME
    return SentenceTransformer(MODEL_NAME)


@st.cache_resource
def get_cached_chroma_collection():
    from embeddings import get_chroma_collection
    _, collection = get_chroma_collection()
    return collection


@st.cache_data(ttl=300)
def get_cached_stats():
    conn = get_connection()
    stats = get_stats(conn)
    conn.close()
    return stats


@st.cache_data(ttl=300)
def get_cached_full_text_count():
    try:
        conn = get_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM papers WHERE full_text IS NOT NULL AND full_text != ''"
        ).fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


@st.cache_data(ttl=300)
def get_cached_embedded_count():
    try:
        collection = get_cached_chroma_collection()
        return collection.count()
    except Exception:
        return 0


# ── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Ag Econ Research Assistant",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    .stApp {
        font-family: 'Inter', sans-serif;
    }

    .main-header {
        background: linear-gradient(135deg, #1a5632 0%, #2d8a4e 50%, #1a7a3a 100%);
        color: white;
        padding: 2rem 2.5rem;
        border-radius: 16px;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 24px rgba(26, 86, 50, 0.3);
    }

    .main-header h1 {
        margin: 0 0 0.3rem 0;
        font-size: 2rem;
        font-weight: 700;
        letter-spacing: -0.5px;
    }

    .main-header p {
        margin: 0;
        opacity: 0.9;
        font-size: 1rem;
        font-weight: 300;
    }

    .stat-card {
        background: linear-gradient(145deg, #ffffff, #f4f8f5);
        border: 1px solid #e0e8e3;
        padding: 1.2rem 1.5rem;
        border-radius: 12px;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        transition: transform 0.2s, box-shadow 0.2s;
    }

    .stat-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 16px rgba(0,0,0,0.08);
    }

    .stat-number {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1a5632;
        line-height: 1.2;
    }

    .stat-label {
        font-size: 0.82rem;
        color: #5a6b5f;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        font-weight: 500;
        margin-top: 0.2rem;
    }

    .result-card {
        background: #fff;
        border: 1px solid #e4e9e5;
        border-left: 4px solid #2d8a4e;
        padding: 1.2rem 1.5rem;
        border-radius: 0 12px 12px 0;
        margin-bottom: 0.8rem;
        transition: box-shadow 0.2s;
    }

    .result-card:hover {
        box-shadow: 0 3px 12px rgba(0,0,0,0.06);
    }

    .result-title {
        font-size: 1.05rem;
        font-weight: 600;
        color: #1a3a24;
        margin-bottom: 0.3rem;
        line-height: 1.35;
    }

    .result-meta {
        font-size: 0.82rem;
        color: #6b7d70;
        margin-bottom: 0.5rem;
    }

    .result-abstract {
        font-size: 0.9rem;
        color: #3a4a3f;
        line-height: 1.55;
    }

    .tier-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .tier-1 { background: #fde8e8; color: #b91c1c; }
    .tier-2 { background: #e0f0ff; color: #1e56a0; }
    .tier-3 { background: #fef3cd; color: #856404; }
    .tier-4 { background: #e8f5e9; color: #2e7d32; }

    .similarity-bar {
        height: 4px;
        background: linear-gradient(90deg, #2d8a4e, #4caf50);
        border-radius: 2px;
        margin-top: 0.3rem;
    }

    .synthesis-box {
        background: linear-gradient(145deg, #f8fdf9, #eef6f0);
        border: 1px solid #c8e0cc;
        border-radius: 14px;
        padding: 1.8rem;
        margin: 1rem 0;
        line-height: 1.7;
        font-size: 0.95rem;
    }

    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f4f8f5 0%, #e8f0ea 100%);
    }
</style>
""", unsafe_allow_html=True)


# ── Helper Functions ────────────────────────────────────────────────────────

TIER_NAMES = {1: "Canadian", 2: "US", 3: "OECD", 4: "Global"}
TIER_CSS = {1: "tier-1", 2: "tier-2", 3: "tier-3", 4: "tier-4"}


def render_header():
    st.markdown("""
    <div class="main-header">
        <h1>📚 Ag Econ Research Assistant</h1>
        <p>Semantic search & AI literature review over agricultural economics papers</p>
    </div>
    """, unsafe_allow_html=True)


def render_stats():
    stats = get_cached_stats()
    embedded_count = get_cached_embedded_count()
    ft_count = get_cached_full_text_count()

    cols = st.columns(6)
    stat_data = [
        (f"{stats['total_papers']:,}", "Total Papers"),
        (f"{stats.get('by_tier', {}).get('Canadian', 0):,}", "Canadian (Tier 1)"),
        (f"{stats['open_access']:,}", "Open Access"),
        (f"{stats['unique_authors']:,}", "Authors"),
        (f"{embedded_count:,}", "Embedded"),
        (f"{ft_count:,}", "Full Text"),
    ]

    for col, (number, label) in zip(cols, stat_data):
        col.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{number}</div>
            <div class="stat-label">{label}</div>
        </div>
        """, unsafe_allow_html=True)


def render_result_card(result, rank):
    tier = result.get("tier", 4)
    tier_name = TIER_NAMES.get(tier, "Other")
    tier_css = TIER_CSS.get(tier, "tier-4")
    similarity = result.get("similarity", 0)
    sim_pct = similarity * 100
    year = result.get("year", "N/A")
    if year == 0:
        year = "N/A"

    # Get full abstract from DB
    abstract = result.get("abstract_snippet", "")
    if len(abstract) > 250:
        abstract = abstract[:250] + "..."

    doi_link = ""
    if result.get("doi"):
        doi_link = f' · <a href="https://doi.org/{result["doi"]}" target="_blank">DOI ↗</a>'

    ft_badge = ""
    if result.get("has_full_text"):
        ft_badge = ' · <span style="background:#e0f7fa;color:#00695c;padding:1px 6px;border-radius:3px;font-size:0.72rem;font-weight:600;">📄 Full Text</span>'

    st.markdown(f"""
    <div class="result-card">
        <div class="result-title">{rank}. {result.get('title', 'Untitled')}</div>
        <div class="result-meta">
            <span class="tier-badge {tier_css}">{tier_name}</span>
            &nbsp; {year} · {result.get('source', 'Unknown')[:40]}
            · {result.get('citations', 0):,} citations
            · Match: {sim_pct:.0f}%{doi_link}{ft_badge}
        </div>
        <div class="result-abstract">{abstract}</div>
        <div class="similarity-bar" style="width: {max(sim_pct, 5)}%"></div>
    </div>
    """, unsafe_allow_html=True)


@st.cache_data(max_entries=50, ttl=900)
def do_semantic_search(query, n_results, tier_filter, year_range):
    """Run semantic search with filters."""
    from embeddings import search

    tier_val = {"All": None, "Canadian (1)": 1, "US (2)": 2, "OECD (3)": 3, "Global (4)": 4}.get(tier_filter)

    # Retrieve cached model and collection
    model = get_embedding_model()
    collection = get_cached_chroma_collection()

    results = search(
        query,
        n_results=n_results,
        tier_filter=tier_val,
        year_min=year_range[0],
        year_max=year_range[1],
        model=model,
        collection=collection,
    )

    # Enrich with abstracts and snippet of full text from DB
    if results:
        conn = get_connection()
        for r in results:
            paper = conn.execute(
                "SELECT abstract, title, SUBSTR(full_text, 1, 1000) as full_text_excerpt, "
                "CASE WHEN full_text IS NOT NULL AND full_text != '' THEN 1 ELSE 0 END as has_full_text "
                "FROM papers WHERE id = ?", (r["paper_id"],)
            ).fetchone()
            if paper:
                r["full_abstract"] = paper["abstract"] or ""
                r["abstract_snippet"] = (paper["abstract"] or "")[:300]
                r["full_text_excerpt"] = paper["full_text_excerpt"] or ""
                r["has_full_text"] = bool(paper["has_full_text"])
        conn.close()

    return results


def generate_literature_review(query, results, api_key):
    """Use Gemini to synthesize a literature review from search results."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    # Build context from top results — use full text excerpt when available
    paper_summaries = []
    for i, r in enumerate(results[:25], 1):
        if r.get("full_text_excerpt"):
            content = r["full_text_excerpt"]
            source_label = "Full Text Excerpt"
        else:
            content = r.get("full_abstract", r.get("abstract_snippet", ""))[:500]
            source_label = "Abstract"
        entry = f"""
Paper {i}: "{r.get('title', 'Untitled')}" ({r.get('year', 'N/A')})
Journal: {r.get('source', 'Unknown')}
Citations: {r.get('citations', 0)}
{source_label}: {content}
"""
        paper_summaries.append(entry)

    context = "\n---\n".join(paper_summaries)

    prompt = f"""You are an agricultural economics research analyst. Based on the following {len(results[:25])} research papers from a database of 34,000+ agricultural economics papers, provide a comprehensive literature review synthesis addressing the research question below.

RESEARCH QUESTION: {query}

PAPERS:
{context}

Please provide:
1. **Key Findings**: Summarize the main findings across these papers, identifying consensus and areas of disagreement.
2. **Methodological Approaches**: What methods are commonly used to study this topic?
3. **Canadian Context**: Highlight any Canadian-specific findings or implications.
4. **Research Gaps**: Identify areas that appear under-researched based on the available papers.
5. **Policy Implications**: What policy-relevant conclusions can be drawn?

Format your response with clear section headers. Cite papers by their number (e.g., Paper 1, Paper 5) throughout your synthesis. Be analytical and specific — avoid generic statements."""

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"**Error generating review:** {str(e)}\n\nMake sure your API key is valid. You can get one from [Google AI Studio](https://aistudio.google.com/apikey)."


# ── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### ⚙️ Search Settings")

    n_results = st.slider("Number of results", 5, 50, 20)

    tier_filter = st.selectbox(
        "Priority Tier",
        ["All", "Canadian (1)", "US (2)", "OECD (3)", "Global (4)"],
    )

    year_range = st.slider(
        "Year Range",
        1950, 2026, (1990, 2026),
    )

    st.markdown("---")
    st.markdown("### 🤖 AI Literature Review")
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        help="Get a free key from [Google AI Studio](https://aistudio.google.com/apikey)",
    )
    enable_ai = st.checkbox("Enable AI Synthesis", value=bool(api_key))

    st.markdown("---")
    st.markdown("### 📊 Quick Actions")
    if st.button("🔄 Rebuild Embeddings"):
        st.session_state["rebuild_embeddings"] = True

    st.markdown("---")
    st.caption("Powered by OpenAlex, AgEcon Search, ChromaDB, and Gemini")


# ── Main Content ────────────────────────────────────────────────────────────

render_header()

# Handle embedding rebuild
if st.session_state.get("rebuild_embeddings"):
    with st.spinner("Building embeddings (this may take a few minutes on first run)..."):
        # Clear caching to force reload after database update
        st.cache_data.clear()
        st.cache_resource.clear()

        # Load fresh model/collection references
        model = get_embedding_model()
        collection = get_cached_chroma_collection()

        from embeddings import build_embeddings
        count = build_embeddings(model=model, collection=collection)
        st.success(f"Embedded {count:,} paper abstracts!")
    st.session_state["rebuild_embeddings"] = False

render_stats()

st.markdown("")

# Search bar
col_search, col_btn = st.columns([5, 1])
with col_search:
    query = st.text_input(
        "🔍 Search",
        placeholder="e.g., impact of carbon pricing on Canadian agriculture",
        label_visibility="collapsed",
    )
with col_btn:
    search_btn = st.button("Search", type="primary", use_container_width=True)

# Example queries
if not query:
    st.markdown("**Try these example queries:**")
    example_cols = st.columns(3)
    examples = [
        "supply management dairy policy Canada",
        "impact of trade agreements on agricultural exports",
        "farm income risk management insurance programs",
    ]
    for col, ex in zip(example_cols, examples):
        if col.button(f"📌 {ex[:40]}...", key=f"ex_{ex[:20]}"):
            st.session_state["query"] = ex
            st.rerun()

# Use stored query from example buttons
if "query" in st.session_state and not query:
    query = st.session_state.pop("query", "")

# Run search
if query and (search_btn or query):
    # Check if embeddings exist
    try:
        collection = get_cached_chroma_collection()
        count = collection.count()
        if count == 0:
            st.warning("⚠️ No embeddings found. Click **Rebuild Embeddings** in the sidebar first.")
            st.stop()
    except Exception as e:
        st.error(f"Embedding database not ready: {e}")
        st.stop()

    with st.spinner("Searching across papers..."):
        results = do_semantic_search(query, n_results, tier_filter, year_range)

    if not results:
        st.info("No results found. Try broadening your search or adjusting filters.")
    else:
        # AI Literature Review
        if enable_ai and api_key:
            st.markdown("### 🧠 AI Literature Review")
            with st.spinner("Generating synthesis from top papers..."):
                review = generate_literature_review(query, results, api_key)
            st.markdown(f'<div class="synthesis-box">{review}</div>', unsafe_allow_html=True)

            with st.expander("📋 Copy full review"):
                st.text_area("Review text", review, height=300, label_visibility="collapsed")

        # Search Results
        st.markdown(f"### 🔎 Search Results ({len(results)} papers)")

        for i, result in enumerate(results, 1):
            render_result_card(result, i)

        # Export results
        st.markdown("---")
        col_exp1, col_exp2, _ = st.columns([1, 1, 3])

        with col_exp1:
            import json
            export_data = json.dumps(results, indent=2, default=str)
            st.download_button(
                "📥 Export JSON",
                export_data,
                file_name=f"search_results_{query[:30].replace(' ', '_')}.json",
                mime="application/json",
            )

        with col_exp2:
            csv_lines = ["Rank,Title,Year,Journal,Tier,Citations,Similarity,DOI"]
            for i, r in enumerate(results, 1):
                title = r.get('title', '').replace('"', "'")
                csv_lines.append(
                    f'{i},"{title}",{r.get("year", "")},{r.get("source", "")[:30]},'
                    f'{r.get("tier", "")},{r.get("citations", 0)},{r.get("similarity", 0):.3f},'
                    f'{r.get("doi", "")}'
                )
            csv_text = "\n".join(csv_lines)
            st.download_button(
                "📥 Export CSV",
                csv_text,
                file_name=f"search_results_{query[:30].replace(' ', '_')}.csv",
                mime="text/csv",
            )
