# Building the Cloud Brain for an Intelligent Musical Instrument

*How 10 weeks of focused engineering produced a production-grade AI system specialized for music production and live performance.*

---

## The Problem

A musician in the middle of a performance has a question. "What key is this progression in?" "How do I create more tension before the drop?" "What should I practice to improve my live sets?"

They can't stop to Google it. They can't wait for a generic AI to generate a hallucinated answer. They need a brain that knows music — really knows it — and responds in under 2 seconds, grounded in real sources, aware of their personal history, and resilient enough to keep working when the internet disappears.

That brain needed to be built.

---

## The Architecture Decision That Made Everything Else Work

The first week produced a decision that shaped everything: `core/` must stay pure.

Every function in `core/` is deterministic. No database. No network. No filesystem. No timestamps. No environment variables. A function that takes text and returns chunks will always return the same chunks for the same input, no matter where it runs — laptop, Docker container, cloud instance.

This sounds like a constraint. It's actually a superpower.

Pure functions are trivially testable. Pure functions are portable. Pure functions don't break when infrastructure changes. When the embedding provider switches from OpenAI to something local, the chunking logic doesn't care. When the database migrates from local Docker to Supabase, the retrieval ranking doesn't change.

The test suite has 2,168 tests. Zero of them make network calls. Zero of them require a running database. They all run in under 13 seconds.

That's what architectural discipline buys you.

---

## The Knowledge Base

The platform ingests any musical document — PDF, markdown, scanned textbook — and stores it as a searchable vector. The current knowledge base contains 12,043 chunks from four sources:

- **Pete Tong Academy** — 9,835 chunks from YouTube course transcripts covering DJing, live performance, organic house production
- **Bob Katz — Mastering Audio** — 568 chunks from 306 pages on loudness, dynamics, and mastering philosophy
- **La Masterización** — 806 chunks (Spanish) providing bilingual mastering coverage
- **Schachter-Aldwell — Harmony and Voice Leading** — 834 chunks from 626 pages of music theory

Each chunk is tokenized with `tiktoken` (cl100k_base, the same tokenizer as the embedding model), embedded as a 1536-dimensional vector with `text-embedding-3-small`, and stored in pgvector with an HNSW index (m=16, ef_construction=64, cosine similarity).

Why token-based chunking instead of character-based or sentence-based? Because token counts map directly to model context windows. A chunk of 512 tokens is always 512 tokens, regardless of the language or the punctuation density. There's no mismatch between what the chunker produces and what the embedding model consumes.

---

## The Retrieval Pipeline

When a musician asks "How do I sidechain a kick with a bass?", the platform doesn't just run a vector search. It runs a 9-step pipeline:

**1. Query Expansion** — Intent detection identifies this as a `mixing` query. The query is expanded with domain terminology: "sidechain compression kick bass ducking threshold attack release". More specific queries retrieve more relevant chunks.

**2. Embedding** — The expanded query becomes a 1536-dimensional vector. This step is circuit-breaker protected: after 3 consecutive failures, subsequent calls fail immediately with a 503 instead of waiting for timeouts.

**3. Hybrid Search** — pgvector cosine similarity is combined with BM25 keyword search using Reciprocal Rank Fusion (70% vector, 30% keyword). Neither alone is sufficient: vector search finds semantically similar content, keyword search finds exact terminology matches.

**4. Reranking** — Maximal Marginal Relevance (MMR, λ=0.7) ensures the retrieved chunks are diverse rather than redundant. Pete Tong Academy content gets a 1.25× boost because it's the primary course material. Filename keywords get a 1.20× boost when the intent matches a known domain.

**5. Confidence Check** — If the top similarity score is below 0.58, the request fails with `insufficient_knowledge`. The system refuses to answer rather than hallucinate.

**6. Context Assembly** — Retrieved chunks are formatted as numbered blocks: `[1] (source.pdf, p.42, score: 0.87)\nText...`. Every claim in the answer can be traced to a source.

**7. Generation** — The LLM receives a grounding constraint in its system prompt: "Answer ONLY from the provided context. If the context doesn't contain enough information, say so explicitly." Citations in the format `[1]`, `[2]` are validated after generation — invalid citations trigger a warning.

---

## The Memory System

After ten sessions, the platform knows you. It knows you prefer A minor. It knows you've been working on arrangement skills. It knows you practiced at 122 BPM last Thursday.

This is the musical memory system: four memory types extracted automatically from every query/answer pair.

- `practice` — topics, duration, BPM, key from practice sessions
- `preference` — musical key preferences, genre choices, style decisions
- `achievement` — milestones, breakthroughs, skills acquired
- `context` — session notes, equipment mentions, current projects

Every memory entry has a cosine similarity embedding and a time decay factor: `score = cosine_similarity × e^(-λt)`, where λ=0.1/day and t is days since the memory was created.

