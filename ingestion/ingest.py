"""
Ingestion pipeline: load -> chunk -> embed -> persist.

CLI entry point::

    python -m ingestion.ingest --data-dir data --limit 10
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import time

from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.chunking import Chunk, chunk_text
from core.text import extract_pdf_text, extract_text
from db.models import Base, ChunkRecord
from db.session import SessionLocal, engine
from ingestion.embeddings import OpenAIEmbeddingProvider
from ingestion.loaders import LoadedDocument, load_documents, load_pdf_pages

logger = logging.getLogger(__name__)

# Chunks shorter than this are too small to produce useful embeddings.
MIN_CHUNK_TOKENS = 20

# Retry parameters for transient embedding API errors.
_MAX_RETRIES = 3
_RETRY_BASE_SECONDS = 2.0


def _extract_text(doc: LoadedDocument) -> str:
    """Choose extraction strategy based on file extension.

    Delegates to the pure ``core.text.extract_text`` dispatcher so the
    mapping of extension to strategy lives in the core layer.
    """
    extension = pathlib.PurePosixPath(doc.name).suffix
    return extract_text(doc.content, extension=extension)


def _chunk_pdf_document(doc: LoadedDocument) -> list[Chunk]:
    """Chunk a PDF document page by page, preserving page numbers.

    Each PDF page is extracted via :func:`load_pdf_pages`, its text is
    normalised with :func:`extract_pdf_text`, and then chunked
    independently.  Every resulting :class:`Chunk` carries the
    originating ``page_number`` so downstream citations can reference
    the exact page.

    ``chunk_index`` is globally sequential across all pages of the
    document (not reset per page).
    """
    pages = load_pdf_pages(doc.path)
    all_chunks: list[Chunk] = []
    global_chunk_index = 0

    for page in pages:
        text = extract_pdf_text(page.text)
        if not text.strip():
            continue
        page_chunks = chunk_text(text, source_path=doc.path)
        # Re-number chunk_index globally and stamp page_number
        for chunk in page_chunks:
            patched = Chunk(
                doc_id=chunk.doc_id,
                source_path=chunk.source_path,
                source_name=chunk.source_name,
                chunk_index=global_chunk_index,
                text=chunk.text,
                token_start=chunk.token_start,
                token_end=chunk.token_end,
                page_number=page.page_number,
            )
            all_chunks.append(patched)
            global_chunk_index += 1

    return all_chunks


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
                page_number=chunk.page_number,
                embedding=emb,
            )
        )
    return records


def _embed_with_retry(
    embedder: OpenAIEmbeddingProvider,
    texts: list[str],
    *,
    max_retries: int = _MAX_RETRIES,
    base_seconds: float = _RETRY_BASE_SECONDS,
) -> list[list[float]]:
    """Embed texts with exponential backoff on transient failures.

    Args:
        embedder: Embedding provider instance.
        texts: Batch of texts to embed.
        max_retries: Maximum retry attempts (default: 3).
        base_seconds: Base sleep duration for backoff (default: 2s).

    Returns:
        List of embedding vectors.

    Raises:
        RuntimeError: If all retry attempts are exhausted.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return embedder.embed_texts(texts)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            wait = base_seconds * (2**attempt)
            logger.warning(
                "Embedding attempt %d/%d failed (%s), retrying in %.1fs",
                attempt + 1,
                max_retries,
                exc,
                wait,
            )
            time.sleep(wait)

    raise RuntimeError(f"Embedding failed after {max_retries} attempts: {last_exc}") from last_exc


def _get_existing_chunk_keys(
    session: SessionLocal,  # type: ignore[type-arg]
    source_paths: list[str],
) -> set[tuple[str, int]]:
    """Query DB for chunks that already exist (resume support).

    Returns a set of ``(source_path, chunk_index)`` tuples for
    chunks that are already persisted, so the pipeline can skip
    re-embedding them.
    """
    if not source_paths:
        return set()

    rows = (
        session.query(ChunkRecord.source_path, ChunkRecord.chunk_index)
        .filter(ChunkRecord.source_path.in_(source_paths))
        .all()
    )
    return {(r.source_path, r.chunk_index) for r in rows}


def _bulk_upsert(session: SessionLocal, records: list[ChunkRecord]) -> int:  # type: ignore[type-arg]
    """Insert records using ON CONFLICT DO NOTHING for true idempotency.

    Returns the number of rows actually inserted.
    """
    if not records:
        return 0

    values = [
        {
            "doc_id": r.doc_id,
            "source_path": r.source_path,
            "source_name": r.source_name,
            "chunk_index": r.chunk_index,
            "token_start": r.token_start,
            "token_end": r.token_end,
            "text": r.text,
            "page_number": r.page_number,
            "embedding": r.embedding,
        }
        for r in records
    ]

    stmt = (
        pg_insert(ChunkRecord)
        .values(values)
        .on_conflict_do_nothing(constraint="uq_chunk_source_index")
    )
    result = session.execute(stmt)
    session.commit()
    return result.rowcount  # type: ignore[return-value]


