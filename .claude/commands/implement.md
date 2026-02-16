---
command: implement
description: Invoke the Implementer agent to build a feature or module.
---

Invoke the Implementer agent.

If $ARGUMENTS is provided, use it as the task description.
Otherwise, ask the user what to implement.

Follow the implementer procedure:
1. Restate the task and ship criteria.
2. Propose a plan (max 6 bullets).
3. Implement with minimal surface area.
4. Validate with `ruff check .` and `pytest -q`.
5. Produce output in the implementer format.
