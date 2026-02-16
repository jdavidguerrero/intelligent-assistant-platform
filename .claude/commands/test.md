---
command: test
description: Invoke the Test Guardian agent to audit test coverage and quality.
---

Invoke the Test Guardian agent.

If $ARGUMENTS is provided, focus on that file or module.
Otherwise, scan for recently changed files via `git diff main...HEAD --name-only` and audit their test coverage.

Follow the test guardian checklist:
1. Identify missing coverage for new or changed code.
2. Verify tests validate behavior, not implementation.
3. Check determinism — no time, network, or random without seeds.
4. Flag edge cases: empty input, boundary values, malformed data.
5. Produce output in the test guardian format.
End with: TESTS SUFFICIENT or TESTS NEEDED.
