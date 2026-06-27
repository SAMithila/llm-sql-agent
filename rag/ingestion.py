"""
rag/ingestion.py
----------------
Phase 7 — RAG Ingestion Pipeline

Ingests PDF documents into Pinecone for the Agentic RAG system.

Flow:
    PDF file → extract text → chunk → embed (OpenAI) → upsert (Pinecone)

Documents indexed:
    - GMR2025_SOTI.pdf        : IFPI Global Music Report 2025
    - GMR2026_SOTI.pdf        : IFPI Global Music Report 2026
    - Spotify-20-F-Filing.pdf : Spotify Annual Report
    - 2025-Year-End-Music-Report-1.2026.pdf : Luminate Year-End Report

Usage:
    python -m rag.ingestion                    # ingest all documents
    python -m rag.ingestion --file GMR2026_SOTI.pdf  # ingest one file
    python -m rag.ingestion --reset            # delete index and re-ingest all
"""

import os
import sys
import argparse
import hashlib
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from pypdf import PdfReader
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------

DOCUMENTS_DIR   = Path(__file__).parent.parent / "documents"
INDEX_NAME      = "doc-intelligence"          # reuse existing index
EMBEDDING_MODEL = "text-embedding-3-small"    # 1536 dims, cheap + fast
CHUNK_SIZE      = 800                         # characters per chunk
CHUNK_OVERLAP   = 150                         # overlap between chunks
BATCH_SIZE      = 100                         # vectors per upsert batch
NAMESPACE       = "chinook-music"             # isolate from other projects

# Document metadata — maps filename to readable source info
DOCUMENT_METADATA = {
    "GMR2025_SOTI.pdf": {
        "title": "IFPI Global Music Report 2025",
        "type": "industry_report",
        "year": 2025,
        "source": "IFPI",
    },
    "GMR2026_SOTI.pdf": {
        "title": "IFPI Global Music Report 2026",
        "type": "industry_report",
        "year": 2026,
        "source": "IFPI",
    },
    "Spotify-20-F-Filing.pdf": {
        "title": "Spotify Annual Report 20-F",
        "type": "financial_report",
        "year": 2024,
        "source": "Spotify",
    },
    "2025-Year-End-Music-Report-1.2026.pdf": {
        "title": "Luminate 2025 Year-End Music Report",
        "type": "industry_report",
        "year": 2025,
        "source": "Luminate",
    },
}


# ------------------------------------------------------------------
# PDF text extraction
# ------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: Path) -> list[dict]:
    """
    Extracts text from each page of a PDF.

    Returns list of dicts:
        [{"page": 1, "text": "..."}, ...]
    """
    pages = []
    try:
        reader = PdfReader(str(pdf_path))
        print(f"  Pages: {len(reader.pages)}")
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                pages.append({
                    "page": i + 1,
                    "text": text.strip(),
                })
        print(f"  Extracted text from {len(pages)} pages")
    except Exception as e:
        print(f"  ERROR extracting {pdf_path.name}: {e}")
    return pages


