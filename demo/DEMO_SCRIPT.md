# 5-Minute Demo Script — Musical Intelligence Platform

**Premise**: "I'm going to show you a production AI system for music production.
Every query you'll see is the kind of question a musician asks while working.
By the end, you'll see how this becomes OpenDock's cloud brain."

**Setup**: API running on localhost:8000. Terminal + browser open. Internet on.

---

## ⏱ 0:00 — Hook (20 seconds)

> "You're a DJ playing live. Your set is building. You want to add tension before the drop.
> You reach for your instrument and ask it a question. Here's what happens."

```bash
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How do I create tension before a drop in organic house?",
    "use_tools": false,
    "top_k": 4
  }' | python -m json.tool
```

**What to show**: Answer with citations [1][2][3]. Highlight:
- `sources[0].source_name` — "Pete Tong Academy" or "Bob Katz"
- `usage.generation_ms` < 2000
- `usage.model` — which model generated it

> "Grounded answer. Real sources. Under 2 seconds."

---

## ⏱ 0:45 — Tool Orchestration (1 minute)

> "Now I've finished a 2-hour arrangement session. The instrument should know about that."

```bash
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Log that I just did a 2-hour arrangement session in A minor at 122 BPM",
    "use_tools": true,
    "session_id": "opendock-demo"
  }' | python -m json.tool
```

**What to show**:
- `mode: "tool"` in response
- `tool_calls[0].tool_name: "log_practice_session"`
- `tool_calls[0].success: true`
- Natural language synthesis: "✓ Logged your 2-hour arrangement session..."

> "Tool executed. Session logged. The instrument just learned something about me."

```bash
# Verify the memory was stored
curl -s "http://localhost:8000/memory?session_id=opendock-demo" | python -m json.tool
```

**What to show**: Memory entries with `memory_type: "practice"`, `content` describing the session.

---

## ⏱ 1:45 — Memory Recall (45 seconds)

> "Now I ask a question that should use what it learned."

```bash
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What should I practice next to improve my arrangement skills?",
    "use_tools": false,
    "session_id": "opendock-demo"
  }' | python -m json.tool
```

**What to show**: The answer references the previous session — "Based on your recent arrangement session..."
- If memory injection worked: the system prompt included the memory block
- If not visible in response: show the system knows about "A minor at 122 BPM"

> "The instrument remembers your sessions. It's not generic advice — it's personal."

---

## ⏱ 2:30 — Multi-Model Routing (45 seconds)

> "Not every question needs the same AI. A simple lookup doesn't need GPT-4."

```bash
USE_ROUTING=true curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the relative major of A minor?",
    "use_tools": false
  }' | python -m json.tool
```

**What to show**:
- `usage.tier: "fast"` — gpt-4o-mini used
- `usage.model: "gpt-4o-mini"`
- `usage.cost_usd: 0.000012` — tiny cost
- Response time < 800ms

```bash
# Now a creative query — should route to standard tier
USE_ROUTING=true curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Suggest a 2-week practice plan for improving live performance skills",
    "use_tools": false
  }' | python -m json.tool
```

**What to show**:
- `usage.tier: "standard"` — gpt-4o used
- `usage.cost_usd` is higher
- Answer is more detailed

> "Factual lookups: fast model, 3¢ per 1000 queries.
> Creative reasoning: powerful model. 56% cost reduction overall."

---

## ⏱ 3:15 — Offline Mode (30 seconds)

> "What happens when OpenAI goes down? The instrument should still help."

```bash
# Simulate circuit breaker tripped — force degraded mode
# (Stop the API briefly, or show the degraded response)
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How do I compress a kick drum?",
    "use_tools": false,
    "confidence_threshold": 0.3
  }' | python -m json.tool
```

> "In degraded mode (mode='degraded'), the musician gets raw excerpts directly from the
> knowledge base. No LLM. No blank screen. 'Here's what I found.'"

**What to show** (or describe): `mode: "degraded"`, answer contains raw text excerpts, `warnings: ["llm_unavailable"]`.

---

## ⏱ 3:45 — Evaluation Dashboard (30 seconds)

> "How do we know this system is actually accurate? We measure it."

```bash
python scripts/run_eval.py --max-queries 10
```

**What to show**: Evaluation output with:
- Per-sub-domain pass rates (mastering, mixing, sound design...)
- `hallucination_refusal: 10/10 = 100%`
- Overall quality score

> "50 golden questions verified against real course content.
> LLM judge evaluates each answer. Nothing ships if this score drops."

---

## ⏱ 4:15 — Architecture Slide (45 seconds)

Switch to browser or diagram. Show the Mermaid architecture diagram from `docs/architecture_diagram.md`.

> "Here's what you just saw:"

Point to each module:
1. **Query** → `POST /ask` → tool routing → RAG pipeline
2. **Knowledge** → pgvector, 12,043 chunks, Pete Tong + Bob Katz + Harmony
3. **Memory** → SQLite, 4 memory types, time decay
4. **Routing** → 3 model tiers, fallback chain, cost tracking
5. **MCP** → the bridge between hardware and every capability you just saw

> "Every module you saw corresponds to one capability that OpenDock needs.
> The patterns are established. The protocols exist.
> What remains is hardware — connecting this brain to an instrument."

---

## ⏱ 5:00 — Close

> "This is OpenDock's cloud brain.
> A musician playing live can ask it anything.
> It answers from real sources, remembers their sessions, routes to the right model,
> and degrades gracefully when the internet disappears.
>
> The next step is physical."

---

## Setup Checklist (Before Demo)

- [ ] `docker compose up -d` — postgres + redis running
- [ ] `uvicorn api.main:app --reload --port 8000` — API running
- [ ] `curl http://localhost:8000/health` returns `{"status": "ok"}`
- [ ] At least 100 chunks in the database (run ingestion first if needed)
- [ ] `session_id: "opendock-demo"` cleared from memory store (fresh demo)
- [ ] Terminal font size ≥ 18pt for visibility
- [ ] `python -m json.tool` installed (stdlib, always available)

## Fallback: If Live Queries Are Slow

Use pre-recorded responses. The key moments to show:

1. `sources[N].source_name` — "Pete Tong..." (proves grounding)
2. `mode: "tool"` with `tool_calls` (proves tool execution)
3. `usage.tier: "fast"` vs `usage.tier: "standard"` (proves routing)
4. `mode: "degraded"` (proves offline resilience)
5. Eval pass rate ≥ 85% (proves quality)

## Timing Guide

| Segment | Time | Key Visual |
|---------|------|-----------|
| Hook — grounded RAG query | 0:00–0:45 | Sources array with Pete Tong |
| Tool execution + memory store | 0:45–1:45 | `mode: "tool"`, memory entries |
| Memory recall | 1:45–2:30 | Personalized answer |
| Multi-model routing | 2:30–3:15 | `tier: "fast"` vs `tier: "standard"` |
| Offline degradation | 3:15–3:45 | `mode: "degraded"` |
| Evaluation dashboard | 3:45–4:15 | Pass rates per sub-domain |
| Architecture diagram | 4:15–5:00 | Full convergence diagram |
