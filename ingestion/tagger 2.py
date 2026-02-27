"""CLI script to back-fill sub_domain tags on existing ChunkRecord rows.

Usage
-----
    python -m ingestion.tagger [--dry-run] [--batch-size N]

Options
-------
--dry-run       Print what would be tagged without writing to the DB.
--batch-size N  Number of rows to process per DB round-trip (default: 200).
"""

from __future__ import annotations

import argparse
import logging
from collections import defaultdict

from sqlalchemy.orm import Session

from db.models import ChunkRecord
from db.session import SessionLocal
from domains.music.tagger_logic import infer_sub_domain

logger = logging.getLogger(__name__)


def tag_chunks(
    session: Session,
    dry_run: bool = False,
    batch_size: int = 200,
) -> dict[str, int]:
    """Assign sub_domain tags to untagged ChunkRecord rows.

    Processes rows in batches to keep memory usage bounded.  Only rows where
    ``sub_domain IS NULL`` are considered; rows that already have a tag are
    skipped.

    Parameters
    ----------
    session:
        Active SQLAlchemy session.
    dry_run:
        When True, infer tags but do not commit changes to the database.
    batch_size:
        Number of rows fetched per iteration.

    Returns
    -------
    dict[str, int]
        Counts per sub_domain label, plus an "untagged" key for rows where
        ``infer_sub_domain`` returned None.
    """
    stats: dict[str, int] = defaultdict(int)
    offset = 0

    while True:
        batch: list[ChunkRecord] = (
            session.query(ChunkRecord)
            .filter(ChunkRecord.sub_domain.is_(None))
            .offset(offset)
            .limit(batch_size)
            .all()
        )
        if not batch:
            break

        for chunk in batch:
            tag = infer_sub_domain(
                source_path=chunk.source_path,
                text=chunk.text,
            )
            if tag is not None:
                if not dry_run:
                    chunk.sub_domain = tag.sub_domain
                stats[tag.sub_domain] += 1
            else:
                stats["untagged"] += 1

        if not dry_run:
            session.commit()

        offset += batch_size

    return dict(stats)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Back-fill sub_domain tags on chunk_records rows.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Infer tags without writing to the database.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        metavar="N",
        help="Rows processed per batch (default: 200).",
    )
    return parser


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    args = _build_parser().parse_args()

    session = SessionLocal()
    try:
        stats = tag_chunks(
            session=session,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )
    finally:
        session.close()

    mode = "DRY RUN" if args.dry_run else "COMMITTED"
    logger.info("[%s] Sub-domain tagging complete. Stats:", mode)
    for label, count in sorted(stats.items()):
        logger.info("  %-20s %d", label, count)
