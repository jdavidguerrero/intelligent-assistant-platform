# Architecture — Musical Intelligence Platform

**OpenDock's Cloud Brain: a production-grade AI system specialized for music production and live performance intelligence.**

Every module in this platform maps directly to a capability that an intelligent musical instrument needs.
This document is the connective tissue between the code and the vision.

---

## 1. System Purpose

A musician playing OpenDock needs a cloud brain that can:

| Question the instrument asks | Module that answers it |
|------------------------------|----------------------|
| "How do I create tension before a drop?" | RAG pipeline → grounded knowledge retrieval |
| "What BPM am I playing right now?" | Realtime tier (claude-haiku, offline-capable) |
| "Suggest a practice plan based on my sessions" | Memory system → personalized response |
| "Log this 2-hour arrangement session" | Tool orchestration → session persistence |
| "I can't reach the cloud right now" | Circuit breaker → degraded mode (raw excerpts) |
| "Show me what you know about organic house" | Genre recipes + sub-domain search |

---

## 2. Module Inventory

### `core/` — Pure Logic (No Side Effects)

The deterministic kernel. Every function here is testable without infrastructure.

| Module | Responsibility | OpenDock Function |
|--------|---------------|-------------------|
| `core/routing/classifier.py` | Classify query as factual / creative / realtime using regex signals | Decides which AI brain handles each request |
| `core/routing/tiers.py` | Define TIER_FAST, TIER_STANDARD, TIER_LOCAL with temp/token config | Maps query type to model capability |
| `core/routing/costs.py` | Calculate USD cost per (model, input_tokens, output_tokens) | Cost observability — know what each interaction costs |
| `core/routing/types.py` | Frozen dataclasses: TaskType, ModelTier, ClassificationResult | Shared types across routing layer |
| `core/memory/types.py` | MemoryEntry, MemoryType (practice, preference, achievement, context) | Musician profile data structures |
| `core/memory/decay.py` | Exponential time decay: `cosine × e^(-λt)` | Memories fade — recent sessions matter more |
| `core/memory/format.py` | Format memory block for injection into system prompt | How the instrument "remembers" you |
| `core/rag/prompts.py` | Build system + user prompts with grounding constraints | The instruction set for every AI response |
| `core/rag/context.py` | Format retrieved chunks into numbered context block [1]...[N] | How knowledge becomes context |
| `core/rag/citations.py` | Extract and validate [1], [2] citation patterns | Ensures answers are grounded, not hallucinated |
| `core/rag/degraded.py` | Build raw-excerpt response when LLM is unavailable | Offline fallback — the brain still helps |
| `core/query_expansion.py` | Expand musical queries with domain-specific terminology | Better search recall from natural language |
| `core/sub_domain_detector.py` | Detect active musical sub-domains (mastering, sound design, etc.) | Namespace search to relevant corpus |
| `core/genre_detector.py` | Detect musical genre from query → load style recipe | Inject organic house / afrobeat context |
| `core/chunking.py` | Token-based text splitting with tiktoken (cl100k_base) | Split any document into searchable units |
| `core/text.py` | Normalize markdown, extract clean text | Pre-process before embedding |
| `core/midi.py` | MIDI event generation and pattern structures | Generate musical sequences |
| `core/generation/base.py` | GenerationProvider protocol + GenerationRequest/Response | Contract every AI model must implement |
| `core/embeddings/base.py` | EmbeddingProvider protocol | Contract every embedding model must implement |

### `ingestion/` — Side Effects Layer

Talks to files, APIs, databases. Orchestrates the pure `core/` functions.