def run_pipeline(
    data_dir: str,
    *,
    limit: int | None = None,
    batch_size: int = 64,
) -> None:
    """
    Execute the full ingestion pipeline.

    1. Load ``.md`` / ``.txt`` / ``.pdf`` files from *data_dir*.
    2. Extract and normalize text.
    3. Chunk each document (skip chunks below ``MIN_CHUNK_TOKENS``).
       For PDFs, chunking is page-aware: each page is chunked separately
       and the resulting ``Chunk`` objects carry a ``page_number``.
    4. Skip chunks already in the database (resume support).
    5. Embed new chunk texts via OpenAI (with retry).
    6. Persist ``ChunkRecord`` rows to Postgres via ``ON CONFLICT DO NOTHING``.
    7. Print summary statistics and a sample row.
    """
    # --- 0. Ensure tables exist ---
    Base.metadata.create_all(bind=engine)

    # --- 1. Load ---
    docs = load_documents(data_dir, limit=limit)
    if not docs:
        print(f"No supported files found in {data_dir}")
        return

    print(f"Loaded {len(docs)} document(s) from {data_dir}")

    # --- 2 & 3. Extract + Chunk (with quality gate) ---
    all_chunks: list[Chunk] = []
    skipped_small = 0
    for doc in docs:
        extension = pathlib.PurePosixPath(doc.name).suffix.lower()

        if extension == ".pdf":
            # Page-aware chunking for PDFs
            doc_chunks = _chunk_pdf_document(doc)
        else:
            text = _extract_text(doc)
            if not text.strip():
                print(f"  [skip] {doc.name}: empty after extraction")
                continue
            doc_chunks = chunk_text(text, source_path=doc.path)

        # Quality gate: drop chunks below MIN_CHUNK_TOKENS
        quality_chunks = [
            c for c in doc_chunks if (c.token_end - c.token_start) >= MIN_CHUNK_TOKENS
        ]
        skipped_small += len(doc_chunks) - len(quality_chunks)
        all_chunks.extend(quality_chunks)
        print(f"  {doc.name}: {len(quality_chunks)} chunk(s)")

    if skipped_small:
        print(f"  Skipped {skipped_small} chunk(s) below {MIN_CHUNK_TOKENS} tokens")

    if not all_chunks:
        print("No chunks produced — nothing to embed.")
        return

    print(f"Total chunks: {len(all_chunks)}")

    # --- 4. Resume: skip chunks already in DB ---
    session = SessionLocal()
    try:
        source_paths = list({c.source_path for c in all_chunks})
        existing_keys = _get_existing_chunk_keys(session, source_paths)

        new_chunks = [c for c in all_chunks if (c.source_path, c.chunk_index) not in existing_keys]
        skipped_existing = len(all_chunks) - len(new_chunks)
        if skipped_existing:
            print(f"  Skipping {skipped_existing} chunk(s) already in DB (resume)")

        if not new_chunks:
            print("All chunks already persisted — nothing to embed.")
            return

        # --- 5. Embed new chunks (in batches, with retry) ---
        embedder = OpenAIEmbeddingProvider()
        all_embeddings: list[list[float]] = []
        texts = [c.text for c in new_chunks]
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_embeddings = _embed_with_retry(embedder, batch)
            all_embeddings.extend(batch_embeddings)
            print(f"  Embedded batch {i // batch_size + 1} ({len(batch)} texts)")

        # --- 6. Persist via ON CONFLICT DO NOTHING ---
        records = _chunks_to_records(new_chunks, all_embeddings)
        inserted = _bulk_upsert(session, records)
        print(f"Inserted {inserted} new chunk(s), skipped {len(records) - inserted} existing.")

        # --- 7. Summary ---
        if records:
            sample = records[0]
            print("\n--- Sample row ---")
            print(f"  doc_id:      {sample.doc_id}")
            print(f"  chunk_index: {sample.chunk_index}")
            print(f"  text:        {sample.text[:80]}...")
            print("--- Done ---")

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    """Parse CLI arguments and run the pipeline."""
    parser = argparse.ArgumentParser(
        description="Ingest .md/.txt/.pdf documents into Postgres with pgvector embeddings.",
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
