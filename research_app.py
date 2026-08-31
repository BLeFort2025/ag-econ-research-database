"""
Ag Econ Research Assistant — Streamlit Application
Semantic search + Project Dossiers + AI-powered literature review memory + Empirical Parameter Mining over 89,000+ agricultural economics papers.

Run with: streamlit run research_app.py
"""
import os
import sys
import json
import streamlit as st

# Ensure project root is on path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from db import (
    get_connection, get_stats, init_db,
    get_all_projects, get_project, create_project, update_project, delete_project,
    add_paper_to_project, remove_paper_from_project, update_project_paper, get_project_papers,
    get_paper_project_memberships, save_project_synthesis, get_project_syntheses,
    seed_initial_projects,
    add_empirical_parameter, get_empirical_parameters, update_empirical_parameter,
    delete_empirical_parameter, export_parameters_for_simulator, seed_empirical_parameters,
    save_policy_brief, get_project_briefs, delete_policy_brief
)
from parameter_extractor import extract_parameters_from_text, extract_and_save_paper_parameters
from policy_brief_generator import (
    generate_policy_brief, export_brief_to_docx, export_brief_to_html, BRIEF_TEMPLATES
)

# ── Initialize DB & Seed Initial Projects ───────────────────────────────────
init_db()
seed_initial_projects()
seed_empirical_parameters()


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


@st.cache_data(ttl=120)
def get_cached_stats():
    conn = get_connection()
    stats = get_stats(conn)
    conn.close()
    return stats


@st.cache_data(ttl=120)
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


@st.cache_data(ttl=120)
def get_cached_embedded_count():
    try:
        collection = get_cached_chroma_collection()
        return collection.count()
    except Exception:
        return 0


# ── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Ag Econ Research Intelligence Platform",
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
        padding: 1.8rem 2.2rem;
        border-radius: 14px;
        margin-bottom: 1.2rem;
        box-shadow: 0 4px 20px rgba(26, 86, 50, 0.25);
    }

    .main-header h1 {
        margin: 0 0 0.2rem 0;
        font-size: 1.9rem;
        font-weight: 700;
        letter-spacing: -0.5px;
    }

    .main-header p {
        margin: 0;
        opacity: 0.92;
        font-size: 0.95rem;
        font-weight: 300;
    }

    .stat-card {
        background: linear-gradient(145deg, #ffffff, #f4f8f5);
        border: 1px solid #e0e8e3;
        padding: 1rem 1.2rem;
        border-radius: 12px;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.03);
    }

    .stat-number {
        font-size: 1.6rem;
        font-weight: 700;
        color: #1a5632;
        line-height: 1.1;
    }

    .stat-label {
        font-size: 0.78rem;
        color: #5a6b5f;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        font-weight: 600;
        margin-top: 0.2rem;
    }

    .result-card {
        background: #fff;
        border: 1px solid #e4e9e5;
        border-left: 4px solid #2d8a4e;
        padding: 1.1rem 1.4rem;
        border-radius: 0 12px 12px 0;
        margin-bottom: 0.7rem;
    }

    .result-title {
        font-size: 1.02rem;
        font-weight: 600;
        color: #1a3a24;
        margin-bottom: 0.25rem;
        line-height: 1.35;
    }

    .result-meta {
        font-size: 0.82rem;
        color: #6b7d70;
        margin-bottom: 0.45rem;
    }

    .result-abstract {
        font-size: 0.88rem;
        color: #3a4a3f;
        line-height: 1.5;
    }

    .tier-badge {
        display: inline-block;
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.4px;
    }

    .tier-1 { background: #fde8e8; color: #b91c1c; }
    .tier-2 { background: #e0f0ff; color: #1e56a0; }
    .tier-3 { background: #fef3cd; color: #856404; }
    .tier-4 { background: #e8f5e9; color: #2e7d32; }

    .tag-badge {
        display: inline-block;
        background: #eef2ff;
        color: #4338ca;
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 600;
        margin-right: 4px;
    }

    .core-badge {
        display: inline-block;
        background: #fef3c7;
        color: #92400e;
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 700;
    }

    .project-header-box {
        background: #f8faf9;
        border: 1px solid #d9e4dd;
        border-radius: 12px;
        padding: 1.4rem;
        margin-bottom: 1.2rem;
    }

    .synthesis-box {
        background: linear-gradient(145deg, #f8fdf9, #eef6f0);
        border: 1px solid #c8e0cc;
        border-radius: 12px;
        padding: 1.6rem;
        margin: 0.8rem 0;
        line-height: 1.65;
        font-size: 0.93rem;
    }

    .note-box {
        background: #fffbeb;
        border-left: 3px solid #f59e0b;
        padding: 0.5rem 0.8rem;
        margin: 0.4rem 0;
        font-size: 0.82rem;
        color: #78350f;
        border-radius: 0 6px 6px 0;
    }
</style>
""", unsafe_allow_html=True)


# ── Constants & Helpers ─────────────────────────────────────────────────────

TIER_NAMES = {1: "Canadian", 2: "US", 3: "OECD", 4: "Global"}
TIER_CSS = {1: "tier-1", 2: "tier-2", 3: "tier-3", 4: "tier-4"}
RELEVANCE_TAGS = ["Core Reference", "Parameter Source", "Methodology", "Background / Context", "Policy Precedent"]


def render_header():
    st.markdown("""
    <div class="main-header">
        <h1>📚 Ag Econ Research Intelligence Platform</h1>
        <p>Semantic retrieval, project dossiers, and AI-powered literature review memory for Ontario agriculture</p>
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
        (f"{embedded_count:,}", "Search Vectors"),
        (f"{ft_count:,}", "Full Text"),
    ]

    for col, (number, label) in zip(cols, stat_data):
        col.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{number}</div>
            <div class="stat-label">{label}</div>
        </div>
        """, unsafe_allow_html=True)


@st.cache_data(max_entries=50, ttl=900)
def do_semantic_search(query, n_results, tier_filter, year_range):
    """Run semantic search with filters."""
    from embeddings import search

    tier_val = {"All": None, "Canadian (1)": 1, "US (2)": 2, "OECD (3)": 3, "Global (4)": 4}.get(tier_filter)

    model = get_embedding_model()
    collection = get_cached_chroma_collection()

    try:
        results = search(
            query,
            n_results=n_results,
            tier_filter=tier_val,
            year_min=year_range[0],
            year_max=year_range[1],
            model=model,
            collection=collection,
        )
    except Exception:
        # If stale cached handle, clear cache and retry
        st.cache_resource.clear()
        results = search(
            query,
            n_results=n_results,
            tier_filter=tier_val,
            year_min=year_range[0],
            year_max=year_range[1],
        )

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
            
            # Fetch existing dossier memberships
            memberships = get_paper_project_memberships(conn, r["paper_id"])
            r["memberships"] = memberships
        conn.close()

    return results


def generate_gemini_synthesis(query, papers_data, api_key, prior_synthesis=None):
    """Generate structured literature review using Gemini."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
    except Exception:
        model = genai.GenerativeModel("gemini-1.5-flash")

    paper_summaries = []
    for i, p in enumerate(papers_data[:25], 1):
        content = p.get("full_text_excerpt") or p.get("full_abstract") or p.get("abstract") or ""
        notes = f"\nAnalyst Note: {p.get('analyst_notes')}" if p.get("analyst_notes") else ""
        entry = f"""Paper {i}: "{p.get('title', 'Untitled')}" ({p.get('year', 'N/A')})
Source: {p.get('source_name', p.get('source', 'Unknown'))} | Citations: {p.get('citation_count', p.get('citations', 0))} | Tier: {p.get('priority_tier', p.get('tier', 4))}{notes}
Excerpt: {content[:600]}"""
        paper_summaries.append(entry)

    context = "\n---\n".join(paper_summaries)

    prior_context = ""
    if prior_synthesis:
        prior_context = f"""
PRIOR ESTABLISHED WORK / SYNTHESIS (Build on and compare with this):
\"\"\"{prior_synthesis[:2500]}\"\"\"
"""

    prompt = f"""You are an agricultural economics senior research analyst at the Ontario Federation of Agriculture (OFA). 
Based on the following {len(papers_data[:25])} research papers from our peer-reviewed and grey literature database, provide a rigorous, evidence-based literature review synthesis addressing the research question below.

RESEARCH QUESTION: {query}
{prior_context}
PAPERS TO SYNTHESIZE:
{context}

Please provide a structured synthesis with the following sections:
1. **Executive Summary & Key Empirical Findings**: Consensus points, key parameters (elasticities, multipliers, pass-through rates), and areas of divergence.
2. **Methodological & Econometric Approaches**: Input-Output, CGE, econometric models, and datasets used.
3. **Canadian & Ontario Policy Context**: Direct relevance to Ontario agriculture, provincial supply chains, or federal policy.
4. **Comparison / New Insights**: Explicitly highlight new insights or parameter adjustments compared to prior baseline work.
5. **Research Gaps & Actionable Takeaways for OFA**: Defensible takeaways for farm policy advocacy and economic modeling.

Cite papers by number and title (e.g. Paper 1, Paper 4). Ground all claims strictly in the provided paper evidence."""

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"**Error generating review:** {str(e)}\n\nMake sure your Gemini API key is valid."


# ── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### ⚙️ Research Platform Settings")

    n_results = st.slider("Max Search Results", 5, 50, 20)

    tier_filter = st.selectbox(
        "Priority Tier Filter",
        ["All", "Canadian (1)", "US (2)", "OECD (3)", "Global (4)"],
    )

    year_range = st.slider(
        "Publication Year Range",
        1950, 2026, (1990, 2026),
    )

    st.markdown("---")
    st.markdown("### 🤖 Gemini AI API")
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        help="Get a free key from Google AI Studio (aistudio.google.com/apikey)",
    )
    if not api_key:
        # Check environment variable
        api_key = os.environ.get("GEMINI_API_KEY", "")

    st.markdown("---")
    st.markdown("### ⚙️ Pipeline & Maintenance")

    with st.expander("📥 Ingestion & Vector Maintenance", expanded=False):
        st.markdown("##### 📄 PDF & Full-Text Ingestion")
        pdf_batch_limit = st.slider("Batch Size (PDFs)", min_value=5, max_value=100, value=25, step=5)
        tier_choice = st.selectbox("Target Tier", [1, 2, 3, 4], format_func=lambda x: {1: "Tier 1: Canadian Focus", 2: "Tier 2: US / Major Ag Econ", 3: "Tier 3: OECD", 4: "Tier 4: Global"}[x])
        if st.button("📥 Download & Extract Full-Text PDFs", use_container_width=True):
            with st.spinner(f"Downloading and extracting Tier {tier_choice} PDFs..."):
                from pdf_downloader import download_pdfs
                dl, fail = download_pdfs(limit=pdf_batch_limit, tier=tier_choice)
                st.success(f"Processed batch: {dl} PDFs saved & extracted with PyMuPDF, {fail} failed.")
                st.rerun()

        st.markdown("---")
        st.markdown("##### 🔄 Vector Index Maintenance")
        if st.button("Rebuild All Embeddings", use_container_width=True):
            st.session_state["trigger_rebuild"] = True

        if st.session_state.get("trigger_rebuild"):
            with st.spinner("Rebuilding ChromaDB embeddings..."):
                st.cache_data.clear()
                st.cache_resource.clear()
                model = get_embedding_model()
                collection = get_cached_chroma_collection()
                from embeddings import build_embeddings
                count = build_embeddings(model=model, collection=collection)
                st.success(f"Successfully embedded {count:,} paper abstracts!")
            st.session_state["trigger_rebuild"] = False

    st.markdown("---")
    st.caption("Agricultural Economics Research Intelligence Platform · Ontario Federation of Agriculture")


# ── Main Content Header & Stats ─────────────────────────────────────────────

render_header()
render_stats()
st.markdown("")

# ── Navigation Tabs ─────────────────────────────────────────────────────────

tab_search, tab_dossiers, tab_canvas, tab_params, tab_briefs = st.tabs([
    "🔍 Search & Discover",
    "📁 Project Dossiers & Saved Workspaces",
    "🧠 Literature Review Canvas & Memory",
    "📊 Empirical Parameters & Simulator Calibration",
    "🏛️ Policy Briefs & Board Memos"
])


# ═════════════════════════════════════════════════════════════════════════════
# TAB 1: SEARCH & DISCOVER
# ═════════════════════════════════════════════════════════════════════════════

with tab_search:
    st.markdown("#### 🔍 Semantic Search Across 89,000+ Agricultural Economics Papers")

    col_search, col_btn = st.columns([5, 1])
    with col_search:
        search_query = st.text_input(
            "Search query",
            placeholder="e.g., Ontario local food economic multiplier import substitution",
            label_visibility="collapsed",
            key="main_search_input"
        )
    with col_btn:
        search_clicked = st.button("Search", type="primary", use_container_width=True, key="search_run_btn")

    # Example queries
    if not search_query:
        st.markdown("**Suggested Research Queries:**")
        ex_cols = st.columns(3)
        examples = [
            "Ontario local food economic multiplier import substitution",
            "tariff pass-through rate Canadian agriculture trade dispute",
            "AgriStability crop insurance whole farm business risk management",
        ]
        for col, ex in zip(ex_cols, examples):
            if col.button(f"📌 {ex[:38]}...", key=f"ex_btn_{ex[:20]}"):
                st.session_state["active_query"] = ex
                st.rerun()

    if "active_query" in st.session_state and not search_query:
        search_query = st.session_state.pop("active_query", "")

    # Execute search
    if search_query and (search_clicked or search_query):
        with st.spinner("Searching semantic vector index & metadata..."):
            results = do_semantic_search(search_query, n_results, tier_filter, year_range)

        if not results:
            st.info("No matching papers found. Try adjusting tier or year filters.")
        else:
            conn = get_connection()
            all_projects = get_all_projects(conn)
            conn.close()

            # AI Review Generation
            if api_key:
                with st.expander("🤖 Generate AI Literature Synthesis from Search Results", expanded=False):
                    if st.button("🧠 Synthesize Top Results with Gemini", key="synth_search_btn"):
                        with st.spinner("Generating synthesis..."):
                            synth_text = generate_gemini_synthesis(search_query, results, api_key)
                            st.session_state["temp_search_synth"] = synth_text
                    
                    if "temp_search_synth" in st.session_state:
                        st.markdown(f'<div class="synthesis-box">{st.session_state["temp_search_synth"]}</div>', unsafe_allow_html=True)
                        
                        # Save to project option
                        if all_projects:
                            st.markdown("##### 💾 Save Synthesis to a Project Dossier")
                            c_proj, c_save = st.columns([3, 1])
                            with c_proj:
                                target_proj_id = st.selectbox(
                                    "Select Target Dossier",
                                    options=[p["id"] for p in all_projects],
                                    format_func=lambda x: next((p["name"] for p in all_projects if p["id"] == x), str(x)),
                                    key="save_synth_proj_select"
                                )
                            with c_save:
                                if st.button("Save to Dossier", key="save_synth_btn"):
                                    c_conn = get_connection()
                                    save_project_synthesis(
                                        c_conn, target_proj_id,
                                        title=f"Search Synthesis: {search_query[:50]}",
                                        query_prompt=search_query,
                                        synthesis_markdown=st.session_state["temp_search_synth"]
                                    )
                                    c_conn.close()
                                    st.success("Synthesis saved to dossier!")

            st.markdown(f"### 🔎 Search Results ({len(results)} papers)")

            for i, r in enumerate(results, 1):
                tier = r.get("tier", 4)
                tier_name = TIER_NAMES.get(tier, "Other")
                tier_css = TIER_CSS.get(tier, "tier-4")
                similarity = r.get("similarity", 0)
                sim_pct = similarity * 100
                year = r.get("year") or "N/A"
                doi_link = f' · <a href="https://doi.org/{r["doi"]}" target="_blank">DOI ↗</a>' if r.get("doi") else ""
                ft_badge = ' · <span style="background:#e0f7fa;color:#00695c;padding:1px 6px;border-radius:3px;font-size:0.72rem;font-weight:600;">📄 Full Text</span>' if r.get("has_full_text") else ""

                # Existing dossier badges
                membership_badges = ""
                if r.get("memberships"):
                    for m in r["memberships"]:
                        membership_badges += f' · <span class="tag-badge">📁 {m["name"]}</span>'

                st.markdown(f"""
                <div class="result-card">
                    <div class="result-title">{i}. {r.get('title', 'Untitled')}</div>
                    <div class="result-meta">
                        <span class="tier-badge {tier_css}">{tier_name}</span>
                        &nbsp; {year} · {r.get('source', 'Unknown')[:40]}
                        · {r.get('citations', 0):,} citations
                        · Match: {sim_pct:.0f}%{doi_link}{ft_badge}{membership_badges}
                    </div>
                    <div class="result-abstract">{r.get('abstract_snippet', '')}</div>
                </div>
                """, unsafe_allow_html=True)

                # Dossier Quick Save Drawer
                with st.expander(f"📁 Save Paper #{i} to a Research Dossier", expanded=False):
                    if not all_projects:
                        st.info("No dossiers created yet. Create one in the **Project Dossiers** tab.")
                    else:
                        c1, c2, c3, c4 = st.columns([3, 2, 4, 2])
                        with c1:
                            chosen_proj_id = st.selectbox(
                                "Dossier",
                                options=[p["id"] for p in all_projects],
                                format_func=lambda x: next((p["name"] for p in all_projects if p["id"] == x), str(x)),
                                key=f"sel_proj_{r['paper_id']}_{i}"
                            )
                        with c2:
                            chosen_tag = st.selectbox(
                                "Tag",
                                RELEVANCE_TAGS,
                                key=f"sel_tag_{r['paper_id']}_{i}"
                            )
                        with c3:
                            custom_note = st.text_input(
                                "Analyst Note",
                                placeholder="Key finding, parameter estimate, or relevance...",
                                key=f"note_{r['paper_id']}_{i}"
                            )
                        with c4:
                            is_core_chk = st.checkbox("Core Paper", key=f"core_{r['paper_id']}_{i}")
                            if st.button("➕ Save to Dossier", key=f"save_btn_{r['paper_id']}_{i}"):
                                save_conn = get_connection()
                                add_paper_to_project(
                                    save_conn, chosen_proj_id, r["paper_id"],
                                    analyst_notes=custom_note,
                                    relevance_tag=chosen_tag,
                                    is_core=1 if is_core_chk else 0
                                )
                                save_conn.close()
                                st.success(f"Saved to '{next(p['name'] for p in all_projects if p['id'] == chosen_proj_id)}'!")

                # Parameter Mining Expander
                with st.expander(f"📊 Mine Empirical Parameters from Paper #{i}", expanded=False):
                    if not api_key:
                        st.info("Enter a Gemini API Key in the left sidebar to extract structured econometric parameters.")
                    else:
                        if st.button(f"🤖 Extract Parameters with Gemini", key=f"extract_btn_{r['paper_id']}_{i}"):
                            with st.spinner("Extracting parameters..."):
                                try:
                                    saved_p_ids = extract_and_save_paper_parameters(r["paper_id"], api_key=api_key)
                                    if saved_p_ids:
                                        st.success(f"Extracted and saved {len(saved_p_ids)} parameters to the Parameter Database! View in Tab 4.")
                                    else:
                                        st.info("No quantitative parameters found in this paper's text.")
                                except Exception as ex:
                                    st.error(f"Extraction error: {ex}")

            # Export Search Results
            st.markdown("---")
            col_e1, col_e2, _ = st.columns([1, 1, 3])
            with col_e1:
                export_json = json.dumps(results, indent=2, default=str)
                st.download_button(
                    "📥 Export JSON",
                    export_json,
                    file_name=f"search_results_{search_query[:25].replace(' ', '_')}.json",
                    mime="application/json"
                )
            with col_e2:
                csv_rows = ["Rank,Title,Year,Journal,Tier,Citations,Similarity,DOI"]
                for idx, r in enumerate(results, 1):
                    t = (r.get("title") or "").replace('"', "'")
                    src = (r.get("source") or "Unknown")[:30].replace('"', "'")
                    doi = r.get("doi") or ""
                    csv_rows.append(f'{idx},"{t}",{r.get("year", "")},"{src}",{r.get("tier", 4)},{r.get("citations", 0)},{r.get("similarity", 0):.3f},"{doi}"')
                st.download_button(
                    "📥 Export CSV",
                    "\n".join(csv_rows),
                    file_name=f"search_results_{search_query[:25].replace(' ', '_')}.csv",
                    mime="text/csv"
                )


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2: PROJECT DOSSIERS & SAVED WORKSPACES
# ═════════════════════════════════════════════════════════════════════════════

with tab_dossiers:
    conn = get_connection()
    projects = get_all_projects(conn)

    col_title, col_new = st.columns([4, 1])
    with col_title:
        st.markdown("#### 📁 Active Research Dossiers & Curated Collections")
    with col_new:
        with st.popover("➕ New Dossier", use_container_width=True):
            new_p_name = st.text_input("Project Name", placeholder="e.g., Carbon Pricing & Crop Margins")
            new_p_desc = st.text_area("Description", placeholder="Objectives, scope, and target policy briefs...")
            new_p_tags = st.text_input("Tags (comma-separated)", placeholder="carbon-tax, margins, policy, ontario")
            if st.button("Create Dossier", type="primary", use_container_width=True):
                if new_p_name:
                    create_project(conn, new_p_name, new_p_desc, new_p_tags)
                    st.success(f"Created dossier '{new_p_name}'!")
                    st.rerun()

    if not projects:
        st.info("No research project dossiers found. Create your first dossier above!")
    else:
        # Project Selector
        selected_project_id = st.selectbox(
            "Select Active Dossier",
            options=[p["id"] for p in projects],
            format_func=lambda x: next(f"📁 {p['name']} ({p['paper_count']} papers, {p['core_count']} core)" for p in projects if p["id"] == x),
            key="active_dossier_select"
        )

        active_project = next(p for p in projects if p["id"] == selected_project_id)
        project_papers = get_project_papers(conn, selected_project_id)
        project_syntheses = get_project_syntheses(conn, selected_project_id)

        # Project Header Card
        tag_html = "".join(f'<span class="tag-badge">#{t.strip()}</span>' for t in active_project["tags"].split(",") if t.strip()) if active_project.get("tags") else ""
        st.markdown(f"""
        <div class="project-header-box">
            <h3 style="margin:0 0 0.4rem 0; color:#1a3a24;">📁 {active_project['name']}</h3>
            <p style="margin:0 0 0.6rem 0; color:#4a5a4f; font-size:0.92rem;">{active_project['description'] or 'No description provided.'}</p>
            <div>{tag_html}</div>
            <div style="margin-top:0.7rem; font-size:0.82rem; color:#6b7d70;">
                <strong>{len(project_papers)}</strong> saved papers · 
                <strong>{active_project['core_count']}</strong> core references · 
                <strong>{len(project_syntheses)}</strong> saved literature review syntheses · 
                Last updated: {active_project['updated_at'][:16]}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Action Bar: Edit, Export, Delete
        c_act1, c_act2, c_act3, c_act4 = st.columns([1.5, 1.5, 1.5, 3])
        with c_act1:
            with st.popover("✏️ Edit Dossier Details"):
                edit_name = st.text_input("Name", value=active_project["name"])
                edit_desc = st.text_area("Description", value=active_project["description"] or "")
                edit_tags = st.text_input("Tags", value=active_project["tags"] or "")
                if st.button("Save Changes", key="edit_dossier_save_btn"):
                    update_project(conn, selected_project_id, edit_name, edit_desc, edit_tags)
                    st.success("Dossier updated!")
                    st.rerun()

        with c_act2:
            # Export Dossier Markdown Briefing
            md_lines = [
                f"# Research Dossier: {active_project.get('name', 'Dossier')}",
                f"\n**Description**: {active_project.get('description', '')}",
                f"**Tags**: {active_project.get('tags', '')}",
                f"**Export Date**: {active_project.get('updated_at', '')}",
                f"\n## Curated Literature ({len(project_papers)} papers)\n"
            ]
            for idx, p in enumerate(project_papers, 1):
                core_str = " [CORE REFERENCE]" if p.get("is_core") else ""
                source_str = (p.get("source_name") or "Unknown")
                md_lines.append(f"### {idx}. {p.get('title', 'Untitled')}{core_str}")
                md_lines.append(f"* **Year**: {p.get('year', 'N/A')} | **Source**: {source_str} | **Tier**: {p.get('priority_tier', 4)} | **Citations**: {p.get('citation_count', 0)}")
                if p.get("relevance_tag"):
                    md_lines.append(f"* **Relevance Tag**: {p['relevance_tag']}")
                if p.get("analyst_notes"):
                    md_lines.append(f"* **Analyst Notes**: {p['analyst_notes']}")
                if p.get("abstract"):
                    md_lines.append(f"\n> {p['abstract']}\n")
            
            st.download_button(
                "📥 Export Briefing (MD)",
                "\n".join(md_lines),
                file_name=f"dossier_{(active_project.get('name') or 'dossier')[:25].replace(' ', '_')}.md",
                mime="text/markdown"
            )

        with c_act3:
            # Export CSV
            csv_dossier = ["PaperID,Title,Year,Journal,Tier,Citations,RelevanceTag,IsCore,AnalystNotes,DOI"]
            for p in project_papers:
                t = (p.get("title") or "").replace('"', "'")
                n = (p.get("analyst_notes") or "").replace('"', "'")
                src = (p.get("source_name") or "Unknown")[:30].replace('"', "'")
                doi = p.get("doi") or ""
                csv_dossier.append(f'{p.get("paper_id", "")},"{t}",{p.get("year", "")},"{src}",{p.get("priority_tier", 4)},{p.get("citation_count", 0)},"{p.get("relevance_tag", "")}",{p.get("is_core", 0)},"{n}","{doi}"')
            st.download_button(
                "📥 Export Table (CSV)",
                "\n".join(csv_dossier),
                file_name=f"dossier_{(active_project.get('name') or 'dossier')[:25].replace(' ', '_')}.csv",
                mime="text/csv"
            )

        with c_act4:
            if st.button("🗑️ Delete Dossier", key="del_dossier_btn"):
                delete_project(conn, selected_project_id)
                st.warning("Dossier deleted!")
                st.rerun()

        st.markdown("---")

        # Filter Dossier Papers
        if project_papers:
            f_col1, f_col2 = st.columns([2, 3])
            with f_col1:
                tag_filter = st.selectbox(
                    "Filter by Relevance Tag",
                    ["All Tags"] + RELEVANCE_TAGS,
                    key="dossier_tag_filter"
                )
            with f_col2:
                dossier_search = st.text_input("Filter within dossier papers", placeholder="Search title or notes...", key="dossier_kw_filter")

            filtered_papers = project_papers
            if tag_filter != "All Tags":
                filtered_papers = [p for p in filtered_papers if p.get("relevance_tag") == tag_filter]
            if dossier_search:
                q_low = dossier_search.lower()
                filtered_papers = [p for p in filtered_papers if q_low in (p.get("title") or "").lower() or q_low in (p.get("analyst_notes") or "").lower()]

            st.markdown(f"##### 📑 Curated Literature ({len(filtered_papers)} of {len(project_papers)} papers)")

            for idx, p in enumerate(filtered_papers, 1):
                tier_css = TIER_CSS.get(p.get("priority_tier", 4), "tier-4")
                tier_name = TIER_NAMES.get(p.get("priority_tier", 4), "Global")
                core_badge = '<span class="core-badge">★ CORE REFERENCE</span> · ' if p.get("is_core") else ""
                tag_badge = f'<span class="tag-badge">🏷️ {p.get("relevance_tag")}</span>' if p.get("relevance_tag") else ""
                doi_link = f' · <a href="https://doi.org/{p.get("doi")}" target="_blank">DOI ↗</a>' if p.get("doi") else ""
                src_disp = (p.get("source_name") or "Unknown")[:40]

                st.markdown(f"""
                <div class="result-card" style="border-left-color: {'#d97706' if p.get('is_core') else '#2d8a4e'};">
                    <div class="result-title">{idx}. {p.get('title', 'Untitled')}</div>
                    <div class="result-meta">
                        {core_badge}<span class="tier-badge {tier_css}">{tier_name}</span>
                        &nbsp; {p.get('year', 'N/A')} · {src_disp} · {p.get('citation_count', 0):,} citations {doi_link} · {tag_badge}
                    </div>
                    {f'<div class="note-box"><strong>Analyst Note:</strong> {p.get("analyst_notes")}</div>' if p.get("analyst_notes") else ''}
                    <div class="result-abstract">{(p.get('abstract') or 'No abstract text available.')[:300]}...</div>
                </div>
                """, unsafe_allow_html=True)

                # Edit paper notes & tag expander
                with st.expander(f"⚙️ Edit Notes & Tag for Paper #{idx}", expanded=False):
                    ec1, ec2, ec3, ec4 = st.columns([3, 4, 2, 2])
                    with ec1:
                        new_tag = st.selectbox("Relevance Tag", RELEVANCE_TAGS, index=RELEVANCE_TAGS.index(p["relevance_tag"]) if p["relevance_tag"] in RELEVANCE_TAGS else 0, key=f"edit_tag_{p['paper_id']}")
                    with ec2:
                        new_notes = st.text_input("Analyst Notes", value=p["analyst_notes"] or "", key=f"edit_notes_{p['paper_id']}")
                    with ec3:
                        new_core = st.checkbox("Core Paper", value=bool(p["is_core"]), key=f"edit_core_{p['paper_id']}")
                    with ec4:
                        if st.button("Update Paper", key=f"update_p_{p['paper_id']}"):
                            update_project_paper(conn, selected_project_id, p["paper_id"], analyst_notes=new_notes, relevance_tag=new_tag, is_core=new_core)
                            st.success("Updated!")
                            st.rerun()
                        if st.button("Remove from Dossier", key=f"rem_p_{p['paper_id']}"):
                            remove_paper_from_project(conn, selected_project_id, p["paper_id"])
                            st.warning("Removed!")
                            st.rerun()
        else:
            st.info("No papers saved in this dossier yet. Add papers from the **Search & Discover** tab!")

    conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3: LITERATURE REVIEW CANVAS & MEMORY
# ═════════════════════════════════════════════════════════════════════════════

with tab_canvas:
    st.markdown("#### 🧠 Literature Review Canvas & Memory")
    st.caption("Generate, version, and compound literature review syntheses grounded directly in your curated project dossiers.")

    conn = get_connection()
    projects = get_all_projects(conn)

    if not projects:
        st.info("No dossiers available. Please create a project dossier first.")
    else:
        active_p_id = st.selectbox(
            "Select Dossier for Synthesis",
            options=[p["id"] for p in projects],
            format_func=lambda x: next(f"📁 {p['name']} ({p['paper_count']} papers, {p['core_count']} core)" for p in projects if p["id"] == x),
            key="canvas_project_select"
        )

        dossier_papers = get_project_papers(conn, active_p_id)
        dossier_syntheses = get_project_syntheses(conn, active_p_id)
        current_project = next(p for p in projects if p["id"] == active_p_id)

        # ── Section 1: Generate / Update Synthesis ──
        st.markdown("##### 🚀 Synthesize Dossier Literature")
        
        if not api_key:
            st.warning("⚠️ Enter a Gemini API Key in the left sidebar to generate or update literature reviews.")
        else:
            synth_col1, synth_col2 = st.columns([3, 1])
            with synth_col1:
                review_focus = st.text_input(
                    "Synthesis Objective / Research Question",
                    value=f"Empirical findings, methodologies, and Ontario policy implications for {current_project['name']}",
                    key="review_focus_input"
                )
            with synth_col2:
                include_prior = st.checkbox(
                    "Build on Prior Review",
                    value=bool(dossier_syntheses),
                    help="Feeds the previous synthesis version into the AI so it highlights updates and avoids repetitive summaries."
                )

            if st.button("🧠 Generate Structured Literature Review", type="primary", use_container_width=True):
                if not dossier_papers:
                    st.error("Cannot synthesize: No papers saved in this dossier yet!")
                else:
                    with st.spinner("Analyzing papers and generating structured synthesis..."):
                        prior_text = dossier_syntheses[0]["synthesis_markdown"] if (include_prior and dossier_syntheses) else None
                        new_review = generate_gemini_synthesis(
                            query=review_focus,
                            papers_data=dossier_papers,
                            api_key=api_key,
                            prior_synthesis=prior_text
                        )
                        st.session_state["canvas_generated_review"] = new_review
                        st.session_state["canvas_generated_prompt"] = review_focus

            if "canvas_generated_review" in st.session_state:
                st.markdown("---")
                st.markdown("##### 📝 Generated Synthesis")
                st.markdown(f'<div class="synthesis-box">{st.session_state["canvas_generated_review"]}</div>', unsafe_allow_html=True)

                s_save_col1, s_save_col2 = st.columns([3, 1])
                with s_save_col1:
                    custom_synth_title = st.text_input(
                        "Synthesis Title",
                        value=f"Synthesis v{len(dossier_syntheses)+1}: {st.session_state.get('canvas_generated_prompt', 'Literature Review')[:40]}",
                        key="synth_title_input"
                    )
                with s_save_col2:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    if st.button("💾 Save as New Version", type="primary", use_container_width=True):
                        save_project_synthesis(
                            conn, active_p_id,
                            title=custom_synth_title,
                            query_prompt=st.session_state.get("canvas_generated_prompt", ""),
                            synthesis_markdown=st.session_state["canvas_generated_review"],
                            model_used="gemini-2.5-flash"
                        )
                        st.success(f"Saved as Version {len(dossier_syntheses)+1}!")
                        del st.session_state["canvas_generated_review"]
                        st.rerun()

        st.markdown("---")

        # ── Section 2: Saved Version History & Synthesis Memory ──
        st.markdown(f"##### 📚 Versioned Synthesis History ({len(dossier_syntheses)} versions)")

        if not dossier_syntheses:
            st.info("No literature review syntheses saved for this project yet.")
        else:
            for s in dossier_syntheses:
                s_date = (s.get("created_at") or "")[:16]
                p_name_slug = (current_project.get("name") or "project")[:20].replace(' ', '_')
                with st.expander(f"📄 Version {s['version']}: {s['title']} ({s_date}) — Model: {s['model_used']}", expanded=(s['version'] == dossier_syntheses[0]['version'])):
                    st.markdown(f"**Research Question / Prompt**: *{s.get('query_prompt', '')}*")
                    st.markdown(f'<div class="synthesis-box">{s.get("synthesis_markdown", "")}</div>', unsafe_allow_html=True)
                    
                    sc1, sc2 = st.columns([2, 1])
                    with sc1:
                        st.text_area("Raw Markdown", s.get("synthesis_markdown", ""), height=150, key=f"raw_md_{s['id']}")
                    with sc2:
                        st.download_button(
                            f"📥 Download v{s['version']} (MD)",
                            s.get("synthesis_markdown", ""),
                            file_name=f"synthesis_v{s['version']}_{p_name_slug}.md",
                            mime="text/markdown",
                            key=f"dl_synth_{s['id']}"
                        )

    conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# TAB 4: EMPIRICAL PARAMETERS & SIMULATOR CALIBRATION
# ═════════════════════════════════════════════════════════════════════════════

with tab_params:
    st.markdown("#### 📊 Empirical Parameters & Economic Simulator Calibration")
    st.caption("Literature-backed econometric parameters, supply elasticities, tariff pass-through rates, and IO multipliers directly linked to OFA simulation models.")

    conn = get_connection()
    all_params = get_empirical_parameters(conn)

    # ── Metric Cards ────────────────────────────────────────────────────────
    c_m1, c_m2, c_m3, c_m4 = st.columns(4)
    commodities_set = {p["commodity"] for p in all_params}
    types_set = {p["parameter_type"] for p in all_params}

    c_m1.metric("Empirical Parameters", f"{len(all_params):,}")
    c_m2.metric("Commodity Sectors", f"{len(commodities_set):,}")
    c_m3.metric("Parameter Types", f"{len(types_set):,}")
    c_m4.metric("Evidence-Based Baseline", "100% Peer-Reviewed/Grey Lit")

    st.markdown("---")

    # ── Section 1: Direct Simulator Calibration Code Export ─────────────────
    with st.expander("🔮 Direct Simulator Calibration Code & Configurations", expanded=False):
        st.markdown("Generate calibrated Python dictionaries and JSON ready to paste into `8_🔮_Growth_&_Risk_Simulator.py` or the OFA IO Multiplier Engine.")
        sim_configs = export_parameters_for_simulator(conn)

        # Format Python code string
        py_snippet = f"""# ==============================================================================
# OFA GROWTH & RISK SIMULATOR — CALIBRATED EMPIRICAL PARAMETERS
# Generated automatically from Ag Econ Research Intelligence Database
# ==============================================================================

TARIFF_CONFIG = {json.dumps(sim_configs['TARIFF_CONFIG'], indent=4)}

SUPPLY_ELASTICITIES = {json.dumps(sim_configs['SUPPLY_ELASTICITIES'], indent=4)}

IO_MULTIPLIERS = {json.dumps(sim_configs['IO_MULTIPLIERS'], indent=4)}

FINANCIAL_RISK_THRESHOLDS = {json.dumps(sim_configs['FINANCIAL_RISK_THRESHOLDS'], indent=4)}
"""
        st.code(py_snippet, language="python")

        sc_c1, sc_c2, sc_c3 = st.columns([1.5, 1.5, 3])
        with sc_c1:
            st.download_button(
                "📥 Download Python Config (`sim_config.py`)",
                py_snippet,
                file_name="sim_config.py",
                mime="text/x-python"
            )
        with sc_c2:
            st.download_button(
                "📥 Download JSON Config",
                json.dumps(sim_configs, indent=2),
                file_name="simulator_parameters.json",
                mime="application/json"
            )
        with sc_c3:
            # CSV table export
            csv_lines = ["ID,Commodity,ParameterType,PointEstimate,Unit,StatLower,StatUpper,StandardError,TimeHorizon,Geography,SamplePeriod,ModelType,SourcePaper,Notes"]
            for p in all_params:
                t = (p.get("paper_title") or "").replace('"', "'")
                n = (p.get("notes") or "").replace('"', "'")
                csv_lines.append(
                    f'{p["id"]},"{p["commodity"]}","{p["parameter_type"]}",{p["point_estimate"]},"{p.get("unit","")}",{p.get("stat_lower","")},{p.get("stat_upper","")},{p.get("standard_error","")},"{p.get("time_horizon","")}","{p.get("geography","")}","{p.get("sample_period","")}","{p.get("model_type","")}","{t}","{n}"'
                )
            st.download_button(
                "📥 Download All Parameters (CSV)",
                "\n".join(csv_lines),
                file_name="empirical_parameters.csv",
                mime="text/csv"
            )

    st.markdown("---")

    # ── Section 2: Interactive Comparison Matrix ────────────────────────────
    st.markdown("##### 🔍 Parameter Comparison Matrix")

    f_col1, f_col2, f_col3 = st.columns([2, 2, 3])
    with f_col1:
        selected_commodity = st.selectbox(
            "Filter by Commodity",
            ["All"] + sorted(list(commodities_set)),
            key="param_filter_commodity"
        )
    with f_col2:
        selected_ptype = st.selectbox(
            "Filter by Parameter Type",
            ["All"] + sorted(list(types_set)),
            key="param_filter_ptype"
        )
    with f_col3:
        param_kw = st.text_input("Search notes or model type", placeholder="e.g. basis, OLS, quota, translog...", key="param_kw_filter")

    filtered_params = get_empirical_parameters(
        conn,
        commodity=selected_commodity if selected_commodity != "All" else None,
        parameter_type=selected_ptype if selected_ptype != "All" else None
    )

    if param_kw:
        kw_low = param_kw.lower()
        filtered_params = [
            p for p in filtered_params
            if kw_low in (p.get("notes") or "").lower()
            or kw_low in (p.get("model_type") or "").lower()
            or kw_low in (p.get("commodity") or "").lower()
            or kw_low in (p.get("paper_title") or "").lower()
        ]

    st.markdown(f"**Showing {len(filtered_params)} matching parameters:**")

    if not filtered_params:
        st.info("No parameters match the selected filters.")
    else:
        for p in filtered_params:
            # Format range and uncertainty strings
            range_str = f"[{p['stat_lower']:.2f} to {p['stat_upper']:.2f}]" if (p.get("stat_lower") is not None and p.get("stat_upper") is not None) else "N/A"
            se_str = f"± {p['standard_error']:.3f}" if p.get("standard_error") is not None else ""
            paper_citation = f'📄 *Source:* {p["paper_title"]} ({p.get("paper_year", "")})' if p.get("paper_title") else '📄 *Source:* OFA Empirical Calibration Baseline'
            doi_link = f' · <a href="https://doi.org/{p["paper_doi"]}" target="_blank">DOI ↗</a>' if p.get("paper_doi") else ""

            st.markdown(f"""
            <div class="result-card" style="border-left-color: #2563eb;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <div>
                        <span class="tag-badge" style="background:#dbeafe; color:#1e40af;">🌾 {p['commodity']}</span>
                        <span class="tag-badge" style="background:#fef3c7; color:#92400e;">📐 {p['parameter_type']}</span>
                        <span class="tag-badge" style="background:#f3e8ff; color:#6b21a8;">⏱️ {p.get('time_horizon', 'N/A')}</span>
                        <span class="tag-badge" style="background:#e0f2fe; color:#0369a1;">📍 {p.get('geography', 'Canada')}</span>
                    </div>
                    <div style="text-align:right;">
                        <span style="font-size:1.4rem; font-weight:700; color:#1e40af;">{p['point_estimate']:.2f}</span>
                        <span style="font-size:0.78rem; color:#64748b;">{p.get('unit', '')}</span>
                    </div>
                </div>
                <div style="margin-top:0.5rem; font-size:0.84rem; color:#475569;">
                    <strong>Range / 95% CI:</strong> {range_str} &nbsp;|&nbsp; <strong>SE:</strong> {se_str or 'Unspecified'} &nbsp;|&nbsp; <strong>Econometric Model:</strong> {p.get('model_type', 'Econometric')} &nbsp;|&nbsp; <strong>Sample:</strong> {p.get('sample_period', 'N/A')}
                </div>
                {f'<div class="note-box" style="background:#f8fafc; border-left-color:#3b82f6; color:#1e293b;"><strong>Empirical Notes:</strong> {p["notes"]}</div>' if p.get("notes") else ''}
                <div style="margin-top:0.4rem; font-size:0.80rem; color:#64748b;">
                    {paper_citation}{doi_link}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Edit / Delete Expander
            with st.expander(f"⚙️ Edit / Manage Parameter #{p['id']} ({p['commodity']} - {p['parameter_type']})", expanded=False):
                ec1, ec2, ec3 = st.columns([2, 2, 2])
                with ec1:
                    new_val = st.number_input("Point Estimate", value=float(p["point_estimate"]), format="%.4f", key=f"edit_pe_{p['id']}")
                    new_comm = st.text_input("Commodity", value=p["commodity"], key=f"edit_c_{p['id']}")
                with ec2:
                    new_low = st.number_input("Lower Bound (CI)", value=float(p["stat_lower"]) if p.get("stat_lower") is not None else 0.0, format="%.4f", key=f"edit_low_{p['id']}")
                    new_high = st.number_input("Upper Bound (CI)", value=float(p["stat_upper"]) if p.get("stat_upper") is not None else 0.0, format="%.4f", key=f"edit_high_{p['id']}")
                with ec3:
                    new_model = st.text_input("Model Type", value=p.get("model_type", ""), key=f"edit_m_{p['id']}")
                    new_notes = st.text_input("Notes", value=p.get("notes", ""), key=f"edit_n_{p['id']}")

                b_upd, b_del, _ = st.columns([1, 1, 3])
                with b_upd:
                    if st.button("Save Changes", key=f"save_param_btn_{p['id']}"):
                        update_empirical_parameter(
                            conn, p["id"],
                            commodity=new_comm,
                            point_estimate=new_val,
                            stat_lower=new_low if new_low != 0.0 else None,
                            stat_upper=new_high if new_high != 0.0 else None,
                            model_type=new_model,
                            notes=new_notes
                        )
                        st.success("Parameter updated!")
                        st.rerun()
                with b_del:
                    if st.button("🗑️ Delete", key=f"del_param_btn_{p['id']}"):
                        delete_empirical_parameter(conn, p["id"])
                        st.warning("Deleted parameter!")
                        st.rerun()

    st.markdown("---")

    # ── Section 3: Add & Mine Parameters ────────────────────────────────────
    st.markdown("##### ➕ Ingest & Mine Empirical Parameters")

    subtab_manual, subtab_ai = st.tabs(["✍️ Add Parameter Manually", "🤖 Mine with Gemini AI"])

    with subtab_manual:
        with st.form("manual_param_form"):
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                man_comm = st.text_input("Commodity / Sector", placeholder="e.g. Canola, Dairy, NAICS 111")
                man_ptype = st.selectbox("Parameter Type", [
                    "Tariff Pass-Through",
                    "Supply Elasticity (Short-Run)",
                    "Supply Elasticity (Long-Run)",
                    "Demand Elasticity",
                    "IO Output Multiplier",
                    "IO Value-Added Multiplier",
                    "IO Employment Multiplier",
                    "Price Transmission Elasticity",
                    "Debt Service Coverage Ratio (DSCR) Distress Threshold",
                    "Debt-to-Asset Stress Threshold",
                    "Exchange Rate Buffer (FX Offset)",
                    "Trade Diversion Annual Decay Rate",
                    "Other"
                ])
                man_pe = st.number_input("Point Estimate", value=0.50, format="%.4f")
            with col_f2:
                man_unit = st.text_input("Unit", value="elasticity (%ΔQ / %ΔP)")
                man_low = st.number_input("Lower Bound (optional)", value=0.0, format="%.4f")
                man_high = st.number_input("Upper Bound (optional)", value=0.0, format="%.4f")
            with col_f3:
                man_horizon = st.selectbox("Time Horizon", ["Short-run (1 yr)", "Medium-run (3 yr)", "Long-run (4+ yr)", "Annual", "Cross-sectional"])
                man_geo = st.text_input("Geography", value="Ontario / Canada")
                man_model = st.text_input("Econometric Model Type", value="Econometric / OLS")

            man_notes = st.text_area("Empirical Context / Notes", placeholder="Identification strategy, dataset, key qualifications...")

            if st.form_submit_button("Add Parameter to Database", type="primary", use_container_width=True):
                if man_comm:
                    add_empirical_parameter(
                        conn,
                        commodity=man_comm,
                        parameter_type=man_ptype,
                        point_estimate=man_pe,
                        unit=man_unit,
                        stat_lower=man_low if man_low != 0.0 else None,
                        stat_upper=man_high if man_high != 0.0 else None,
                        time_horizon=man_horizon,
                        geography=man_geo,
                        model_type=man_model,
                        notes=man_notes
                    )
                    st.success(f"Added parameter for {man_comm} ({man_ptype}: {man_pe})!")
                    st.rerun()

    with subtab_ai:
        if not api_key:
            st.warning("⚠️ Enter a Gemini API Key in the left sidebar to use the AI Parameter Miner.")
        else:
            st.markdown("Paste an excerpt or abstract from an agricultural economics paper to automatically extract structured parameters.")
            ai_input_title = st.text_input("Paper Title", placeholder="e.g. Econometric Analysis of Canadian Wheat Export Price Transmission", key="ai_param_title_input")
            ai_input_text = st.text_area("Paper Abstract / Methodology / Results Text", height=200, placeholder="Paste paper text containing elasticities, multipliers, or pass-through estimates...", key="ai_param_text_input")

            if st.button("🤖 Run Parameter Extraction with Gemini", type="primary", use_container_width=True, key="run_ai_param_miner_btn"):
                if not ai_input_text:
                    st.error("Please paste paper text to extract parameters.")
                else:
                    with st.spinner("Extracting parameters with Gemini..."):
                        try:
                            extracted_results = extract_parameters_from_text(ai_input_text, title=ai_input_title, api_key=api_key)
                            st.session_state["temp_extracted_params"] = extracted_results
                            st.success(f"Extracted {len(extracted_results)} parameters!")
                        except Exception as e:
                            st.error(f"Extraction failed: {e}")

            if "temp_extracted_params" in st.session_state and st.session_state["temp_extracted_params"]:
                st.markdown("##### 📋 Extracted Parameters Preview")
                for idx, ep in enumerate(st.session_state["temp_extracted_params"], 1):
                    st.json(ep)

                if st.button("💾 Save All Extracted Parameters to Database", type="primary", use_container_width=True, key="save_all_extracted_btn"):
                    for ep in st.session_state["temp_extracted_params"]:
                        add_empirical_parameter(
                            conn,
                            commodity=ep.get("commodity", "General Ag"),
                            parameter_type=ep.get("parameter_type", "Elasticity"),
                            point_estimate=float(ep.get("point_estimate", 0.0)),
                            unit=ep.get("unit", "elasticity"),
                            stat_lower=float(ep["stat_lower"]) if ep.get("stat_lower") is not None else None,
                            stat_upper=float(ep["stat_upper"]) if ep.get("stat_upper") is not None else None,
                            standard_error=float(ep["standard_error"]) if ep.get("standard_error") is not None else None,
                            time_horizon=ep.get("time_horizon", "Short-run (1 yr)"),
                            geography=ep.get("geography", "Canada"),
                            sample_period=ep.get("sample_period"),
                            model_type=ep.get("model_type", "Econometric"),
                            notes=ep.get("notes", "")
                        )
                    st.success(f"Saved {len(st.session_state['temp_extracted_params'])} parameters to database!")
                    del st.session_state["temp_extracted_params"]
                    st.rerun()

    conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# TAB 5: POLICY BRIEFS & BOARD MEMOS
# ═════════════════════════════════════════════════════════════════════════════

with tab_briefs:
    st.markdown("#### 🏛️ OFA Policy Brief & Board Memo Generator")
    st.caption("Synthesize curated research literature, empirical parameters, and economic simulation models into publication-ready policy submissions and executive memos.")

    conn = get_connection()
    projects = get_all_projects(conn)

    if not projects:
        st.info("No research dossiers found. Create a dossier in the **Project Dossiers** tab first.")
    else:
        # Project Selector
        col_psel1, col_psel2 = st.columns([3, 2])
        with col_psel1:
            active_b_pid = st.selectbox(
                "Select Research Dossier",
                options=[p["id"] for p in projects],
                format_func=lambda x: next(f"📁 {p['name']} ({p['paper_count']} papers, {p['core_count']} core)" for p in projects if p["id"] == x),
                key="brief_project_select"
            )
        
        current_b_proj = next(p for p in projects if p["id"] == active_b_pid)
        dossier_papers = get_project_papers(conn, active_b_pid)
        dossier_params = get_empirical_parameters(conn, project_id=active_b_pid)
        dossier_briefs = get_project_briefs(conn, active_b_pid)

        with col_psel2:
            st.markdown(f"""
            <div style="background:#f8faf9; border:1px solid #d1ded6; border-radius:8px; padding:0.6rem 0.9rem; margin-top:0.3rem; font-size:0.84rem;">
                <strong>Dossier Assets:</strong> {len(dossier_papers)} papers · {current_b_proj['core_count']} core · {len(dossier_params)} calibrated parameters · {len(dossier_briefs)} saved briefs
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")

        # ── Section 1: Brief Generator Configuration ──
        st.markdown("##### 🚀 Draft New Policy Brief or Memo")

        if not api_key:
            st.warning("⚠️ Enter a Gemini API Key in the left sidebar to generate policy briefs.")
        else:
            bc1, bc2 = st.columns([2, 3])
            with bc1:
                chosen_template = st.selectbox(
                    "Brief Template",
                    list(BRIEF_TEMPLATES.keys()),
                    key="chosen_brief_template"
                )
                default_aud = BRIEF_TEMPLATES[chosen_template]["audience"]
                custom_aud = st.text_input("Target Audience", value=default_aud, key="custom_brief_audience")

            with bc2:
                template_desc = BRIEF_TEMPLATES[chosen_template]["description"]
                st.info(f"💡 **Template Purpose:** {template_desc}")
                custom_focus_text = st.text_area(
                    "Specific Issues / Angles to Emphasize (Optional)",
                    placeholder="e.g. Highlight Ontario farm cash flow impacts, input cost pressures, and recommend specific transitional compensation mechanisms...",
                    height=80,
                    key="custom_brief_focus"
                )

            if st.button("🏛️ Generate Policy Document with Gemini", type="primary", use_container_width=True, key="gen_brief_btn"):
                if not dossier_papers:
                    st.error("Cannot generate brief: No research papers have been added to this dossier yet.")
                else:
                    with st.spinner(f"Compiling literature & generating {chosen_template}..."):
                        try:
                            generated_brief_md = generate_policy_brief(
                                project_id=active_b_pid,
                                template_type=chosen_template,
                                target_audience=custom_aud,
                                custom_focus=custom_focus_text,
                                api_key=api_key
                            )
                            st.session_state["active_generated_brief"] = generated_brief_md
                            st.session_state["active_brief_template"] = chosen_template
                            st.session_state["active_brief_aud"] = custom_aud
                        except Exception as err:
                            st.error(f"Generation failed: {err}")

            # ── Display Generated Brief ──
            if "active_generated_brief" in st.session_state and st.session_state["active_generated_brief"]:
                brief_text = st.session_state["active_generated_brief"]
                brief_tmpl = st.session_state.get("active_brief_template", chosen_template)
                brief_aud = st.session_state.get("active_brief_aud", custom_aud)

                st.markdown("---")
                st.markdown("##### 📄 Generated Document Preview")

                # Action bar for downloads
                d_c1, d_c2, d_c3, d_c4 = st.columns([2, 2, 2, 3])
                proj_slug = current_b_proj["name"][:20].replace(" ", "_")

                with d_c1:
                    # Word Document Export
                    docx_stream = export_brief_to_docx(
                        brief_text,
                        title=f"OFA Policy Brief: {current_b_proj['name']}",
                        project_name=current_b_proj["name"]
                    )
                    st.download_button(
                        "📥 Download Word (.docx)",
                        docx_stream,
                        file_name=f"OFA_Policy_Brief_{proj_slug}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="dl_preview_docx"
                    )

                with d_c2:
                    # Markdown Export
                    st.download_button(
                        "📥 Download Markdown (.md)",
                        brief_text,
                        file_name=f"OFA_Policy_Brief_{proj_slug}.md",
                        mime="text/markdown",
                        key="dl_preview_md"
                    )

                with d_c3:
                    # HTML Printable Export
                    html_doc = export_brief_to_html(brief_text, title=f"OFA Policy Brief: {current_b_proj['name']}")
                    st.download_button(
                        "📥 Download HTML Report",
                        html_doc,
                        file_name=f"OFA_Policy_Brief_{proj_slug}.html",
                        mime="text/html",
                        key="dl_preview_html"
                    )

                # Render Brief in styling box
                st.markdown(f'<div class="synthesis-box" style="background:#ffffff; border-left:4px solid #1a5632;">{brief_text}</div>', unsafe_allow_html=True)

                # Save to project archive
                st.markdown("##### 💾 Save to Project Brief Archive")
                sc1, sc2 = st.columns([3, 1])
                with sc1:
                    save_brief_title = st.text_input(
                        "Brief Title",
                        value=f"{brief_tmpl}: {current_b_proj['name']}",
                        key="save_brief_title_input"
                    )
                with sc2:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    if st.button("Save to Archive", type="primary", use_container_width=True, key="save_brief_btn"):
                        save_policy_brief(
                            conn,
                            project_id=active_b_pid,
                            title=save_brief_title,
                            template_type=brief_tmpl,
                            target_audience=brief_aud,
                            brief_markdown=brief_text,
                            model_used="gemini-2.5-flash"
                        )
                        st.success("Policy brief saved to archive!")
                        del st.session_state["active_generated_brief"]
                        st.rerun()

        st.markdown("---")

        # ── Section 2: Saved Policy Briefs Archive ──
        st.markdown(f"##### 📚 Saved Policy Briefs & Decision Memos ({len(dossier_briefs)} documents)")

        if not dossier_briefs:
            st.info("No policy briefs saved for this project yet. Generate your first brief above!")
        else:
            for b in dossier_briefs:
                b_date = (b.get("created_at") or "")[:16]
                p_slug = current_b_proj["name"][:20].replace(" ", "_")
                with st.expander(f"📄 Version {b['version']}: {b['title']} ({b_date}) — [{b['template_type']}]", expanded=(b['version'] == dossier_briefs[0]['version'])):
                    st.markdown(f"**Target Audience**: *{b.get('target_audience', 'Not specified')}* | **Model**: {b.get('model_used', 'gemini-2.5-flash')}")
                    st.markdown(f'<div class="synthesis-box" style="background:#ffffff; border-left:4px solid #1a5632;">{b["brief_markdown"]}</div>', unsafe_allow_html=True)

                    bc_d1, bc_d2, bc_d3, bc_del = st.columns([1.5, 1.5, 1.5, 2])
                    with bc_d1:
                        doc_stream = export_brief_to_docx(b["brief_markdown"], title=b["title"], project_name=current_b_proj["name"])
                        st.download_button(
                            "📥 Word (.docx)",
                            doc_stream,
                            file_name=f"OFA_{b['template_type'][:10].replace(' ','_')}_v{b['version']}_{p_slug}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"dl_saved_docx_{b['id']}"
                        )
                    with bc_d2:
                        st.download_button(
                            "📥 Markdown (.md)",
                            b["brief_markdown"],
                            file_name=f"OFA_{b['template_type'][:10].replace(' ','_')}_v{b['version']}_{p_slug}.md",
                            mime="text/markdown",
                            key=f"dl_saved_md_{b['id']}"
                        )
                    with bc_d3:
                        html_out = export_brief_to_html(b["brief_markdown"], title=b["title"])
                        st.download_button(
                            "📥 HTML Report",
                            html_out,
                            file_name=f"OFA_{b['template_type'][:10].replace(' ','_')}_v{b['version']}_{p_slug}.html",
                            mime="text/html",
                            key=f"dl_saved_html_{b['id']}"
                        )
                    with bc_del:
                        if st.button("🗑️ Delete Brief", key=f"del_brief_{b['id']}"):
                            delete_policy_brief(conn, b["id"])
                            st.warning("Brief deleted!")
                            st.rerun()

    conn.close()



