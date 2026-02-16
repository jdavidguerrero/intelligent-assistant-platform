---
command: refactor
description: Invoke the Refactorer agent for safe structural improvements.
---

Invoke the Refactorer agent.

If $ARGUMENTS is provided, focus the refactor on that target (file, module, or concern).
Otherwise, scan for structural issues: naming collisions, wrong-direction imports, god modules.

Follow the refactorer procedure:
1. Identify the specific structural problem.
2. Verify tests pass before changes (`pytest -q`).
3. Make one change per concern.
4. Run tests again — must stay green.
5. Verify import directions are correct.
6. Produce output in the refactorer format.
End with: REFACTOR COMPLETE or NEEDS FOLLOW-UP.
