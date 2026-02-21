"""
OCR ingestion pipeline for scanned PDFs.

Uses Google Vision API to extract text page-by-page, caches results locally,
then chunks → embeds → persists to pgvector.

Usage::

    GOOGLE_APPLICATION_CREDENTIALS=path/to/key.json \\
    python -m ingestion.ingest_ocr \\
        --pdf data/music/books/_scanned/Bob_Katz.pdf \\
        --pdf data/music/books/_scanned/La_Masterizacion_de_audio_Bob_Katz.pdf \\
        --pdf data/music/books/_scanned/Schachter_Aldwell-Harmony_Voice_Leading.pdf
"""

from __future__ import annotations

import argparse
import logging
import time

from core.chunking import Chunk, chunk_text
from core.text import extract_pdf_text
from db.models import Base
from db.session import SessionLocal, engine
from ingestion.embeddings import OpenAIEmbeddingProvider
from ingestion.ingest import (
    _MAX_RETRIES,
    _RETRY_BASE_SECONDS,
    MIN_CHUNK_TOKENS,
    _bulk_upsert,
    _chunks_to_records,
    _get_existing_chunk_keys,
)
from ingestion.loaders_ocr import load_scanned_pdf_pages, ocr_pages_to_loaded_pages

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _chunk_ocr_document(pdf_path: str) -> list[Chunk]:
    """OCR a scanned PDF page-by-page and return chunks with page numbers.

    Uses :func:`load_scanned_pdf_pages` (Google Vision API + local cache)
    and then applies the same chunking pipeline as the regular PDF path.
    """
    logger.info("Starting OCR for: %s", pdf_path)
    ocr_pages = load_scanned_pdf_pages(pdf_path)
    loaded_pages = ocr_pages_to_loaded_pages(ocr_pages)

    all_chunks: list[Chunk] = []
    global_chunk_index = 0
    empty_pages = 0

    for page in loaded_pages:
        text = extract_pdf_text(page.text)
        if not text.strip():
            empty_pages += 1
            continue
        page_chunks = chunk_text(text, source_path=pdf_path)
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

    logger.info(
        "OCR complete: %d chunks from %d pages (%d empty pages skipped)",
        len(all_chunks),
        len(loaded_pages),
        empty_pages,
    )
    return all_chunks


def _embed_with_retry(
    embedder: OpenAIEmbeddingProvider,
    texts: list[str],
) -> list[list[float]]:
    """Embed with exponential backoff (mirrors ingest.py)."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return embedder.embed_texts(texts)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            wait = _RETRY_BASE_SECONDS * (2**attempt)
            logger.warning(
                "Embedding attempt %d/%d failed (%s), retrying in %.1fs",
                attempt + 1,
                _MAX_RETRIES,
                exc,
                wait,
            )
            time.sleep(wait)
    raise RuntimeError(f"Embedding failed after {_MAX_RETRIES} attempts: {last_exc}") from last_exc


def run_ocr_pipeline(pdf_paths: list[str], *, batch_size: int = 64) -> None:
    """Run OCR → chunk → embed → persist for a list of scanned PDFs.

    Args:
        pdf_paths: Absolute paths to scanned PDF files.
        batch_size: Number of texts per OpenAI embedding call.
    """
    Base.metadata.create_all(bind=engine)

    all_chunks: list[Chunk] = []
    skipped_small = 0

    for pdf_path in pdf_paths:
        doc_chunks = _chunk_ocr_document(pdf_path)
        quality_chunks = [
            c for c in doc_chunks if (c.token_end - c.token_start) >= MIN_CHUNK_TOKENS
        ]
        skipped_small += len(doc_chunks) - len(quality_chunks)
        all_chunks.extend(quality_chunks)
        name = pdf_path.split("/")[-1]
        logger.info("%s → %d chunk(s) after quality gate", name, len(quality_chunks))

    if skipped_small:
        logger.info("Skipped %d chunk(s) below %d tokens", skipped_small, MIN_CHUNK_TOKENS)

    if not all_chunks:
        logger.warning("No chunks produced — nothing to embed.")
        return

    logger.info("Total chunks to process: %d", len(all_chunks))

    session = SessionLocal()
    try:
        source_paths = list({c.source_path for c in all_chunks})
        existing_keys = _get_existing_chunk_keys(session, source_paths)
        new_chunks = [c for c in all_chunks if (c.source_path, c.chunk_index) not in existing_keys]
        skipped_existing = len(all_chunks) - len(new_chunks)
        if skipped_existing:
            logger.info("Skipping %d chunk(s) already in DB (resume)", skipped_existing)

        if not new_chunks:
            logger.info("All chunks already persisted — nothing to embed.")
            return

        embedder = OpenAIEmbeddingProvider()
        all_embeddings: list[list[float]] = []
        texts = [c.text for c in new_chunks]
        total_batches = (len(texts) + batch_size - 1) // batch_size

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_num = i // batch_size + 1
            logger.info("Embedding batch %d/%d (%d texts)", batch_num, total_batches, len(batch))
            batch_embeddings = _embed_with_retry(embedder, batch)
            all_embeddings.extend(batch_embeddings)

        records = _chunks_to_records(new_chunks, all_embeddings)
        inserted = _bulk_upsert(session, records)
        logger.info(
            "Done — inserted %d new chunk(s), skipped %d existing.",
            inserted,
            len(records) - inserted,
        )

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    """Parse CLI arguments and run the OCR ingestion pipeline."""
    parser = argparse.ArgumentParser(
        description="Ingest scanned PDFs via Google Vision OCR into pgvector.",
    )
    parser.add_argument(
        "--pdf",
        dest="pdfs",
        action="append",
        required=True,
        metavar="PATH",
        help="Path to a scanned PDF (repeat for multiple files).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Embedding batch size (default: 64).",
    )
    args = parser.parse_args()
    run_ocr_pipeline(args.pdfs, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