Recent sessions rank higher than old ones. A preference from last week matters more than one from three months ago. Memories below a 0.35 trigger threshold are silenced — not relevant enough to inject into the current query.

The memory store lives in SQLite locally (WAL mode, thread-safe). No cloud dependency. The instrument remembers you even when offline.

---

## Multi-Model Routing

Not every question deserves the same AI.

"What is the relative major of A minor?" — this is a factual lookup. It should cost $0.000012 (gpt-4o-mini) not $0.00025 (gpt-4o). The answer is the same either way.

"Suggest a 2-week practice plan for improving my live performance based on my recent sessions" — this is creative reasoning. It needs the more capable model. Cost is justified.

"Detect the BPM of the track playing right now" — this is realtime. It should work offline, cross-provider, with Anthropic's claude-haiku as a fallback if OpenAI is unavailable.

The classifier uses 45 regex signals across three categories:

```
factual:  "what is", "how does", "define", "what bpm", "what key"
creative: "analyze", "suggest", "improve", "based on my sessions", "2-week"
realtime: "right now", "real-time", "currently", "while I'm playing"
```

Confidence = `n / (n + 1)` — asymptotic toward 1.0. Zero matches defaults to factual (safest, cheapest).

The routing saves approximately 56% on API costs compared to always using gpt-4o, based on an observed distribution of 60% factual / 35% creative / 5% realtime queries.

Each tier has a fallback chain:
- factual: fast → local → standard (never spend on gpt-4o for a lookup)
- creative: standard → fast → local (quality first)
- realtime: local → fast → standard (Anthropic first for cross-provider redundancy)

If OpenAI goes down entirely, realtime queries fall back to claude-haiku. The instrument keeps answering.

---

## Resilience

A musical instrument cannot crash. The platform is designed for this.

**Circuit Breakers** — Three consecutive LLM failures open the circuit for 30 seconds. Subsequent calls fail in under 1ms instead of waiting 30 seconds for timeouts. The instrument never freezes.

**Degraded Mode** — When the LLM is unavailable, the platform returns raw knowledge base excerpts directly. No generation, no citations, but real content from real sources. "Here's what I found" is always better than "Server Error."

**Response Cache** — Redis caches answers by (query_hash, top_k, threshold). Identical queries return in under 5ms from cache. Cache is invalidated when a source document is re-ingested.

**Rate Limiting** — Sliding window 30 requests/minute per session. Prevents runaway loops from broken client code.

**Chaos Test Suite** — 24 tests specifically for failure scenarios: database down → 503, LLM timeout → degraded 200, Redis down → fail-open (cache misses, not errors).

---

## The MCP Bridge

All of this intelligence needs to reach the hardware. That's what the MCP (Model Context Protocol) server does.

The musical_mcp package exposes every platform capability as an MCP tool via stdin/stdout. Hardware or AI agents connect once and get access to the entire system:

- `search_production_knowledge` — full RAG pipeline over the knowledge base
- `log_practice_session` — write to the memory system
- `analyze_track` — extract BPM, key, energy from audio
- `suggest_chord_progression` — generate musically coherent progressions
- `ableton_insert_chords` — write directly to Ableton's piano roll via OSC

The transport layer is stdio — it runs on the instrument's local process without network configuration. The intelligence is cloud, the protocol is local.

---

## The Quality Gate

Nothing ships without passing the golden set.

50 carefully chosen queries across 6 musical sub-domains plus 10 adversarial hallucination triggers. A GPT-4o judge evaluates each answer for factual accuracy, source quality, and citation correctness.

Current baseline:
- Musical queries: 13/15 = 87%
- Hallucination refusal: 10/10 = 100%

The 100% adversarial refusal rate is the number that matters most. When a musician asks about their plumbing, the platform says "I don't have knowledge about that." When asked about a topic not in the knowledge base, it raises `insufficient_knowledge` rather than inventing an answer.

A brain that sometimes hallucinates is worse than no brain. The quality gate enforces this.

---

## What's Next

Ten weeks of engineering produced:
- 2,168 deterministic tests
- 12,043 chunks of grounded musical knowledge
- 7 production modules (RAG, memory, routing, tools, MCP, infrastructure, eval)
- A platform that routes queries, remembers musicians, degrades gracefully, and measures itself

The architecture is complete. The protocols are established. The quality is verified.

What remains is physical.

The platform is OpenDock's cloud brain. When the hardware connects — instrument operating system, embedded process, MCP stdio transport — every capability described here becomes available to the musician in real time. The same patterns, the same protocols, the same data structures.

The next step is connecting the brain to an instrument.

---

*The platform is open source. The full codebase, test suite, evaluation framework, and architecture documentation are in the repository. Every architectural decision is documented in the decision log.*

*Built over 10 weeks. 2,168 tests. 12,043 knowledge chunks. One goal: a musical instrument that actually understands music.*
