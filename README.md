# Musical Intelligence Platform

**OpenDock's cloud brain — a production-grade AI system for music production and live performance intelligence.**

A musician asks "How do I create tension before a drop in organic house?" and gets a grounded, cited answer drawn from Pete Tong Academy, Bob Katz, and Schachter-Aldwell in under 2 seconds. The system remembers their last practice session, routes the query to the right AI model, logs the interaction, and degrades gracefully if the internet is down.

This is not a portfolio project. It is the AI layer of an intelligent musical instrument.

---

## What it does

| Capability | How |
|-----------|-----|
| **Grounded musical Q&A** | RAG over 12,043 chunks from Pete Tong, Bob Katz, music theory texts |
| **Session memory** | Remembers practice topics, BPMs, keys across sessions with time decay |
| **Tool orchestration** | Logs sessions, analyzes tracks, suggests chords, inserts into Ableton |
| **Multi-model routing** | Fast model for lookups, powerful for creative, offline for realtime |
| **Genre-aware answers** | Organic house recipes, afrobeat patterns, classical theory contexts |
| **Offline degradation** | Returns raw excerpts when LLM unavailable — never a blank screen |
| **Hardware protocol** | MCP server bridges the instrument to every capability above |

---

## Quickstart (5 minutes)

### Prerequisites
- Python 3.12+
- Docker + Docker Compose
- OpenAI API key
- Anthropic API key (for local/realtime tier, optional)

### 1 — Clone and install

```bash
git clone https://github.com/youruser/intelligent-assistant-platform.git
cd intelligent-assistant-platform
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # ruff + pytest
```

### 2 — Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your API keys:
#   OPENAI_API_KEY=sk-...
#   ANTHROPIC_API_KEY=sk-ant-...  (optional — enables Tier 3 / claude-haiku)
#   DATABASE_URL=postgresql+psycopg://ia:ia@localhost:5432/ia
#   REDIS_URL=redis://localhost:6379/0
```

### 3 — Start infrastructure

```bash
docker compose up -d
# Starts: pgvector/postgres:16 on :5432 and redis:7 on :6379
```

### 4 — Initialize the database

```bash
python -c "from db.init_db import init_db; init_db()"
```

### 5 — Start the API

```bash
uvicorn api.main:app --reload --port 8000
```

### 6 — Ask a musical question

```bash
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I sidechain a kick with a bass in organic house?", "use_tools": false}' \
  | python -m json.tool
```

**Expected**: A cited answer with sources from Pete Tong / Bob Katz, `usage.tier` field, response time < 3s.

---

## One-Command Docker Deployment

```bash
# Build and run the full platform (API + pgvector + redis)
docker compose -f compose.yml -f compose.api.yml up --build -d
```

The API container uses the `Dockerfile` in the project root. Environment variables are read from `.env`.

### Health check

```bash
curl http://localhost:8000/health
# {"status": "ok"}

curl http://localhost:8000/metrics
# Prometheus metrics in text format
```

---

## Ingest your first document

```bash
# Ingest a PDF into the knowledge base
python -m ingestion.ingest --path docs/my-book.pdf --sub-domain mixing

# Ingest a scanned PDF (requires GOOGLE_VISION_API_KEY)
python ingestion/ingest_ocr.py --path docs/scanned-mastering.pdf

# Run the full eval after ingestion to verify quality
python scripts/run_eval.py --max-queries 10
```

---

## Multi-Model Routing (opt-in)

The platform supports routing queries to different models based on task type.
Enable it with the `USE_ROUTING=true` environment variable:

```bash
USE_ROUTING=true uvicorn api.main:app --reload

# Response now includes:
# "usage": {
#   "tier": "fast",          ← which model tier was used
#   "cost_usd": 0.000042,    ← estimated cost for this call
#   "model": "gpt-4o-mini"
# }
```

| Task type | Default model | Use case |
|-----------|--------------|----------|
| `factual` | gpt-4o-mini | "What BPM is house music?" |
| `creative` | gpt-4o | "Suggest a 2-week practice plan" |
| `realtime` | claude-haiku-4 | "Detect the key right now" |

Override model names via env vars: `TIER_FAST_MODEL`, `TIER_STANDARD_MODEL`, `TIER_LOCAL_MODEL`.

Projected cost savings vs always-gpt-4o: **~56%** (based on 60% factual / 35% creative / 5% realtime distribution).

---

## Memory System

The platform learns from every interaction and personalizes responses:

```bash
# Check what the system remembers about you
curl http://localhost:8000/memory?session_id=my-session

# Add a memory explicitly
curl -X POST http://localhost:8000/memory \
  -H "Content-Type: application/json" \
  -d '{"session_id": "my-session", "memory_type": "preference", "content": "I play in A minor"}'

# Now ask a question — the system will inject relevant memories
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "What chord progressions work well for my style?", "session_id": "my-session"}'
```

Memories decay over time: `score = cosine_similarity × e^(-0.1 × days)`. Sessions from yesterday rank higher than sessions from last month.

---

## MCP Server (for hardware/AI agents)

The platform exposes all capabilities as MCP tools via stdin/stdout:

```bash
# Start the MCP server (connects to the running API)
python -m musical_mcp.server