# ------------------------------------------------------------------
# Text chunking
# ------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Splits text into overlapping chunks.

    Uses sentence-aware splitting — tries to break at sentence boundaries
    rather than mid-sentence for better semantic coherence.
    """
    # Split into sentences first
    sentences = []
    current = ""
    for char in text:
        current += char
        if char in ".!?\n" and len(current) > 50:
            sentences.append(current.strip())
            current = ""
    if current.strip():
        sentences.append(current.strip())

    # Build chunks by accumulating sentences
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= chunk_size:
            current_chunk += " " + sentence
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            # Start new chunk with overlap from previous
            overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
            current_chunk = overlap_text + " " + sentence

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return [c for c in chunks if len(c) > 100]  # filter tiny chunks


def create_chunks_from_pages(pages: list[dict], doc_meta: dict, filename: str) -> list[dict]:
    """
    Converts pages into chunks with full metadata.

    Each chunk includes:
        - id: unique hash for deduplication
        - text: the chunk content
        - metadata: source, page, type, title, year
    """
    all_chunks = []
    chunk_index = 0

    for page_data in pages:
        page_chunks = chunk_text(page_data["text"])

        for chunk_text_content in page_chunks:
            # Create deterministic ID from content hash
            chunk_id = hashlib.md5(
                f"{filename}_{page_data['page']}_{chunk_index}".encode()
            ).hexdigest()

            all_chunks.append({
                "id": chunk_id,
                "text": chunk_text_content,
                "metadata": {
                    "source":    filename,
                    "title":     doc_meta.get("title", filename),
                    "type":      doc_meta.get("type", "document"),
                    "year":      doc_meta.get("year", 0),
                    "publisher": doc_meta.get("source", "Unknown"),
                    "page":      page_data["page"],
                    "chunk_idx": chunk_index,
                    "text":      chunk_text_content[:500],  # store preview in metadata
                },
            })
            chunk_index += 1

    return all_chunks


# ------------------------------------------------------------------
# Embedding
# ------------------------------------------------------------------

def embed_chunks(chunks: list[dict], client: OpenAI) -> list[dict]:
    """
    Embeds chunk texts using OpenAI text-embedding-3-small.

    Processes in batches to avoid rate limits.
    Returns chunks with 'values' field added.
    """
    texts = [c["text"] for c in chunks]
    embedded = []

    # Process in batches of 50
    batch_size = 50
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        batch_chunks = chunks[i:i + batch_size]

        try:
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=batch_texts,
            )
            for chunk, embedding_obj in zip(batch_chunks, response.data):
                embedded.append({
                    "id":       chunk["id"],
                    "values":   embedding_obj.embedding,
                    "metadata": chunk["metadata"],
                })
            print(f"    Embedded batch {i//batch_size + 1} ({len(batch_texts)} chunks)")
            time.sleep(0.5)  # rate limit buffer

        except Exception as e:
            print(f"    ERROR embedding batch {i//batch_size + 1}: {e}")
            time.sleep(2)

    return embedded


# ------------------------------------------------------------------
# Pinecone upsert
# ------------------------------------------------------------------

def upsert_to_pinecone(vectors: list[dict], index, namespace: str = NAMESPACE):
    """
    Upserts vectors to Pinecone in batches.
    """
    total = 0
    for i in range(0, len(vectors), BATCH_SIZE):
        batch = vectors[i:i + BATCH_SIZE]
        try:
            index.upsert(vectors=batch, namespace=namespace)
            total += len(batch)
            print(f"    Upserted batch {i//BATCH_SIZE + 1} ({len(batch)} vectors, {total} total)")
            time.sleep(0.3)
        except Exception as e:
            print(f"    ERROR upserting batch: {e}")

    return total


# ------------------------------------------------------------------
# Main ingestion function
# ------------------------------------------------------------------

def ingest_document(pdf_path: Path, index, openai_client: OpenAI) -> dict:
    """
    Full pipeline for one document:
        PDF → extract → chunk → embed → upsert
    """
    filename = pdf_path.name
    doc_meta = DOCUMENT_METADATA.get(filename, {
        "title": filename,
        "type": "document",
        "year": 0,
        "source": "Unknown",
    })

    print(f"\n{'='*60}")
    print(f"Ingesting: {filename}")
    print(f"Title: {doc_meta.get('title')}")
    print(f"{'='*60}")

    # Step 1: Extract text
    print("Step 1: Extracting text...")
    pages = extract_text_from_pdf(pdf_path)
    if not pages:
        print("  No text extracted — skipping")
        return {"file": filename, "status": "skipped", "chunks": 0}

    # Step 2: Chunk
    print("Step 2: Chunking text...")
    chunks = create_chunks_from_pages(pages, doc_meta, filename)
    print(f"  Created {len(chunks)} chunks")

    # Step 3: Embed
    print("Step 3: Embedding chunks...")
    vectors = embed_chunks(chunks, openai_client)
    print(f"  Embedded {len(vectors)} vectors")

    # Step 4: Upsert
    print("Step 4: Upserting to Pinecone...")
    total_upserted = upsert_to_pinecone(vectors, index)

    result = {
        "file":    filename,
        "status":  "success",
        "pages":   len(pages),
        "chunks":  len(chunks),
        "vectors": total_upserted,
    }
    print(f"\n✅ Done: {filename} — {total_upserted} vectors indexed")
    return result


def setup_pinecone(reset: bool = False):
    """
    Connects to Pinecone and ensures the index exists.
    Uses existing 'doc-intelligence' index with chinook-music namespace.
    """
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY not found in .env")

    pc = Pinecone(api_key=api_key)

    # Check if index exists
    existing_indexes = [idx.name for idx in pc.list_indexes()]

    if INDEX_NAME not in existing_indexes:
        print(f"Creating new Pinecone index: {INDEX_NAME}")
        pc.create_index(
            name=INDEX_NAME,
            dimension=1536,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        time.sleep(10)  # wait for index to be ready
        print(f"Index '{INDEX_NAME}' created")
    else:
        print(f"Using existing index: {INDEX_NAME}")

    index = pc.Index(INDEX_NAME)

    # If reset, delete the chinook namespace
    if reset:
        print(f"Resetting namespace '{NAMESPACE}'...")
        try:
            index.delete(delete_all=True, namespace=NAMESPACE)
            time.sleep(2)
            print("Namespace cleared")
        except Exception as e:
            print(f"Reset warning: {e}")

    # Show current stats
    stats = index.describe_index_stats()
    print(f"Index stats: {stats.total_vector_count} total vectors")

    return index


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ingest PDFs into Pinecone for Agentic RAG")
    parser.add_argument("--file", type=str, help="Ingest a specific file only")
    parser.add_argument("--reset", action="store_true", help="Clear namespace before ingesting")
    parser.add_argument("--list", action="store_true", help="List available documents")
    args = parser.parse_args()

    # List mode
    if args.list:
        print("\nAvailable documents:")
        for f in DOCUMENTS_DIR.glob("*.pdf"):
            meta = DOCUMENT_METADATA.get(f.name, {})
            size = f.stat().st_size / (1024 * 1024)
            print(f"  {f.name} ({size:.1f}MB) — {meta.get('title', 'Unknown')}")
        return

    # Setup clients
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    index = setup_pinecone(reset=args.reset)

    # Determine which files to ingest
    if args.file:
        pdf_paths = [DOCUMENTS_DIR / args.file]
        if not pdf_paths[0].exists():
            print(f"ERROR: File not found: {pdf_paths[0]}")
            sys.exit(1)
    else:
        pdf_paths = sorted(DOCUMENTS_DIR.glob("*.pdf"))
        if not pdf_paths:
            print(f"ERROR: No PDFs found in {DOCUMENTS_DIR}")
            sys.exit(1)

    print(f"\nIngesting {len(pdf_paths)} document(s) into namespace '{NAMESPACE}'")

    # Ingest each document
    results = []
    for pdf_path in pdf_paths:
        result = ingest_document(pdf_path, index, openai_client)
        results.append(result)

    # Summary
    print(f"\n{'='*60}")
    print("INGESTION SUMMARY")
    print(f"{'='*60}")
    total_vectors = 0
    for r in results:
        status_icon = "✅" if r["status"] == "success" else "⚠️"
        print(f"{status_icon} {r['file']}")
        if r["status"] == "success":
            print(f"   Pages: {r['pages']} | Chunks: {r['chunks']} | Vectors: {r['vectors']}")
            total_vectors += r["vectors"]

    print(f"\nTotal vectors indexed: {total_vectors}")
    print(f"Namespace: {NAMESPACE}")
    print(f"Index: {INDEX_NAME}")

    # Final index stats
    stats = index.describe_index_stats()
    print(f"Index total vectors: {stats.total_vector_count}")


if __name__ == "__main__":
    main()