| Module | Responsibility | OpenDock Function |
|--------|---------------|-------------------|
| `ingestion/router.py` | TaskRouter: 3 providers + fallback chains | Route to the right model with automatic recovery |
| `ingestion/generation.py` | OpenAIGenerationProvider + AnthropicGenerationProvider | Multi-provider AI text generation |
| `ingestion/embeddings.py` | OpenAIEmbeddingProvider (text-embedding-3-small, 1536d) | Convert text to vectors for similarity search |
| `ingestion/memory_store.py` | SQLite-backed MemoryStore (WAL mode, local-first) | Persist musician profile across sessions |
| `ingestion/memory_extractor.py` | Rule-based + LLM extraction of memorable facts | Auto-learn from every query/answer pair |
| `ingestion/ingest.py` | CLI: load → chunk → embed → persist to pgvector | Pipeline to ingest any musical document |
| `ingestion/ingest_ocr.py` | Google Vision OCR + pdf2image for scanned books | Ingest physical textbooks (Bob Katz, etc.) |
| `ingestion/loaders.py` | Load .md, .txt, .pdf documents | The front door for new knowledge |
| `ingestion/tagger.py` | Tag chunks with sub-domain metadata | Index chunks so search can be namespaced |
| `ingestion/recipes.py` | Load genre-specific production recipes from YAML | Style context for genre-aware answers |

### `db/` — Persistence Layer

SQLAlchemy + pgvector. The long-term memory of the platform.

| Module | Responsibility | OpenDock Function |
|--------|---------------|-------------------|
| `db/models.py` | ChunkRecord (text, embedding Vector(1536), source, page, sub_domain) | Every knowledge chunk with HNSW index |
| `db/search.py` | `search_chunks()` + `hybrid_search()` (vector + BM25 keyword RRF) | Find the most relevant knowledge for any query |
| `db/rerank.py` | MMR reranking with course_boost=1.25, filename_boost=1.20 | Surface the best diverse set of sources |
| `db/session.py` | SQLAlchemy SessionLocal factory | Database connection management |

### `api/` — HTTP Boundary

FastAPI thin controllers. No business logic — only wiring.

| Module | Responsibility | OpenDock Function |
|--------|---------------|-------------------|
| `api/routes/ask.py` | `POST /ask` — 9-step RAG pipeline (expand→embed→search→rerank→memory→classify→generate→cite) | The main intelligence endpoint |
| `api/routes/search.py` | `POST /search` — raw vector search | Direct retrieval without generation |
| `api/routes/memory.py` | `GET/POST/DELETE /memory` — CRUD for musician profile | Session history management API |
| `api/deps.py` | Singleton providers (embedder, generator, router, memory, cache, circuit breakers) | One instance per server process |

### `musical_mcp/` — Edge Protocol

MCP (Model Context Protocol) server — the bridge between the instrument and the cloud brain.

| Module | Responsibility | OpenDock Function |
|--------|---------------|-------------------|
| `musical_mcp/server.py` | MCP server registering all musical tools | Hardware-readable protocol interface |
| `musical_mcp/handlers.py` | Handler functions: RAG query, session log, track analysis, chord suggest | Each handler = one instrument capability |
| `musical_mcp/ableton.py` | OSC bridge to Ableton Live (localhost:11001) | Insert chords directly into the piano roll |
| `musical_mcp/transport.py` | StdioServerTransport — works over stdin/stdout | Runs on the instrument's local process |
| `musical_mcp/schemas.py` | Pydantic models for tool inputs/outputs | Typed contract for hardware calls |

### `infrastructure/` — Production Reliability

The brain stays up even when third-party services fail.

| Module | Responsibility | OpenDock Function |
|--------|---------------|-------------------|
| `infrastructure/circuit_breaker.py` | Trip after 3 failures, reset after 30s | If OpenAI goes down, degrade gracefully |
| `infrastructure/cache.py` | Redis response cache (24h TTL, source-key invalidation) | Sub-100ms on repeated queries |
| `infrastructure/rate_limiter.py` | Sliding window 30 req/min per session | Protect from runaway loops |
| `infrastructure/metrics.py` | Prometheus counters: ask latency, cache hit, tier, subdomain | Observability for production deployment |
| `infrastructure/retry.py` | Exponential backoff with jitter | Transient API failures handled automatically |

### `eval/` — Quality Assurance

The quality gate. Nothing ships without passing the golden set.

