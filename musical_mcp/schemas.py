"""
MCP Musical Intelligence — shared schemas, URI constants, and log types.

Defines:
    - URI prefix constants for MCP resources
    - StructuredLog dataclass for correlation-ID-aware logging
    - Musical domain constants (genres, keys, categories)

Pure module — no I/O, no side effects.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Resource URI prefixes
# ---------------------------------------------------------------------------

# All MCP resource URIs follow the pattern:
#   {PREFIX}/{identifier}
# This makes them predictable and easy to route in handlers.

URI_PRACTICE_LOGS = "music://practice-logs"
URI_SESSION_NOTES = "music://session-notes"
URI_KB_METADATA = "music://knowledge-base/metadata"
URI_SETLIST = "music://setlist"

# ---------------------------------------------------------------------------
# Musical domain constants
# ---------------------------------------------------------------------------

# Supported genres for search_by_genre and chord suggestions
SUPPORTED_GENRES: frozenset[str] = frozenset(
    {
        "organic house",
        "melodic house",
        "afro house",
        "deep house",
        "minimal techno",
        "techno",
        "progressive house",
        "melodic techno",
        "ambient",
        "downtempo",
    }
)

# Note categories for session notes
NOTE_CATEGORIES: frozenset[str] = frozenset(
    {"discovery", "problem", "idea", "reference", "next_steps"}
)

# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------


@dataclass
class McpCallLog:
    """
    Structured log record for a single MCP tool/resource/prompt call.

    Every MCP call produces exactly one McpCallLog at completion.
    Correlation IDs allow tracing full request chains across tools.

    Attributes:
        call_id:     Unique UUID for this call (auto-generated)
        tool_name:   Name of the tool, resource, or prompt invoked
        inputs:      Sanitized copy of the input parameters
        outputs:     Summary of the output (NOT the full payload — avoid log bloat)
        success:     Whether the call completed without error
        error:       Error message if success=False, else None
        latency_ms:  Wall-clock duration in milliseconds
        timestamp:   Unix timestamp at call start
        correlation_id: Optional parent ID for chained calls
    """

    tool_name: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    success: bool
    latency_ms: float
    timestamp: float = field(default_factory=time.time)
    call_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    error: str | None = None
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a loggable dict (suitable for structured log sinks)."""
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "success": self.success,
            "error": self.error,
            "latency_ms": round(self.latency_ms, 2),
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
        }

    def __str__(self) -> str:
        status = "OK" if self.success else f"ERR:{self.error}"
        corr = f" corr={self.correlation_id}" if self.correlation_id else ""
        return f"[{self.call_id}] {self.tool_name} " f"{status} {self.latency_ms:.1f}ms{corr}"


# ---------------------------------------------------------------------------
# Helper: build McpCallLog from a completed call
# ---------------------------------------------------------------------------


def make_call_log(
    tool_name: str,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    latency_ms: float,
    success: bool = True,
    error: str | None = None,
    correlation_id: str | None = None,
) -> McpCallLog:
    """
    Build a McpCallLog from call metadata.

    Pure factory function — no I/O.

    Args:
        tool_name:      Name of the MCP tool/resource/prompt
        inputs:         Sanitized input parameters (no secrets)
        outputs:        Output summary fields
        latency_ms:     Elapsed wall-clock time in ms
        success:        Whether the call succeeded
        error:          Error message on failure
        correlation_id: Optional parent correlation ID

    Returns:
        Populated McpCallLog instance
    """
    return McpCallLog(
        tool_name=tool_name,
        inputs=inputs,
        outputs=outputs,
        success=success,
        error=error,
        latency_ms=latency_ms,
        correlation_id=correlation_id,
    )
