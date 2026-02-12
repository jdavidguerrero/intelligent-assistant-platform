"""
Ingestion pipeline: load -> chunk -> embed -> persist.

CLI entry point::

    python -m ingestion.ingest --data-dir data --limit 10
"""

from __future__ import annotations

import argparse

from core.chunking import Chunk, chunk_text
from core.text import extract_markdown_text, extract_plaintext
from db.models import Base, ChunkRecord
from db.session import SessionLocal, engine
from ingestion.embeddings import OpenAIEmbeddingProvider
from ingestion.loaders import LoadedDocument, load_documents


def _extract_text(doc: LoadedDocument) -> str:
    """Choose extraction strategy based on file extension."""
    if doc.name.lower().endswith(".md"):
        return extract_markdown_text(doc.content)
    return extract_plaintext(doc.content)


def _chunks_to_records(
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> list[ChunkRecord]:
    """Convert core Chunks + embeddings into ORM records."""
    records: list[ChunkRecord] = []
    for chunk, emb in zip(chunks, embeddings, strict=True):
        records.append(
            ChunkRecord(
                doc_id=chunk.doc_id,
                source_path=chunk.source_path,
                source_name=chunk.source_name,
                chunk_index=chunk.chunk_index,
                token_start=chunk.token_start,
                token_end=chunk.token_end,
                text=chunk.text,
                embedding=emb,
            )
        )
    return records


def run_pipeline(
    data_dir: str,
    *,
    limit: int | None = None,
    batch_size: int = 64,
) -> None:
    """
    Execute the full ingestion pipeline.

    1. Load ``.md`` / ``.txt`` files from *data_dir*.
    2. Extract and normalize text.
    3. Chunk each document.
    4. Embed chunk texts via OpenAI.
    5. Persist ``ChunkRecord`` rows to Postgres.
    6. Print summary statistics and a sample row.
    """
    # --- 0. Ensure tables exist ---
    Base.metadata.create_all(bind=engine)

    # --- 1. Load ---
    docs = load_documents(data_dir, limit=limit)
    if not docs:
        print(f"No .md/.txt files found in {data_dir}")
        return

    print(f"Loaded {len(docs)} document(s) from {data_dir}")

    # --- 2 & 3. Extract + Chunk ---
    all_chunks: list[Chunk] = []
    for doc in docs:
        text = _extract_text(doc)
        if not text.strip():
            print(f"  [skip] {doc.name}: empty after extraction")
            continue
        doc_chunks = chunk_text(text, source_path=doc.path)
        all_chunks.extend(doc_chunks)
        print(f"  {doc.name}: {len(doc_chunks)} chunk(s)")

    if not all_chunks:
        print("No chunks produced — nothing to embed.")
        return

    print(f"Total chunks: {len(all_chunks)}")

    # --- 4. Embed (in batches) ---
    embedder = OpenAIEmbeddingProvider()
    all_embeddings: list[list[float]] = []
    texts = [c.text for c in all_chunks]
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        all_embeddings.extend(embedder.embed_texts(batch))
        print(f"  Embedded batch {i // batch_size + 1} ({len(batch)} texts)")

    # --- 5. Persist ---
    records = _chunks_to_records(all_chunks, all_embeddings)
    session = SessionLocal()
    try:
        # Use merge() for idempotent ingestion - skips duplicates via UniqueConstraint
        for record in records:
            session.merge(record)
        session.commit()
        print(f"Upserted {len(records)} chunk record(s) into Postgres.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    # --- 6. Summary ---
    sample = records[0]
    print("\n--- Sample row ---")
    print(f"  doc_id:      {sample.doc_id}")
    print(f"  chunk_index: {sample.chunk_index}")
    print(f"  text:        {sample.text[:80]}...")
    print("--- Done ---")


def main() -> None:
    """Parse CLI arguments and run the pipeline."""
    parser = argparse.ArgumentParser(
        description="Ingest .md/.txt documents into Postgres with pgvector embeddings.",
    )
    parser.add_argument(
        "--data-dir",
        required=True,
        help="Root directory containing documents to ingest.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of files to process.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Number of texts per embedding API call (default: 64).",
    )
    args = parser.parse_args()
    run_pipeline(args.data_dir, limit=args.limit, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