| Module | Responsibility | OpenDock Function |
|--------|---------------|-------------------|
| `eval/dataset.py` | 50 golden Q&A pairs: 6 sub-domains + adversarial | Ground truth for the musical knowledge base |
| `eval/runner.py` | End-to-end eval runner (real /ask calls or mocked) | Regression protection on every deploy |
| `eval/judge.py` | GPT-4o LLM judge: factual accuracy + citation quality | Automated QA without human review |
| `eval/tier_comparison.py` | Compare quality + cost across 3 model tiers | Validate routing efficiency analytically |
| `eval/retrieval_metrics.py` | NDCG@5, MRR, precision/recall for search quality | Search quality measurement |
| `eval/regression.py` | Detect score regressions vs baseline | Alert before shipping a broken model |
| `eval/report.py` | Generate markdown evaluation reports | Shareable evaluation artifacts |

---

## 3. Data Flow — Every /ask Request

```
                              ┌─────────────────────────────────────────────┐
                              │              POST /ask                       │
                              │   { query: str, session_id: str, ... }      │
                              └─────────────────┬───────────────────────────┘
                                                │
                              ┌─────────────────▼───────────────────────────┐
                              │   Step 0: Tool Router (use_tools=True)       │
                              │   ToolRouter.route(query)                    │
                              │   ├── intent matched → execute tool          │
                              │   │   └── LLM synthesis → mode="tool"       │
                              │   └── no match → continue RAG               │
                              └─────────────────┬───────────────────────────┘
                                                │
                              ┌─────────────────▼───────────────────────────┐
                              │   Step 1: Query Expansion                    │
                              │   detect_intents() + detect_sub_domains()    │
                              │   + detect_genre() + expand_query()          │
                              │   Output: expanded_query, active_sub_domains │
                              │           genre_result, query_terms          │
                              └─────────────────┬───────────────────────────┘
                                                │
                              ┌─────────────────▼───────────────────────────┐
                              │   Step 2: Embed (circuit-breaker protected)  │
                              │   OpenAIEmbeddingProvider.embed_texts()      │
                              │   text-embedding-3-small → [1536] float      │
                              └─────────────────┬───────────────────────────┘
                                                │
                              ┌─────────────────▼───────────────────────────┐
                              │   Step 3: Vector Search                      │
                              │   hybrid_search() = pgvector cosine          │
                              │   + BM25 keyword RRF fusion (70/30)          │
                              │   HNSW index m=16, ef_construction=64        │
                              └─────────────────┬───────────────────────────┘
                                                │
                              ┌─────────────────▼───────────────────────────┐
                              │   Step 4: Rerank (MMR + course boost)        │
                              │   rerank_results():                          │
                              │   - MMR diversity λ=0.7                     │
                              │   - course_boost=1.25 (Pete Tong priority)  │
                              │   - filename_boost=1.20 (domain keywords)   │
                              └─────────────────┬───────────────────────────┘
                                                │
                              ┌─────────────────▼───────────────────────────┐
                              │   Step 5: Confidence Check                   │
                              │   max_score < threshold → 422                │
                              │   (insufficient_knowledge)                   │
                              └─────────────────┬───────────────────────────┘
                                                │
                              ┌─────────────────▼───────────────────────────┐
                              │   Step 6: Context Assembly                   │
                              │   format_context_block() → "[1] (source...  │
                              │   build_system_prompt() + build_user_prompt()│
                              └─────────────────┬───────────────────────────┘
                                                │
                              ┌─────────────────▼───────────────────────────┐
                              │   Step 6.5: Memory Retrieval (best-effort)   │
                              │   memory_store.search_relevant()             │
                              │   cosine × e^(-λt) ≥ 0.35 → inject          │
                              │   → "Based on your last session..."          │
                              └─────────────────┬───────────────────────────┘
                                                │
                              ┌─────────────────▼───────────────────────────┐
                              │   Step 6.7: Task Classification (USE_ROUTING)│
                              │   classify_musical_task(query) →            │
                              │   factual → TIER_FAST (gpt-4o-mini)          │
                              │   creative → TIER_STANDARD (gpt-4o)          │
                              │   realtime → TIER_LOCAL (claude-haiku)       │
                              └─────────────────┬───────────────────────────┘
                                                │
                              ┌─────────────────▼───────────────────────────┐
                              │   Step 8: Generate (circuit-breaker / router)│
                              │   TaskRouter.generate_with_decision()        │
                              │   Fallback chain per task type:              │
                              │   factual: fast→local→standard               │
                              │   creative: standard→fast→local              │
                              │   realtime: local→fast→standard              │
                              └─────────────────┬───────────────────────────┘
                                                │
                              ┌─────────────────▼───────────────────────────┐
                              │   Step 9: Citation Validation                │
                              │   extract_citations() → validate_citations() │
                              │   → warn "invalid_citations" if needed       │
                              └─────────────────┬───────────────────────────┘
                                                │
                              ┌─────────────────▼───────────────────────────┐
                              │   Step 9.5: Memory Extraction (best-effort)  │
                              │   extract_memories() → memory_store.save()  │
                              │   Auto-learns from (query, answer) pairs     │
                              └─────────────────┬───────────────────────────┘
                                                │
                              ┌─────────────────▼───────────────────────────┐
                              │   Response: AskResponse                      │
                              │   { answer, sources, citations, warnings,    │
                              │     usage: { tier, cost_usd, model, ms } }  │
                              └─────────────────────────────────────────────┘
```

