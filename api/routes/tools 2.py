"""api/routes/tools.py — Direct tool invocation endpoint.

POST /tools/call  — Execute any registered MusicalTool by name with params dict.
GET  /tools/list  — List all registered tools with their parameter schemas.

Thin HTTP boundary: no business logic.  Delegates to the global ToolRegistry
singleton defined in tools/registry.py.  All tool errors are encoded in the
response body (success=False, error=str) — this endpoint never returns 500.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tools.registry import get_registry

router = APIRouter(prefix="/tools", tags=["tools"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ToolCallRequest(BaseModel):
    """POST /tools/call request body."""

    name: str
    """Tool name as returned by ToolRegistry.list_tools()['name']."""

    params: dict[str, Any] = {}
    """Keyword arguments forwarded to the tool's __call__ method."""


class ToolCallResponse(BaseModel):
    """POST /tools/call response body."""

    success: bool
    data: Any = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/call", response_model=ToolCallResponse)
def call_tool(request: ToolCallRequest) -> ToolCallResponse:
    """Execute a registered MusicalTool by name.

    Finds the tool in the global registry, validates its parameters, and
    executes it.  Returns the ToolResult as JSON.  Never raises 500 —
    all errors are encoded in the response body with ``success=False``.

    Args:
        request: Tool name and params dict.

    Returns:
        ToolCallResponse — mirrors the ToolResult fields.

    Raises:
        HTTPException(404): Tool not registered.
    """
    registry = get_registry()
    tool = registry.get(request.name)
    if tool is None:
        available = [t["name"] for t in registry.list_tools()]
        raise HTTPException(
            status_code=404,
            detail=(
                f"Tool '{request.name}' not found in registry. "
                f"Available tools: {available}"
            ),
        )

    result = tool(**request.params)
    return ToolCallResponse(
        success=result.success,
        data=result.data,
        error=result.error,
        metadata=result.metadata,
    )


@router.get("/list")
def list_tools() -> list[dict[str, Any]]:
    """List all registered tools with their parameter schemas.

    Returns:
        List of tool dicts — each has ``name``, ``description``,
        and ``parameters`` (list of param dicts).
    """
    return get_registry().list_tools()
