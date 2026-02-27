"""Migration: add sub_domain column + index to chunk_records. Idempotent."""

import logging

from sqlalchemy import text

from db.session import engine

logger = logging.getLogger(__name__)


def run() -> None:
    """Add sub_domain VARCHAR(64) column and partial index to chunk_records.

    Safe to run multiple times — checks for column existence before altering.
    """
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='chunk_records' AND column_name='sub_domain'"
            )
        )
        if result.fetchone():
            logger.info("sub_domain column already exists — skipping")
            return
        conn.execute(text("ALTER TABLE chunk_records ADD COLUMN sub_domain VARCHAR(64) NULL"))
        conn.execute(
            text(
                "CREATE INDEX idx_chunk_sub_domain ON chunk_records(sub_domain) "
                "WHERE sub_domain IS NOT NULL"
            )
        )
        logger.info("Migration complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
