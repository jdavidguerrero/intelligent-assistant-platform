#!/usr/bin/env python3
"""
MCP Server Smoke Test — Day 4 verification script.

Simulates what Claude Desktop does:
    1. Launches musical_mcp.server as a subprocess (stdio transport)
    2. Sends JSON-RPC initialize request
    3. Sends tools/list request
    4. Sends resources/list request
    5. Sends prompts/list request
    6. Sends tools/call for suggest_chord_progression
    7. Verifies each response

Usage:
    python3 scripts/smoke_test_mcp.py

Expected output:
    ✓  initialize — protocol negotiated
    ✓  tools/list — 6 tools registered
    ✓  resources/list — 4 resources registered
    ✓  prompts/list — 2 prompts registered
    ✓  tools/call suggest_chord_progression — chord progression returned
    All smoke tests passed.

Exit codes:
    0 — all tests passed
    1 — one or more tests failed
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
PYTHON = str(PROJECT_ROOT / ".venv" / "bin" / "python")
MODULE = "musical_mcp.server"
TIMEOUT_SECS = 15

# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------


def _rpc(method: str, params: dict | None = None, id: int = 1) -> bytes:
    """Encode a JSON-RPC 2.0 request as bytes with newline terminator."""
    msg = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        msg["params"] = params
    return (json.dumps(msg) + "\n").encode()


def _read_response(proc: subprocess.Popen) -> dict:
    """Read one JSON-RPC response line from the process stdout."""
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("Server stdout closed unexpectedly")
    return json.loads(line.decode().strip())


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def run_smoke_tests() -> int:
    """
    Launch server, run all checks, return exit code (0=pass, 1=fail).
    """
    failures: list[str] = []

    print(f"Launching server: {PYTHON} -m {MODULE}")
    proc = subprocess.Popen(
        [PYTHON, "-m", MODULE],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(PROJECT_ROOT),
        env={
            **__import__("os").environ,
            "PYTHONPATH": str(PROJECT_ROOT),
            "MCP_TRANSPORT": "stdio",
        },
    )

    try:
        # Give the server 2 seconds to boot
        time.sleep(2)

        # ----------------------------------------------------------------
        # 1. initialize
        # ----------------------------------------------------------------
        proc.stdin.write(
            _rpc(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "smoke-test", "version": "1.0"},
                },
            )
        )
        proc.stdin.flush()

        resp = _read_response(proc)
        if "result" not in resp:
            failures.append(f"initialize: no result — {resp}")
        elif "protocolVersion" not in resp.get("result", {}):
            failures.append(f"initialize: missing protocolVersion — {resp['result']}")
        else:
            print("✓  initialize — protocol negotiated")

        # Send initialized notification (required by MCP spec)
        proc.stdin.write(
            (json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode()
        )
        proc.stdin.flush()

        # ----------------------------------------------------------------
        # 2. tools/list
        # ----------------------------------------------------------------
        proc.stdin.write(_rpc("tools/list", id=2))
        proc.stdin.flush()

        resp = _read_response(proc)
        tools = resp.get("result", {}).get("tools", [])
        tool_names = {t["name"] for t in tools}
        expected_tools = {
            "log_practice_session",
            "create_session_note",
            "analyze_track",
            "search_production_knowledge",
            "suggest_chord_progression",
            "suggest_compatible_tracks",
        }
        missing = expected_tools - tool_names
        if missing:
            failures.append(f"tools/list: missing tools {missing}")
        else:
            print(f"✓  tools/list — {len(tools)} tools registered")

        # ----------------------------------------------------------------
        # 3. resources/list
        # ----------------------------------------------------------------
        proc.stdin.write(_rpc("resources/list", id=3))
        proc.stdin.flush()

        resp = _read_response(proc)
        resources = resp.get("result", {}).get("resources", [])
        resource_uris = {r["uri"] for r in resources}
        expected_uris = {
            "music://practice-logs",
            "music://session-notes",
            "music://knowledge-base/metadata",
            "music://setlist",
        }
        missing_r = expected_uris - resource_uris
        if missing_r:
            failures.append(f"resources/list: missing {missing_r}")
        else:
            print(f"✓  resources/list — {len(resources)} resources registered")

        # ----------------------------------------------------------------
        # 4. prompts/list
        # ----------------------------------------------------------------
        proc.stdin.write(_rpc("prompts/list", id=4))
        proc.stdin.flush()

        resp = _read_response(proc)
        prompts = resp.get("result", {}).get("prompts", [])
        prompt_names = {p["name"] for p in prompts}
        expected_prompts = {"prepare_for_set", "review_practice_week"}
        missing_p = expected_prompts - prompt_names
        if missing_p:
            failures.append(f"prompts/list: missing {missing_p}")
        else:
            print(f"✓  prompts/list — {len(prompts)} prompts registered")

        # ----------------------------------------------------------------
        # 5. tools/call — suggest_chord_progression (no external I/O)
        # ----------------------------------------------------------------
        proc.stdin.write(
            _rpc(
                "tools/call",
                {
                    "name": "suggest_chord_progression",
                    "arguments": {
                        "key": "A minor",
                        "genre": "organic house",
                        "mood": "dark",
                        "bars": 8,
                    },
                },
                id=5,
            )
        )
        proc.stdin.flush()

        resp = _read_response(proc)
        if "result" not in resp:
            failures.append(f"tools/call: no result — {resp}")
        else:
            content = resp["result"].get("content", [])
            # Content should be a list with at least one text item
            if not content:
                failures.append("tools/call: empty content in response")
            else:
                text = content[0].get("text", "")
                if "A minor" not in text:
                    failures.append(
                        f"tools/call: expected 'A minor' in response, got: {text[:100]}"
                    )
                else:
                    print("✓  tools/call suggest_chord_progression — chord progression returned")
                    print(f"   Preview: {text[:80].strip()}...")

        # ----------------------------------------------------------------
        # 6. tools/call — analyze_track with filename only (no audio file)
        # ----------------------------------------------------------------
        proc.stdin.write(
            _rpc(
                "tools/call",
                {
                    "name": "analyze_track",
                    "arguments": {
                        "file_path": "Bicep - Glue (A Minor, 128 BPM).mp3",
                        "analyze_audio": False,
                    },
                },
                id=6,
            )
        )
        proc.stdin.flush()

        resp = _read_response(proc)
        if "result" not in resp:
            failures.append(f"analyze_track: no result — {resp}")
        else:
            content = resp["result"].get("content", [])
            text = content[0].get("text", "") if content else ""
            if not text:
                failures.append("analyze_track: empty response")
            else:
                print("✓  tools/call analyze_track — filename parsing works")
                print(f"   Preview: {text[:80].strip()}...")

    except Exception as exc:
        failures.append(f"Unexpected error: {exc}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    print()
    if failures:
        print(f"❌  {len(failures)} smoke test(s) FAILED:")
        for f in failures:
            print(f"   • {f}")
        return 1
    else:
        print("✅  All smoke tests passed.")
        print("    → Claude Desktop will be able to use the musical-intelligence MCP server.")
        return 0


if __name__ == "__main__":
    sys.exit(run_smoke_tests())
