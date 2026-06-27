"""
rag/retriever.py
----------------
Phase 7 — RAG Retriever

Searches Pinecone for relevant document chunks given a query.

Usage:
    from rag.retriever import retrieve

    results = retrieve("What is the global streaming revenue growth?")
    for r in results:
        print(r["text"])
        print(r["source"])
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from openai import OpenAI
from pinecone import Pinecone

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------

INDEX_NAME      = "doc-intelligence"
NAMESPACE       = "chinook-music"
EMBEDDING_MODEL = "text-embedding-3-small"
TOP_K           = 5       # number of chunks to retrieve
MIN_SCORE       = 0.3     # minimum similarity score threshold


# ------------------------------------------------------------------
# Clients (lazy initialized)
# ------------------------------------------------------------------

_openai_client = None
_pinecone_index = None


def _get_clients():
    global _openai_client, _pinecone_index

    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    if _pinecone_index is None:
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        _pinecone_index = pc.Index(INDEX_NAME)

    return _openai_client, _pinecone_index


# ------------------------------------------------------------------
# Core retrieval function
# ------------------------------------------------------------------

def retrieve(
    query: str,
    top_k: int = TOP_K,
    min_score: float = MIN_SCORE,
    filter_source: Optional[str] = None,
    filter_type: Optional[str] = None,
) -> list[dict]:
    """
    Retrieves the most relevant document chunks for a query.

    Args:
        query:         Natural language question
        top_k:         Number of results to return
        min_score:     Minimum cosine similarity threshold (0-1)
        filter_source: Filter by document filename (optional)
        filter_type:   Filter by document type: 'industry_report' | 'financial_report'

    Returns:
        List of dicts with keys:
            - text:      chunk content
            - source:    filename
            - title:     document title
            - page:      page number
            - score:     similarity score
            - publisher: IFPI, Spotify, Luminate
            - year:      publication year
    """
    if not query or not query.strip():
        return []

    openai_client, index = _get_clients()

    # Embed the query
    try:
        response = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=query.strip(),
        )
        query_vector = response.data[0].embedding
    except Exception as e:
        print(f"[Retriever] Embedding error: {e}")
        return []

    # Build optional metadata filter
    pinecone_filter = {}
    if filter_source:
        pinecone_filter["source"] = {"$eq": filter_source}
    if filter_type:
        pinecone_filter["type"] = {"$eq": filter_type}

    # Query Pinecone
    try:
        query_kwargs = {
            "vector":    query_vector,
            "top_k":     top_k,
            "namespace": NAMESPACE,
            "include_metadata": True,
        }
        if pinecone_filter:
            query_kwargs["filter"] = pinecone_filter

        results = index.query(**query_kwargs)

    except Exception as e:
        print(f"[Retriever] Pinecone query error: {e}")
        return []

    # Parse and filter results
    chunks = []
    for match in results.matches:
        if match.score < min_score:
            continue

        meta = match.metadata or {}
        chunks.append({
            "text":      meta.get("text", ""),
            "source":    meta.get("source", "unknown"),
            "title":     meta.get("title", "Unknown Document"),
            "page":      meta.get("page", 0),
            "score":     round(match.score, 4),
            "publisher": meta.get("publisher", "Unknown"),
            "year":      meta.get("year", 0),
            "type":      meta.get("type", "document"),
        })

    return chunks


def retrieve_with_context(query: str, top_k: int = TOP_K) -> dict:
    """
    Retrieves chunks and formats them as a context string for the LLM.

    Returns:
        {
            "context":  formatted string ready to inject into LLM prompt,
            "chunks":   raw list of chunk dicts,
            "sources":  deduplicated list of source documents cited
        }
    """
    chunks = retrieve(query, top_k=top_k)

    if not chunks:
        return {
            "context": "No relevant documents found.",
            "chunks": [],
            "sources": [],
        }

    # Format context string
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"[Source {i}: {chunk['title']} (p.{chunk['page']}, score={chunk['score']})]"
            f"\n{chunk['text']}"
        )

    context = "\n\n".join(context_parts)

    # Deduplicate sources
    seen = set()
    sources = []
    for chunk in chunks:
        key = chunk["source"]
        if key not in seen:
            seen.add(key)
            sources.append({
                "title":     chunk["title"],
                "source":    chunk["source"],
                "publisher": chunk["publisher"],
                "year":      chunk["year"],
            })

    return {
        "context": context,
        "chunks":  chunks,
        "sources": sources,
    }


# ------------------------------------------------------------------
# Quick test
# ------------------------------------------------------------------

if __name__ == "__main__":
    test_queries = [
        "What is the global recorded music revenue growth rate?",
        "Which music genre has the highest streaming revenue?",
        "How many paid streaming subscribers are there worldwide?",
        "What is Spotify's monthly active user count?",
        "Which region is growing fastest in music revenue?",
    ]

    print("=" * 60)
    print("RAG RETRIEVER TEST")
    print("=" * 60)

    for query in test_queries:
        print(f"\nQuery: {query}")
        print("-" * 40)
        result = retrieve_with_context(query, top_k=3)

        for chunk in result["chunks"]:
            print(f"  [{chunk['score']:.3f}] {chunk['title']} (p.{chunk['page']})")
            print(f"  {chunk['text'][:150]}...")
            print()

        print(f"Sources: {[s['title'] for s in result['sources']]}")