"""core/ableton — Pure Ableton Live session model.

This package contains zero I/O, zero network calls, zero filesystem access.
All types, device maps, query helpers, and command generators are
deterministic functions of their inputs.

Ingestion-layer I/O (WebSocket to ALS Listener) lives in ingestion/ableton_bridge.py.
"""
