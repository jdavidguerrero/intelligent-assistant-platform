# Playbook: PR Review

## Goal

Catch correctness issues, boundary violations, and test gaps before merge.

## When to Use

- Before merging any PR
- After addressing review feedback (re-review)

## Procedure

1. **Understand intent** — Read the PR title, description, and branch name. Infer roadmap context.
2. **Get the diff** — Run `git diff main...HEAD`. Also run `git status` and `git log -n 5` if helpful.
3. **Check architecture** — Scan changed files for boundary violations. Trace imports if unclear.
4. **Verify correctness** — Check invariants, edge cases, error handling.
5. **Evaluate tests** — Do they test behavior or implementation? Are invariants covered?
6. **Check naming** — No collisions between `core/` types and `db/` models.
7. **Assess DX** — Docs, comments, error messages, determinism.
8. **Produce review** — Follow the output format defined in `agents/pr-reviewer.md`.

## Common Pitfalls

- Hidden I/O in `core/` (file reads, env vars, `datetime.now()`)
- Tests that pass even when the code is wrong
- New dependencies without justification
- Naming collisions introduced between layers

## Anti-Patterns

- Do not ask for pasted diffs — inspect the repo yourself.
- Do not nitpick style unless it affects correctness.
- Do not hedge on the decision — `APPROVE` or `REQUEST CHANGES`, no middle ground.
