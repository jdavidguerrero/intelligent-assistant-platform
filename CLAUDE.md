# Intelligent Assistant Platform — Engineering Rules

You are operating inside a production-oriented AI backend.

Core principles:

- Favor clarity over cleverness
- Strong typing is preferred
- Async-first design when possible
- Keep modules decoupled
- Retrieval and embeddings must be swappable
- Avoid hidden side effects
- Write testable code
- Prefer pure functions when possible

Architecture priorities:

1. Retrieval quality > model cleverness
2. Deterministic tools > LLM reasoning
3. Observability is mandatory
4. Latency matters
5. Simplicity scales

Code style:

- Python 3.14+
- Use type hints everywhere
- Prefer dataclasses or pydantic
- Docstrings required for public functions
- Avoid premature abstractions

When proposing changes:

- Explain WHY briefly
- Identify tradeoffs
- Prefer minimal surface area changes