# Available tools:
# - search_production_knowledge(query, top_k)
# - log_practice_session(topic, duration_minutes, key_practiced, bpm_practiced)
# - create_session_note(category, title, content, tags)
# - analyze_track(file_path)
# - suggest_chord_progression(key, genre, mood, bars)
# - suggest_compatible_tracks(key, bpm)
# - ableton_insert_chords(chords, beats_per_chord, velocity, octave)
```

Configure in Claude Desktop or any MCP-compatible client:

```json
{
  "mcpServers": {
    "musical-intelligence": {
      "command": "python",
      "args": ["-m", "musical_mcp.server"],
      "cwd": "/path/to/intelligent-assistant-platform",
      "env": {
        "OPENAI_API_KEY": "sk-...",
        "IAP_BASE_URL": "http://localhost:8000"
      }
    }
  }
}
```

---

## Run the Golden Set Evaluation

```bash
# Quick eval (10 queries, mocked providers)
python scripts/run_eval.py --max-queries 10

# Full eval with real API calls (requires OPENAI_API_KEY)
python scripts/run_eval.py

# Tier comparison — compare cost vs quality across models
python scripts/run_tier_eval.py --max-queries 5  # smoke test
python scripts/run_tier_eval.py                   # full 40 queries

# Run the full test suite
pytest -q
# Expected: 2168 passed, 21 skipped, 0 failed
```

### Evaluation baseline (Week 6)

| Category | Score |
|----------|-------|
| Musical queries (15) | 13/15 = 87% |
| Hallucination refusal (10 adversarial) | 10/10 = 100% |
| Disambiguation queries | 2/3 = 67% |

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the complete module inventory, data flow diagram, and OpenDock convergence table.

```
┌──────────────┐     MCP stdio      ┌────────────────────────────────────┐
│  OpenDock    │◄──────────────────►│  Musical Intelligence Platform     │
│  Hardware    │                    │                                    │
│  (instrument)│                    │  POST /ask ─► RAG pipeline         │
└──────────────┘                    │              ├── Query expansion    │
                                    │              ├── Embedding          │
┌──────────────┐                    │              ├── pgvector search    │
│  Claude      │◄── MCP tools ─────►│              ├── Memory injection   │
│  Desktop /   │                    │              ├── Multi-model route  │
│  AI Agent    │                    │              └── Citation validate  │
└──────────────┘                    │                                    │
                                    │  Tools: session log, track analyze  │
                                    │  Memory: SQLite, time decay         │
                                    │  Infra: Redis, circuit breaker      │
                                    └────────────────────────────────────┘
```

**Layer rules (enforced in tests):**
```
api/ → ingestion/ → core/
api/ → db/
core/ must stay pure — no DB, no network, no filesystem
```

---

## Project Structure

```
├── core/           Pure logic (routing, RAG, memory, chunking)
├── ingestion/      Side effects (embeddings, generation, memory store)
├── db/             SQLAlchemy + pgvector persistence
├── api/            FastAPI HTTP boundary
├── musical_mcp/    MCP server for hardware/AI agent integration
├── infrastructure/ Cache, circuit breaker, rate limiter, metrics
├── eval/           Golden dataset, LLM judge, tier comparison
├── tools/          Musical tool implementations (session, track, MIDI)
├── domains/        Musical domain definitions and sub-domain logic
├── scripts/        CLI tools: eval, ingest, tier comparison
├── tests/          2168 deterministic tests (no network, no flaky)
├── ARCHITECTURE.md Module inventory + OpenDock convergence table
└── compose.yml     pgvector + Redis infrastructure
```

---

## Development

```bash
# Lint
ruff check . && ruff format --check .

# Format
ruff format .

# Tests (all, no network)
pytest -q

# Tests (specific module)
pytest -q tests/test_task_router.py

# PR workflow
# branch → implement → lint + test → PR → status checks → review → merge
```

All new features require:
1. Tests in `tests/` (deterministic, no network)
2. Type hints everywhere
3. Docstrings on all public functions
4. Passing `ruff check` before PR

---

## Knowledge Base

| Source | Chunks | Domain |
|--------|--------|--------|
| Pete Tong Academy (YouTube) | ~9,835 | DJing, live performance, organic house |
| Bob Katz — Mastering Audio | 568 | Mastering, mixing |
| La Masterización | 806 | Mastering (Spanish) |
| Schachter-Aldwell — Harmony | 834 | Music theory |
| **Total** | **~12,043** | |

---

## Status

**Week 10 — Production-ready.** All 10 weeks of the roadmap implemented:

| Week | Feature |
|------|---------|
| 1 | Chunking, text extraction, ingestion pipeline |
| 2 | Embeddings, pgvector, `/search` endpoint |
| 3 | `/ask` RAG pipeline with citations |
| 4 | Tool orchestration (session log, track analysis, chord suggest) |
| 5 | Sub-domain search, genre detection, hybrid RRF search |
| 6 | LLM judge evaluation, golden dataset, OCR ingestion |
| 7 | Chaos tests, Prometheus metrics, Redis cache, circuit breakers |
| 8 | Musical memory system (4 types, time decay, auto-extraction) |
| 9 | Multi-model routing (3 tiers, fallback chain, cost tracking) |
| 10 | Architecture documentation, demo, blog post — OpenDock convergence |

---

*Built for OpenDock — an intelligent musical instrument with a cloud brain.*
