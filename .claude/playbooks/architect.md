# Playbook: Architect Review

Goal: keep architecture clean while shipping quickly.

When invoked:
1) Read repo layout and key files relevant to current work.
2) Identify boundary violations (core importing db/api, side effects in pure modules).
3) Check naming collisions (Chunk vs ChunkRecord etc).
4) Verify integration path for next step (ingestion → chunking → embeddings → storage).
5) Recommend only changes that reduce friction within the next 1–2 days.

Week 1 constraints:
- No PDF parsing yet.
- Chunking stays token-based.
- Tests must validate token invariants.
- Minimal config/typing improvements allowed only if they remove future blockers.

Must flag (blocking):
- Leaky boundaries
- Confusing naming collisions
- No path to ingestion integration
- Un-testable design

Nice-to-have:
- core/types.py to separate pure data vs DB records
- core/text.py for pure text normalization
- ChunkingConfig dataclass if parameter sprawl starts