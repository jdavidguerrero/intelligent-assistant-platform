"""
MCP Musical Intelligence — transport configuration and logging setup.

Responsibilities:
    - Configure structured logging to stderr (NEVER stdout — corrupts stdio transport)
    - Provide transport factory: stdio (local) vs SSE (future cloud/DAW)
    - Document the stdio ↔ SSE boundary for OpenDock edge/cloud split

Transport decision matrix:
    ┌─────────────────────┬──────────────────────────────────┐
    │ Context             │ Transport                        │
    ├─────────────────────┼──────────────────────────────────┤
    │ Local laptop/Ableton│ stdio (in-process, zero latency) │
    │ Cloud / OpenDock    │ HTTP+SSE (cross-process, async)  │
    │ Testing             │ stdio (same process, mocked)     │
    └─────────────────────┴──────────────────────────────────┘

Why stdio for local?
    - Zero latency: no network round-trip
    - No port conflicts with DAW software
    - Direct process pipe: Claude Desktop ↔ server
    - OS handles buffering and flow control

Why SSE for cloud?
    - Stateless HTTP: load balancers, autoscaling
    - Server-sent events: push model for real-time musical events
    - OpenDock edge (Teensy/ESP32) can POST over cellular/WiFi
    - Reconnect handling built into SSE protocol
"""

from __future__ import annotations

import logging
import sys
from typing import Literal

TransportMode = Literal["stdio", "sse"]

# ---------------------------------------------------------------------------
# Logging — must go to stderr, NEVER stdout
# ---------------------------------------------------------------------------

# MCP stdio transport uses stdout exclusively for JSON-RPC messages.
# Any print() or logging to stdout corrupts the protocol stream.
# All diagnostic output must go to stderr.

_LOG_FORMAT = "%(asctime)s.%(msecs)03d " "[%(name)s] %(levelname)s " "%(message)s"
_LOG_DATE_FORMAT = "%H:%M:%S"


def configure_logging(level: int = logging.INFO) -> None:
    """
    Configure root logger to write structured output to stderr.

    Must be called BEFORE the MCP server starts to ensure no
    accidental stdout writes corrupt the stdio transport.

    Args:
        level: Python logging level (default: INFO)
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Silence noisy third-party loggers that write INFO spam
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("librosa").setLevel(logging.WARNING)
    logging.getLogger("numba").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Transport selection
# ---------------------------------------------------------------------------


def get_transport_mode() -> TransportMode:
    """
    Determine the active transport mode from environment.

    Reads MCP_TRANSPORT env var:
        "sse"   → HTTP + Server-Sent Events (future cloud/OpenDock)
        default → "stdio" (local laptop, Claude Desktop)

    Returns:
        "stdio" or "sse"
    """
    import os

    mode = os.getenv("MCP_TRANSPORT", "stdio").lower().strip()
    if mode not in ("stdio", "sse"):
        logging.getLogger(__name__).warning(
            "Unknown MCP_TRANSPORT=%r — falling back to stdio", mode
        )
        return "stdio"
    return mode  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Future SSE integration path (NOT built — documented for OpenDock Phase 2)
# ---------------------------------------------------------------------------
#
# When OpenDock edge hardware goes live, the server will expose an SSE endpoint:
#
#   POST /tools/call       — invoke a musical tool
#   GET  /events           — subscribe to server-push events (practice reminders, etc.)
#   GET  /resources/{uri}  — read a musical resource
#
# Edge (Teensy/ESP32) calls:
#   - analyze_track (BPM/key from MIDI clock or audio tap)
#   - suggest_compatible_tracks (real-time harmonic mixing)
#   - log_practice_session (session start/end via hardware button)
#
# Cloud-only calls:
#   - search_by_genre (requires pgvector / full knowledge base)
#   - suggest_chord_progression (requires chord theory engine)
#   - generate_midi_pattern (compute-heavy, not edge-appropriate)
#
# The split is:
#   Edge  → low-latency, offline-capable, hardware I/O
#   Cloud → knowledge-intensive, generative, stateful history
#
# Transport change: set MCP_TRANSPORT=sse + provide MCP_HOST / MCP_PORT env vars.
