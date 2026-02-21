"""
verify_migration.py — Post-migration verification for Supabase.

Connects to both local and Supabase databases and verifies:
  - Row counts match (documents + chunk_records)
  - Embedding integrity: spot-checks 3 vectors (first, middle, last)
  - HNSW index exists and is usable
  - A sample cosine-distance query returns results

Usage:
    # With both URLs explicit:
    LOCAL_DB_URL="postgresql://ia:ia@localhost:5432/ia" \\
    SUPABASE_DB_URL="postgresql://postgres:<PW>@db.<REF>.supabase.co:5432/postgres" \\
    python scripts/verify_migration.py

    # After updating .env:
    python scripts/verify_migration.py
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Read URLs — local uses the same default as db/session.py
# ---------------------------------------------------------------------------

_DEFAULT_LOCAL = "postgresql+psycopg://ia:ia@localhost:5432/ia"

LOCAL_URL: str = os.getenv("LOCAL_DB_URL", _DEFAULT_LOCAL)
SUPA_URL: str = os.getenv("SUPABASE_DB_URL", "")


# Ensure SQLAlchemy driver prefix
def _sqlalchemy_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


LOCAL_URL = _sqlalchemy_url(LOCAL_URL)

if not SUPA_URL:
    print("ERROR: SUPABASE_DB_URL is not set.")
    print(
        "  export SUPABASE_DB_URL='postgresql://postgres:<PW>@db.<REF>.supabase.co:5432/postgres'"
    )
    sys.exit(1)

SUPA_URL = _sqlalchemy_url(SUPA_URL)

# ---------------------------------------------------------------------------
# SQLAlchemy engines (no app startup needed — direct connections)
# ---------------------------------------------------------------------------

from sqlalchemy import create_engine, text  # noqa: E402

_CONNECT_ARGS = {"connect_timeout": 15}

try:
    local_engine = create_engine(LOCAL_URL, connect_args=_CONNECT_ARGS, pool_pre_ping=True)
    supa_engine = create_engine(SUPA_URL, connect_args=_CONNECT_ARGS, pool_pre_ping=True)
except Exception as exc:
    print(f"ERROR: Could not create engines: {exc}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASS = "\033[32m PASS \033[0m"
FAIL = "\033[31m FAIL \033[0m"
WARN = "\033[33m WARN \033[0m"


def _count(engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()  # noqa: S608


def _check(label: str, ok: bool, detail: str = "") -> bool:
    status = PASS if ok else FAIL
    print(f"  [{status}] {label}" + (f"  — {detail}" if detail else ""))
    return ok


# ---------------------------------------------------------------------------
# Main verification
# ---------------------------------------------------------------------------


def main() -> None:
    print()
    print("=" * 60)
    print("  Supabase Migration Verification")
    print("=" * 60)
    print()

    all_ok = True

    # -----------------------------------------------------------------------
    # 1. Connectivity
    # -----------------------------------------------------------------------
    print("1. Connectivity")
    try:
        with local_engine.connect() as c:
            c.execute(text("SELECT 1"))
        all_ok &= _check("Local DB reachable", True)
    except Exception as exc:
        all_ok &= _check("Local DB reachable", False, str(exc))

    try:
        with supa_engine.connect() as c:
            c.execute(text("SELECT 1"))
        all_ok &= _check("Supabase reachable", True)
    except Exception as exc:
        all_ok &= _check("Supabase reachable", False, str(exc))
        print()
        print("  Cannot reach Supabase — aborting remaining checks.")
        sys.exit(1)

    print()

    # -----------------------------------------------------------------------
    # 2. pgvector extension
    # -----------------------------------------------------------------------
    print("2. pgvector extension")
    with supa_engine.connect() as c:
        ext = c.execute(text("SELECT COUNT(*) FROM pg_extension WHERE extname = 'vector'")).scalar()
    all_ok &= _check("vector extension enabled", ext == 1)
    print()

    # -----------------------------------------------------------------------
    # 3. Row count parity
    # -----------------------------------------------------------------------
    print("3. Row counts")
    for table in ("documents", "chunk_records"):
        local_n = _count(local_engine, table)
        supa_n = _count(supa_engine, table)
        ok = local_n == supa_n
        all_ok &= _check(
            f"{table}",
            ok,
            f"local={local_n}, supabase={supa_n}" + ("  ✓" if ok else "  ← MISMATCH"),
        )
    print()

    # -----------------------------------------------------------------------
    # 4. Embedding spot-check (first, middle, last chunk_record)
    # -----------------------------------------------------------------------
    print("4. Embedding integrity (spot-check 3 rows)")
    with local_engine.connect() as lc, supa_engine.connect() as sc:
        local_ids = (
            [r[0] for r in lc.execute(text("SELECT id FROM chunk_records ORDER BY id ASC LIMIT 1"))]
            + [
                r[0]
                for r in lc.execute(
                    text(
                        "SELECT id FROM chunk_records ORDER BY id ASC OFFSET (SELECT COUNT(*)/2 FROM chunk_records) LIMIT 1"
                    )
                )
            ]
            + [
                r[0]
                for r in lc.execute(text("SELECT id FROM chunk_records ORDER BY id DESC LIMIT 1"))
            ]
        )

        for row_id in local_ids:
            local_emb = lc.execute(
                text("SELECT embedding FROM chunk_records WHERE id = :id"), {"id": row_id}
            ).scalar()
            supa_emb = sc.execute(
                text("SELECT embedding FROM chunk_records WHERE id = :id"), {"id": row_id}
            ).scalar()

            if local_emb is None or supa_emb is None:
                all_ok &= _check(f"row id={row_id}", False, "embedding is NULL in one DB")
                continue

            # Compare first 5 floats for a quick sanity check
            local_vals = local_emb[:5] if hasattr(local_emb, "__getitem__") else []
            supa_vals = supa_emb[:5] if hasattr(supa_emb, "__getitem__") else []
            match = local_vals == supa_vals
            all_ok &= _check(
                f"row id={row_id} embedding prefix",
                match,
                "match" if match else f"local={local_vals[:3]} supa={supa_vals[:3]}",
            )
    print()

    # -----------------------------------------------------------------------
    # 5. HNSW index
    # -----------------------------------------------------------------------
    print("5. Indexes")
    with supa_engine.connect() as c:
        hnsw = c.execute(
            text(
                "SELECT COUNT(*) FROM pg_indexes "
                "WHERE tablename='chunk_records' AND indexname='idx_chunk_embedding_hnsw'"
            )
        ).scalar()
    all_ok &= _check("HNSW index (idx_chunk_embedding_hnsw)", hnsw == 1)
    print()

    # -----------------------------------------------------------------------
    # 6. Sample cosine-distance query (uses pgvector operator <=>)
    # -----------------------------------------------------------------------
    print("6. Cosine-distance query sanity check")
    try:
        with supa_engine.connect() as c:
            # Use a zero vector — not meaningful but validates the operator works
            sample_embedding = "[" + ",".join(["0.0"] * 1536) + "]"
            rows = c.execute(
                text(
                    "SELECT id, 1 - (embedding <=> CAST(:emb AS vector)) AS score "
                    "FROM chunk_records "
                    "ORDER BY embedding <=> CAST(:emb AS vector) "
                    "LIMIT 3"
                ),
                {"emb": sample_embedding},
            ).fetchall()
        all_ok &= _check(
            f"<=> operator returns {len(rows)} row(s)",
            len(rows) > 0,
        )
    except Exception as exc:
        all_ok &= _check("cosine-distance query", False, str(exc))
    print()

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print("=" * 60)
    if all_ok:
        print("\033[32m  ALL CHECKS PASSED — migration verified!\033[0m")
        print()
        print("  Next: update DATABASE_URL in .env to your Supabase URL:")
        print(f"  DATABASE_URL={SUPA_URL}")
        print()
        print("  Then restart the API and run: pytest -q")
    else:
        print("\033[31m  SOME CHECKS FAILED — review the output above.\033[0m")
        print()
        sys.exit(1)
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