---

## 4. OpenDock Convergence Table

Every module in this platform maps to a concrete capability of the OpenDock instrument.

| Platform Module | OpenDock Capability | Musical Use Case | Latency |
|-----------------|--------------------|--------------------|---------|
| `core/routing/classifier.py` | Instrument intelligence router | Decide: lookup vs creative vs offline | <10ms |
| `core/routing/tiers.py` + `ingestion/router.py` | Multi-brain model selection | Fast for scales, powerful for arrangement advice | <50ms |
| `core/rag/` + `db/search.py` | Musical knowledge retrieval | "How do I layer a kick bass?" | <200ms |
| `ingestion/memory_store.py` + `core/memory/` | Musician profile & session history | "You practiced Am pentatonic last time" | <50ms |
| `ingestion/memory_extractor.py` | Auto-learning from sessions | Build musician model without manual input | background |
| `tools/` + MCP handlers | Instrument action layer | Log session, analyze BPM, insert chords | <500ms |
| `musical_mcp/server.py` | Edge ↔ cloud protocol bridge | Hardware talks to AI over MCP stdio | <50ms |
| `musical_mcp/ableton.py` | DAW integration (OSC) | AI-generated chords appear in piano roll | <100ms |
| `infrastructure/circuit_breaker.py` | Offline-first degradation | Brain still helps when internet is down | <1ms |
| `infrastructure/cache.py` | Response cache (Redis) | Instant answers for repeated queries | <5ms |
| `infrastructure/metrics.py` | Production observability | Monitor what the instrument is asking | async |
| `eval/dataset.py` + `eval/runner.py` | Quality gate | Nothing deploys if musical accuracy drops | CI/CD |
| `ingestion/ingest_ocr.py` | Physical book ingestion | Add any music textbook to the knowledge base | offline |
| `core/genre_detector.py` + recipes | Genre-aware intelligence | Organic house context vs classical harmony | <5ms |

---

## 5. Edge / Cloud Integration Points

```
    OpenDock Hardware                           Cloud Brain
    ─────────────                               ────────────
    ┌────────────────┐                         ┌─────────────────────────┐
    │  Instrument OS │                         │   Musical Intelligence  │
    │  (embedded)    │◄──── MCP stdio ────────►│   Platform (FastAPI)    │
    │                │                         │                         │
    │  musical_mcp/  │  Calls tools over MCP:  │  POST /ask              │
    │  transport.py  │  - search_production_   │  POST /search           │
    │                │    _knowledge           │  POST /memory           │
    │                │  - log_practice_session │  GET  /health           │
    │                │  - analyze_track        │  GET  /metrics          │
    │                │  - suggest_chords       │                         │
    │                │  - ableton_insert_chords│  ┌──────────────────┐  │
    └────────────────┘                         │  │  pgvector        │  │
                                               │  │  12,043 chunks   │  │
    Optional: Local model fallback             │  │  HNSW index      │  │
    ┌────────────────┐                         │  └──────────────────┘  │
    │  Tier 3 (local)│                         │                         │
    │  claude-haiku  │◄──── direct call ──────►│  ┌──────────────────┐  │
    │  (realtime     │      when OpenAI down   │  │  SQLite memory   │  │
    │   queries)     │                         │  │  (local-first)   │  │
    └────────────────┘                         │  └──────────────────┘  │
                                               └─────────────────────────┘
```

