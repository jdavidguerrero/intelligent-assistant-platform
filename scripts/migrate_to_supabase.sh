#!/usr/bin/env bash
# =============================================================================
# migrate_to_supabase.sh
#
# Migrates the intelligent-assistant platform database from local Postgres
# (Docker) to Supabase.
#
# Prerequisites (do these BEFORE running):
#   1. Create a Supabase project at https://supabase.com
#   2. In Supabase SQL Editor run:  CREATE EXTENSION IF NOT EXISTS vector;
#   3. In Supabase Dashboard → Settings → Database → Connection string
#      copy the "Direct connection" URI (not the pooler).
#   4. Export the variable:
#        export SUPABASE_DB_URL="postgresql://postgres:<PASSWORD>@db.<REF>.supabase.co:5432/postgres"
#
# Usage:
#   export SUPABASE_DB_URL="postgresql://postgres:..."
#   chmod +x scripts/migrate_to_supabase.sh
#   ./scripts/migrate_to_supabase.sh
#
# Optional overrides:
#   LOCAL_DB_URL   — defaults to postgresql://ia:ia@localhost:5432/ia
#   DUMP_FILE      — defaults to /tmp/ia_migration_$(date +%Y%m%d_%H%M%S).dump
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()    { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LOCAL_DB_URL="${LOCAL_DB_URL:-postgresql://ia:ia@localhost:5432/ia}"
DUMP_FILE="${DUMP_FILE:-/tmp/ia_migration_$(date +%Y%m%d_%H%M%S).dump}"

if [[ -z "${SUPABASE_DB_URL:-}" ]]; then
    fail "SUPABASE_DB_URL is not set.\nRun: export SUPABASE_DB_URL=\"postgresql://postgres:<PASSWORD>@db.<REF>.supabase.co:5432/postgres\""
fi

# Strip trailing slash just in case
LOCAL_DB_URL="${LOCAL_DB_URL%/}"
SUPABASE_DB_URL="${SUPABASE_DB_URL%/}"

echo ""
echo "=================================================================="
echo "  Intelligent Assistant Platform — Supabase Migration"
echo "=================================================================="
echo ""
info "Source  : ${LOCAL_DB_URL//:*@/:***@}"
info "Target  : ${SUPABASE_DB_URL//:*@/:***@}"
info "Dump    : ${DUMP_FILE}"
echo ""

# ---------------------------------------------------------------------------
# Phase A — Tool check
# ---------------------------------------------------------------------------
info "Phase A: Checking required tools..."

for tool in pg_dump psql pg_restore; do
    if ! command -v "$tool" &>/dev/null; then
        fail "$tool not found. Install with: brew install libpq (macOS) or apt-get install postgresql-client"
    fi
done
success "pg_dump, psql, pg_restore found"

# ---------------------------------------------------------------------------
# Phase B — Validate local DB
# ---------------------------------------------------------------------------
info "Phase B: Validating local database..."

LOCAL_DOCS=$(psql "$LOCAL_DB_URL" -t -c "SELECT COUNT(*) FROM documents;" 2>/dev/null | tr -d '[:space:]') \
    || fail "Cannot connect to local DB: ${LOCAL_DB_URL//:*@/:***@}"
LOCAL_CHUNKS=$(psql "$LOCAL_DB_URL" -t -c "SELECT COUNT(*) FROM chunk_records;" 2>/dev/null | tr -d '[:space:]')

success "Local DB: ${LOCAL_DOCS} documents, ${LOCAL_CHUNKS} chunk_records"

# ---------------------------------------------------------------------------
# Phase C — Validate Supabase connection + pgvector
# ---------------------------------------------------------------------------
info "Phase C: Validating Supabase connection and pgvector extension..."

psql "$SUPABASE_DB_URL" -c "SELECT 1;" &>/dev/null \
    || fail "Cannot connect to Supabase. Check SUPABASE_DB_URL and your project's network settings."

VECTOR_INSTALLED=$(psql "$SUPABASE_DB_URL" -t -c \
    "SELECT COUNT(*) FROM pg_extension WHERE extname = 'vector';" 2>/dev/null | tr -d '[:space:]')

if [[ "$VECTOR_INSTALLED" == "0" ]]; then
    fail "pgvector extension not enabled in Supabase.\nRun in Supabase SQL Editor:\n  CREATE EXTENSION IF NOT EXISTS vector;"
fi
success "Supabase reachable, pgvector extension confirmed"

# Check if tables already exist in Supabase
EXISTING=$(psql "$SUPABASE_DB_URL" -t -c \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('documents','chunk_records');" \
    2>/dev/null | tr -d '[:space:]')

if [[ "$EXISTING" == "2" ]]; then
    warn "Tables already exist in Supabase."
    SUPA_CHUNKS=$(psql "$SUPABASE_DB_URL" -t -c "SELECT COUNT(*) FROM chunk_records;" 2>/dev/null | tr -d '[:space:]')
    if [[ "$SUPA_CHUNKS" == "$LOCAL_CHUNKS" ]]; then
        success "Row counts match (${SUPA_CHUNKS}). Migration already complete — nothing to do."
        exit 0
    fi
    warn "Tables exist but row counts differ (local=${LOCAL_CHUNKS}, supabase=${SUPA_CHUNKS}). Proceeding with fresh restore."
    info "Dropping existing tables in Supabase to start clean..."
    psql "$SUPABASE_DB_URL" -c "DROP TABLE IF EXISTS chunk_records CASCADE; DROP TABLE IF EXISTS documents CASCADE;" \
        || fail "Could not drop existing tables."
fi

# ---------------------------------------------------------------------------
# Phase D — Dump local database (custom format, includes schema + data)
# ---------------------------------------------------------------------------
info "Phase D: Dumping local database to ${DUMP_FILE}..."

# Exclude pgvector extension itself from dump (already enabled in Supabase)
pg_dump "$LOCAL_DB_URL" \
    --format=custom \
    --no-owner \
    --no-privileges \
    --exclude-table-data="pg_*" \
    --file="$DUMP_FILE" \
    2>/dev/null || fail "pg_dump failed. Is the local Docker DB running?"

DUMP_SIZE=$(du -sh "$DUMP_FILE" | cut -f1)
success "Dump complete: ${DUMP_FILE} (${DUMP_SIZE})"

# ---------------------------------------------------------------------------
# Phase E — Restore to Supabase
# ---------------------------------------------------------------------------
info "Phase E: Restoring to Supabase (this may take a few minutes for large embeddings)..."

# --single-transaction: all-or-nothing restore
# --no-owner: don't try to set object ownership (Supabase restricts this)
# --no-privileges: skip GRANT/REVOKE (same reason)
# -j 4: parallel workers for faster restore of large tables
pg_restore "$DUMP_FILE" \
    --dbname="$SUPABASE_DB_URL" \
    --no-owner \
    --no-privileges \
    --single-transaction \
    -j 4 \
    2>&1 | grep -v "^pg_restore: warning" | grep -v "^$" || true

success "Restore complete"

# ---------------------------------------------------------------------------
# Phase F — Verify row counts
# ---------------------------------------------------------------------------
info "Phase F: Verifying row counts..."

SUPA_DOCS=$(psql "$SUPABASE_DB_URL" -t -c "SELECT COUNT(*) FROM documents;" 2>/dev/null | tr -d '[:space:]')
SUPA_CHUNKS=$(psql "$SUPABASE_DB_URL" -t -c "SELECT COUNT(*) FROM chunk_records;" 2>/dev/null | tr -d '[:space:]')

echo ""
echo "  ┌─────────────────────┬──────────┬──────────┐"
printf "  │ %-19s │ %-8s │ %-8s │\n" "Table" "Local" "Supabase"
echo "  ├─────────────────────┼──────────┼──────────┤"
printf "  │ %-19s │ %-8s │ %-8s │\n" "documents"     "$LOCAL_DOCS"   "$SUPA_DOCS"
printf "  │ %-19s │ %-8s │ %-8s │\n" "chunk_records"  "$LOCAL_CHUNKS" "$SUPA_CHUNKS"
echo "  └─────────────────────┴──────────┴──────────┘"
echo ""

if [[ "$LOCAL_DOCS" == "$SUPA_DOCS" && "$LOCAL_CHUNKS" == "$SUPA_CHUNKS" ]]; then
    success "Row counts match — migration verified!"
else
    fail "Row count mismatch! Local: docs=${LOCAL_DOCS}, chunks=${LOCAL_CHUNKS} | Supabase: docs=${SUPA_DOCS}, chunks=${SUPA_CHUNKS}"
fi

# ---------------------------------------------------------------------------
# Phase G — Verify HNSW index
# ---------------------------------------------------------------------------
info "Phase G: Checking HNSW vector index..."

HNSW=$(psql "$SUPABASE_DB_URL" -t -c \
    "SELECT COUNT(*) FROM pg_indexes WHERE tablename='chunk_records' AND indexname='idx_chunk_embedding_hnsw';" \
    2>/dev/null | tr -d '[:space:]')

if [[ "$HNSW" == "1" ]]; then
    success "HNSW index present (idx_chunk_embedding_hnsw)"
else
    warn "HNSW index not found — rebuilding..."
    psql "$SUPABASE_DB_URL" -c "
        CREATE INDEX IF NOT EXISTS idx_chunk_embedding_hnsw
        ON chunk_records USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    " && success "HNSW index created" || warn "HNSW index creation failed — run manually if needed"
fi

# ---------------------------------------------------------------------------
# Done — next steps
# ---------------------------------------------------------------------------
echo ""
echo "=================================================================="
echo -e "  ${GREEN}Migration complete!${NC}"
echo "=================================================================="
echo ""
echo "  Next step: update your .env with the Supabase DATABASE_URL"
echo ""
echo "  The SQLAlchemy driver prefix (+psycopg) must be added:"
SUPA_SQLALCHEMY="${SUPABASE_DB_URL/postgresql:\/\//postgresql+psycopg:\/\/}"
echo "  DATABASE_URL=${SUPA_SQLALCHEMY}"
echo ""
echo "  Then run the verification script:"
echo "  python scripts/verify_migration.py"
echo ""

# Clean up dump file
read -r -p "Delete dump file ${DUMP_FILE}? [y/N] " response
if [[ "${response,,}" == "y" ]]; then
    rm -f "$DUMP_FILE"
    success "Dump file deleted"
else
    info "Dump file kept at ${DUMP_FILE}"
fi
