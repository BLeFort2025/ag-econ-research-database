"""
Embedding pipeline for the Ag Econ Research Database.
Embeds paper abstracts using sentence-transformers and stores vectors in ChromaDB
for semantic search capabilities.
"""
import os
import sys
import time
from db import get_connection, init_db
from config import BASE_DIR

CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")
MODEL_NAME = "all-MiniLM-L6-v2"  # Fast, good quality, ~80MB model
BATCH_SIZE = 256  # Papers per embedding batch


def get_chroma_collection():
    """Get or create the ChromaDB collection for paper embeddings."""
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(
        name="paper_abstracts",
        metadata={"hnsw:space": "cosine"},
    )
    return client, collection


def build_embeddings(limit=None, force_rebuild=False, model=None, collection=None):
    """
    Embed all paper abstracts that have text content.
    Skips papers already embedded unless force_rebuild=True.
    """
    from sentence_transformers import SentenceTransformer

    print("=" * 70)
    print("  EMBEDDING PIPELINE")
    print("=" * 70)

    # Load model
    if model is None:
        print(f"\n[MODEL] Loading {MODEL_NAME}...")
        model = SentenceTransformer(MODEL_NAME)
        print(f"[MODEL] Ready ({MODEL_NAME})")
    else:
        print(f"\n[MODEL] Using pre-loaded {MODEL_NAME}")

    # Connect to ChromaDB
    if collection is None:
        _, collection = get_chroma_collection()

    if force_rebuild:
        import chromadb
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        client.delete_collection("paper_abstracts")
        _, collection = get_chroma_collection()
        existing_ids = set()
        print("[CHROMA] Collection rebuilt from scratch")
    else:
        # Paged ID retrieval to handle 89k+ vectors without SQLite variable limits
        existing_ids = set()
        col_total = collection.count()
        chunk_sz = 5000
        offset = 0
        while offset < col_total:
            batch = collection.get(limit=chunk_sz, offset=offset)
            if not batch or not batch["ids"]:
                break
            existing_ids.update(batch["ids"])
            offset += len(batch["ids"])
        print(f"[CHROMA] {len(existing_ids)} papers already embedded")

    # Fetch papers with abstracts or full text
    conn = get_connection()
    query = """
        SELECT id, openalex_id, title, abstract, full_text, year, source_name,
               priority_tier, citation_count, doi, is_open_access
        FROM papers
        WHERE (abstract IS NOT NULL AND abstract != '')
           OR (full_text IS NOT NULL AND full_text != '')
    """
    if limit:
        query += f" ORDER BY priority_tier ASC, citation_count DESC LIMIT {int(limit)}"
    else:
        query += " ORDER BY priority_tier ASC, citation_count DESC"

    papers = conn.execute(query).fetchall()
    conn.close()

    # Filter out already-embedded papers
    papers_to_embed = [
        p for p in papers if str(p["id"]) not in existing_ids
    ]

    total = len(papers_to_embed)
    full_text_count = sum(1 for p in papers_to_embed if p["full_text"])
    print(f"[QUEUE] {total} papers to embed ({len(papers) - total} already done)")
    print(f"[QUEUE] {full_text_count} with full text, {total - full_text_count} abstract-only\n")

    if total == 0:
        print("[DONE] All papers already embedded!")
        return 0

    # Process in batches
    embedded = 0
    start_time = time.time()

    for batch_start in range(0, total, BATCH_SIZE):
        batch = papers_to_embed[batch_start:batch_start + BATCH_SIZE]

        # Prepare texts — use full text when available, fall back to abstract
        # MiniLM has a 256 token window, so we front-load the most relevant content
        texts = []
        ids = []
        metadatas = []

        for paper in batch:
            title_str = paper["title"] or ""
            if paper["full_text"]:
                # Use title + first 2000 chars of full text for richer embeddings
                body = paper["full_text"][:2000]
            else:
                body = paper["abstract"] or ""
            text = f"{title_str}. {body}".strip()
            texts.append(text)
            ids.append(str(paper["id"]))
            metadatas.append({
                "title": title_str[:500],
                "year": paper["year"] or 0,
                "source": paper["source_name"] or "Unknown",
                "tier": paper["priority_tier"] or 4,
                "citations": paper["citation_count"] or 0,
                "doi": paper["doi"] or "",
                "is_open_access": paper["is_open_access"] or 0,
                "has_full_text": 1 if paper["full_text"] else 0,
            })

        # Embed batch
        embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)

        # Store in ChromaDB
        collection.add(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metadatas,
        )

        embedded += len(batch)
        elapsed = time.time() - start_time
        rate = embedded / elapsed if elapsed > 0 else 0
        eta = (total - embedded) / rate if rate > 0 else 0

        print(
            f"  Batch {batch_start // BATCH_SIZE + 1}: "
            f"Embedded {embedded:,}/{total:,} "
            f"({embedded / total * 100:.0f}%) | "
            f"{rate:.0f} papers/sec | "
            f"ETA: {eta:.0f}s"
        )

    elapsed = time.time() - start_time
    print(f"\n[DONE] Embedded {embedded:,} papers in {elapsed:.1f}s")
    print(f"[CHROMA] Total vectors: {collection.count():,}")
    return embedded


def search(query_text, n_results=20, tier_filter=None, year_min=None, year_max=None, model=None, collection=None):
    """
    Robust semantic search over paper abstracts.
    Performs pure vector similarity search and applies tier/year filters smoothly.
    """
    if model is None:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(MODEL_NAME)
    if collection is None:
        _, collection = get_chroma_collection()

    # Embed query
    query_embedding = model.encode([query_text], convert_to_numpy=True).tolist()

    # Retrieve candidate vectors (buffer candidates if filters applied)
    has_filter = (tier_filter is not None) or (year_min is not None) or (year_max is not None)
    fetch_k = min(max(n_results * 5, 100), collection.count()) if has_filter else n_results

    try:
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=fetch_k,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        _, fresh_collection = get_chroma_collection()
        results = fresh_collection.query(
            query_embeddings=query_embedding,
            n_results=fetch_k,
            include=["documents", "metadatas", "distances"],
        )

    # Format & filter results
    formatted = []
    if results and results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i] or {}
            distance = results["distances"][0][i]
            similarity = 1.0 - distance

            p_tier = meta.get("tier", 4)
            p_year = meta.get("year", 0)

            # Apply tier filter
            if tier_filter is not None and p_tier != tier_filter:
                continue

            # Apply year filter
            if year_min is not None and p_year < year_min:
                continue
            if year_max is not None and p_year > year_max:
                continue

            formatted.append({
                "paper_id": int(doc_id),
                "title": meta.get("title", ""),
                "year": p_year,
                "source": meta.get("source", ""),
                "tier": p_tier,
                "citations": meta.get("citations", 0),
                "doi": meta.get("doi", ""),
                "is_open_access": meta.get("is_open_access", 0),
                "similarity": round(similarity, 4),
                "abstract_snippet": (results["documents"][0][i] or "")[:300],
            })

            if len(formatted) >= n_results:
                break

    return formatted


if __name__ == "__main__":
    init_db()
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        query = " ".join(sys.argv[2:])
        print(f"\nSearching for: '{query}'\n")
        results = search(query)
        for i, r in enumerate(results, 1):
            print(f"{i:2d}. [{r['similarity']:.2f}] ({r['year']}) {r['title'][:80]}")
            print(f"    Journal: {r['source'][:50]} | Citations: {r['citations']} | Tier: {r['tier']}")
            print()
    else:
        build_embeddings()