**MCP tools exposed to hardware:**

| Tool | Parameters | Returns |
|------|-----------|---------|
| `search_production_knowledge` | `query: str, top_k: int` | Grounded answer + citations |
| `log_practice_session` | `topic, duration_minutes, key_practiced, bpm_practiced` | Session ID + confirmation |
| `create_session_note` | `category, title, content, tags` | Note ID |
| `analyze_track` | `file_path: str` | BPM, key, energy |
| `suggest_chord_progression` | `key, genre, mood, bars` | Chord progression + MIDI notes |
| `suggest_compatible_tracks` | `key, bpm` | Compatible keys (Camelot wheel) |
| `ableton_insert_chords` | `chords, beats_per_chord, velocity, octave` | Chords written to piano roll |

---

## 6. Knowledge Base

| Source | Chunks | Pages | Domain |
|--------|--------|-------|--------|
| Pete Tong Academy courses (YouTube transcripts) | ~9,835 | — | Live performance, DJing, organic house |
| Bob Katz — Mastering Audio | 568 | 306 | Mastering, mixing, loudness |
| La Masterización (Spanish) | 806 | 316 | Mastering (bilingual coverage) |
| Schachter-Aldwell — Harmony & Voice Leading | 834 | 626 | Music theory, harmony |
| **Total** | **~12,043** | **~1,248** | |

Search is namespaced by sub-domain (mastering, sound_design, mixing, arrangement, etc.) with a global fallback if fewer than 3 sub-domain results are found.

---

## 7. Evaluation Baseline (Week 6)

| Metric | Score |
|--------|-------|
| Musical queries (15 golden) | 13/15 = 87% |
| Hallucination refusal (10 adversarial) | 10/10 = 100% |
| Disambiguation queries | 2/3 = 67% |
| Full test suite | 2168 passed, 0 failed, 21 skipped |

**Known gaps**: "prepare stems for DJ set" scores 0.54 (below 0.58 threshold) — insufficient corpus coverage.

---

## 8. Architecture Decisions

Full decision log in `.claude/rules/decision-log.md`. Key decisions:

| Decision | Rationale |
|----------|-----------|
| **DL-001**: `core/` purity boundary | Pure functions are trivially testable and portable across deployment targets |
| **DL-002**: Token-based chunking (tiktoken cl100k_base) | Token counts map directly to model context windows — no mismatch |
| **DL-003**: pgvector + HNSW | Vectors and metadata in one Postgres instance — no sync between two systems |
| **Week 9**: Three-tier model routing | 60% factual / 35% creative / 5% realtime → ~56% cost reduction vs always-gpt-4o |
| **Week 8**: Memory decay (λ=0.1/day) | Recent sessions matter more; old preferences don't pollute new queries |
| **Week 7**: Hybrid search (RRF 70/30) | Vector recall + keyword precision — neither alone is sufficient |

---

## 9. Dependency Rules (Non-Negotiable)

```
api/ → ingestion/ → core/
api/ → db/
ingestion/ → db/
ingestion/ → core/

NEVER: core/ → db/       (purity violation)
NEVER: core/ → api/      (circular)
NEVER: core/ → ingestion/ (circular)
```

All new features must respect this boundary. `core/` imports: stdlib, tiktoken, dataclasses, typing only.

---

## 10. What's Next — Hardware Integration

When this cloud brain connects to OpenDock hardware, the convergence is complete:

1. **Hardware event** → MCP stdio message → `musical_mcp/transport.py`
2. **Tool dispatch** → `musical_mcp/handlers.py` → `POST /ask` or tool call
3. **Intelligence** → RAG + Memory + Routing → grounded musical answer
4. **Action** → OSC to Ableton → notes in the piano roll

The patterns are identical. The protocols are established. The data structures match.
The next step is physical — connecting the hardware process to this server.

---

*Last updated: Week 10 — January 2026*
*Test suite: 2168 passed · Knowledge base: 12,043 chunks · Models: gpt-4o-mini / gpt-4o / claude-haiku-4*
