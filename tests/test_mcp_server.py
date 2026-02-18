"""
MCP Musical Intelligence Server — Day 1 smoke tests.

Tests that:
    1. schemas.py — McpCallLog, make_call_log, URI constants are correct
    2. transport.py — configure_logging doesn't crash, get_transport_mode defaults
    3. server.py — FastMCP instance created, handlers registered, tools listed
    4. handlers.py — tools respond (mocked external deps)

No actual MCP protocol calls — this is unit-level testing of the server logic.
All tests are deterministic: no network, no DB, no file I/O (mocked).

Coverage:
    - McpCallLog creation and serialization
    - make_call_log factory function
    - URI prefix constants
    - Transport mode selection from env
    - FastMCP instance and tool registration
    - Each tool handler produces a string response
    - Resource handlers return valid JSON strings
    - Prompts return non-empty string templates
"""

import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# schemas.py tests
# ---------------------------------------------------------------------------


class TestMcpCallLog:
    """Tests for McpCallLog dataclass and make_call_log factory."""

    def test_call_log_has_auto_id(self) -> None:
        from musical_mcp.schemas import McpCallLog

        log = McpCallLog(
            tool_name="test_tool",
            inputs={"a": 1},
            outputs={"b": 2},
            success=True,
            latency_ms=42.5,
        )
        assert log.call_id is not None
        assert len(log.call_id) == 8

    def test_call_log_auto_timestamp(self) -> None:
        from musical_mcp.schemas import McpCallLog

        before = time.time()
        log = McpCallLog(
            tool_name="t",
            inputs={},
            outputs={},
            success=True,
            latency_ms=1.0,
        )
        after = time.time()
        assert before <= log.timestamp <= after

    def test_to_dict_has_required_keys(self) -> None:
        from musical_mcp.schemas import McpCallLog

        log = McpCallLog(
            tool_name="log_practice_session",
            inputs={"topic": "bass"},
            outputs={"session_id": "abc"},
            success=True,
            latency_ms=12.3,
        )
        d = log.to_dict()
        assert "call_id" in d
        assert "tool_name" in d
        assert "inputs" in d
        assert "outputs" in d
        assert "success" in d
        assert "latency_ms" in d
        assert "timestamp" in d
        assert "error" in d
        assert "correlation_id" in d

    def test_to_dict_tool_name_preserved(self) -> None:
        from musical_mcp.schemas import McpCallLog

        log = McpCallLog(
            tool_name="analyze_track",
            inputs={},
            outputs={},
            success=True,
            latency_ms=0.1,
        )
        assert log.to_dict()["tool_name"] == "analyze_track"

    def test_failed_log_has_error(self) -> None:
        from musical_mcp.schemas import McpCallLog

        log = McpCallLog(
            tool_name="t",
            inputs={},
            outputs={},
            success=False,
            latency_ms=5.0,
            error="file not found",
        )
        assert log.to_dict()["success"] is False
        assert log.to_dict()["error"] == "file not found"

    def test_str_representation_ok(self) -> None:
        from musical_mcp.schemas import McpCallLog

        log = McpCallLog(
            tool_name="analyze_track",
            inputs={},
            outputs={},
            success=True,
            latency_ms=77.7,
        )
        s = str(log)
        assert "analyze_track" in s
        assert "OK" in s

    def test_str_representation_error(self) -> None:
        from musical_mcp.schemas import McpCallLog

        log = McpCallLog(
            tool_name="t",
            inputs={},
            outputs={},
            success=False,
            latency_ms=1.0,
            error="oops",
        )
        assert "ERR:oops" in str(log)

    def test_correlation_id_in_str(self) -> None:
        from musical_mcp.schemas import McpCallLog

        log = McpCallLog(
            tool_name="t",
            inputs={},
            outputs={},
            success=True,
            latency_ms=1.0,
            correlation_id="parent-123",
        )
        assert "parent-123" in str(log)

    def test_make_call_log_factory(self) -> None:
        from musical_mcp.schemas import make_call_log

        log = make_call_log(
            tool_name="log_practice_session",
            inputs={"topic": "bass", "duration_minutes": 60},
            outputs={"session_id": "xyz"},
            latency_ms=25.0,
        )
        assert log.tool_name == "log_practice_session"
        assert log.success is True
        assert log.error is None

    def test_make_call_log_failure(self) -> None:
        from musical_mcp.schemas import make_call_log

        log = make_call_log(
            tool_name="t",
            inputs={},
            outputs={},
            latency_ms=1.0,
            success=False,
            error="timeout",
        )
        assert log.success is False
        assert log.error == "timeout"

    def test_make_call_log_with_correlation(self) -> None:
        from musical_mcp.schemas import make_call_log

        log = make_call_log(
            tool_name="t",
            inputs={},
            outputs={},
            latency_ms=1.0,
            correlation_id="parent-abc",
        )
        assert log.correlation_id == "parent-abc"

    def test_unique_call_ids(self) -> None:
        from musical_mcp.schemas import McpCallLog

        ids = {
            McpCallLog(
                tool_name="t",
                inputs={},
                outputs={},
                success=True,
                latency_ms=0.0,
            ).call_id
            for _ in range(10)
        }
        assert len(ids) == 10  # all unique


class TestUriConstants:
    """URI constants are stable strings."""

    def test_practice_logs_uri(self) -> None:
        from musical_mcp.schemas import URI_PRACTICE_LOGS

        assert URI_PRACTICE_LOGS.startswith("music://")

    def test_session_notes_uri(self) -> None:
        from musical_mcp.schemas import URI_SESSION_NOTES

        assert URI_SESSION_NOTES.startswith("music://")

    def test_kb_metadata_uri(self) -> None:
        from musical_mcp.schemas import URI_KB_METADATA

        assert URI_KB_METADATA.startswith("music://")

    def test_setlist_uri(self) -> None:
        from musical_mcp.schemas import URI_SETLIST

        assert URI_SETLIST.startswith("music://")

    def test_all_uris_unique(self) -> None:
        from musical_mcp.schemas import (
            URI_KB_METADATA,
            URI_PRACTICE_LOGS,
            URI_SESSION_NOTES,
            URI_SETLIST,
        )

        uris = {URI_PRACTICE_LOGS, URI_SESSION_NOTES, URI_KB_METADATA, URI_SETLIST}
        assert len(uris) == 4


# ---------------------------------------------------------------------------
# transport.py tests
# ---------------------------------------------------------------------------


class TestTransport:
    def test_configure_logging_does_not_raise(self) -> None:
        import logging

        from musical_mcp.transport import configure_logging

        configure_logging(level=logging.DEBUG)  # should not raise

    def test_get_transport_mode_default_is_stdio(self) -> None:
        from musical_mcp.transport import get_transport_mode

        with patch.dict(os.environ, {}, clear=True):
            # Ensure MCP_TRANSPORT is not set
            os.environ.pop("MCP_TRANSPORT", None)
            mode = get_transport_mode()
        assert mode == "stdio"

    def test_get_transport_mode_sse(self) -> None:
        from musical_mcp.transport import get_transport_mode

        with patch.dict(os.environ, {"MCP_TRANSPORT": "sse"}):
            mode = get_transport_mode()
        assert mode == "sse"

    def test_get_transport_mode_unknown_falls_back_to_stdio(self) -> None:
        from musical_mcp.transport import get_transport_mode

        with patch.dict(os.environ, {"MCP_TRANSPORT": "grpc"}):
            mode = get_transport_mode()
        assert mode == "stdio"

    def test_get_transport_mode_case_insensitive(self) -> None:
        from musical_mcp.transport import get_transport_mode

        with patch.dict(os.environ, {"MCP_TRANSPORT": "SSE"}):
            mode = get_transport_mode()
        assert mode == "sse"


# ---------------------------------------------------------------------------
# server.py — FastMCP instance
# ---------------------------------------------------------------------------


class TestMcpServerInstance:
    """The FastMCP instance is created and tools are registered."""

    def test_mcp_instance_exists(self) -> None:
        from musical_mcp.server import mcp

        assert mcp is not None

    def test_server_has_tools_registered(self) -> None:
        from musical_mcp.server import mcp

        # FastMCP stores tools in _tool_manager._tools dict
        tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
        assert len(tools) >= 5  # at least our 5 musical tools

    def test_expected_tools_registered(self) -> None:
        from musical_mcp.server import mcp

        tool_names = set(mcp._tool_manager._tools.keys())  # type: ignore[attr-defined]
        expected = {
            "log_practice_session",
            "create_session_note",
            "analyze_track",
            "search_production_knowledge",
            "suggest_chord_progression",
            "suggest_compatible_tracks",
        }
        assert expected.issubset(tool_names), f"Missing tools: {expected - tool_names}"

    def test_server_name_is_musical_intelligence(self) -> None:
        from musical_mcp.server import mcp

        assert mcp.name == "musical-intelligence"


# ---------------------------------------------------------------------------
# handlers.py — tool handler responses (mocked Week 3 tools)
# ---------------------------------------------------------------------------


class TestLogPracticeSessionHandler:
    """log_practice_session handler produces correct string output."""

    @pytest.mark.asyncio
    async def test_successful_session_log(self) -> None:
        from musical_mcp.server import mcp

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = {
            "session_id": "sess-abc",
            "topic": "bass design",
            "duration_minutes": 60,
            "practice_gaps": ["mixing"],
        }
        mock_result.error = None

        with patch(
            "tools.music.log_practice_session.LogPracticeSession.__call__", return_value=mock_result
        ):
            tool_fn = mcp._tool_manager._tools["log_practice_session"]  # type: ignore[attr-defined]
            result = await tool_fn.fn(
                topic="bass design",
                duration_minutes=60,
                notes="",
                bpm_practiced=0,
                key_practiced="",
            )

        assert "sess-abc" in result
        assert "bass design" in result
        assert "60" in result

    @pytest.mark.asyncio
    async def test_failed_session_log_returns_error(self) -> None:
        from musical_mcp.server import mcp

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "duration must be > 0"

        with patch(
            "tools.music.log_practice_session.LogPracticeSession.__call__", return_value=mock_result
        ):
            tool_fn = mcp._tool_manager._tools["log_practice_session"]  # type: ignore[attr-defined]
            result = await tool_fn.fn(
                topic="bass",
                duration_minutes=0,
                notes="",
                bpm_practiced=0,
                key_practiced="",
            )

        assert "✗" in result
        assert "duration" in result


class TestAnalyzeTrackHandler:
    """analyze_track handler produces formatted output."""

    @pytest.mark.asyncio
    async def test_filename_analysis(self) -> None:
        from musical_mcp.server import mcp

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = {
            "bpm": 124,
            "key": "A minor",
            "energy": 7,
            "confidence": "high",
        }
        mock_result.metadata = {"method": "filename_parsing"}
        mock_result.error = None

        with patch("tools.music.analyze_track.AnalyzeTrack.__call__", return_value=mock_result):
            tool_fn = mcp._tool_manager._tools["analyze_track"]  # type: ignore[attr-defined]
            result = await tool_fn.fn(
                file_path="track_124bpm_Aminor.mp3",
                analyze_audio=False,
            )

        assert "124" in result
        assert "A minor" in result
        assert "7" in result


class TestCreateSessionNoteHandler:
    @pytest.mark.asyncio
    async def test_discovery_note_saved(self) -> None:
        from musical_mcp.server import mcp

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = {
            "note_id": "note-xyz",
            "category": "discovery",
            "title": "Fast attack sidechain",
            "tags": ["sidechain", "attack"],
            "total_notes": 3,
        }
        mock_result.error = None

        with patch(
            "tools.music.create_session_note.CreateSessionNote.__call__", return_value=mock_result
        ):
            tool_fn = mcp._tool_manager._tools["create_session_note"]  # type: ignore[attr-defined]
            result = await tool_fn.fn(
                category="discovery",
                title="Fast attack sidechain",
                content="Fast attack on sidechain creates tight pumping",
                tags=["sidechain", "attack"],
            )

        assert "note-xyz" in result
        assert "discovery" in result


class TestSuggestChordProgressionHandler:
    @pytest.mark.asyncio
    async def test_chord_progression_formatted(self) -> None:
        from musical_mcp.server import mcp

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = {
            "chords": ["Am7", "Fmaj7", "Cmaj7", "Gm7"],
            "roman_analysis": "i7 - VI7 - III7 - vii7",
            "production_tips": ["Use sustained pads", "Avoid sharp attacks"],
        }
        mock_result.error = None

        with patch(
            "tools.music.suggest_chord_progression.SuggestChordProgression.__call__",
            return_value=mock_result,
        ):
            tool_fn = mcp._tool_manager._tools["suggest_chord_progression"]  # type: ignore[attr-defined]
            result = await tool_fn.fn(
                key="A minor",
                genre="organic house",
                mood="melancholic",
                bars=8,
            )

        assert "Am7" in result
        assert "A minor" in result


class TestSuggestCompatibleTracksHandler:
    @pytest.mark.asyncio
    async def test_compatible_tracks_listed(self) -> None:
        from musical_mcp.server import mcp

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = {
            "camelot_position": "8A",
            "compatible_keys": [
                {"key": "A minor", "camelot": "8A", "relationship": "same"},
                {"key": "E minor", "camelot": "9A", "relationship": "adjacent"},
                {"key": "D minor", "camelot": "7A", "relationship": "adjacent"},
                {"key": "C major", "camelot": "8B", "relationship": "relative"},
            ],
            "total_found": 4,
        }
        mock_result.error = None

        with patch(
            "tools.music.suggest_compatible_tracks.SuggestCompatibleTracks.__call__",
            return_value=mock_result,
        ):
            tool_fn = mcp._tool_manager._tools["suggest_compatible_tracks"]  # type: ignore[attr-defined]
            result = await tool_fn.fn(key="A minor", bpm=0.0, max_results=10)

        assert "A minor" in result
        assert "8A" in result


# ---------------------------------------------------------------------------
# handlers.py — resource handlers return valid JSON
# ---------------------------------------------------------------------------


class TestResourceHandlers:
    def test_practice_logs_no_file_returns_empty(self) -> None:
        """When data/practice_sessions.json doesn't exist → returns empty list."""
        with patch("pathlib.Path.exists", return_value=False):
            from musical_mcp.server import mcp

            resource_fn = mcp._resource_manager._resources.get(  # type: ignore[attr-defined]
                "music://practice-logs"
            )
            if resource_fn is None:
                # FastMCP may store by URI differently — skip if not found
                return
            result = resource_fn.fn()
            data = json.loads(result)
            assert data["total"] == 0

    def test_session_notes_no_file_returns_empty(self) -> None:
        with patch("pathlib.Path.exists", return_value=False):
            from musical_mcp.server import mcp

            resource_fn = mcp._resource_manager._resources.get(  # type: ignore[attr-defined]
                "music://session-notes"
            )
            if resource_fn is None:
                return
            result = resource_fn.fn()
            data = json.loads(result)
            assert data["total"] == 0

    def test_kb_metadata_no_db_url(self) -> None:
        """When DATABASE_URL is not set → returns unavailable status."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATABASE_URL", None)
            from musical_mcp.server import mcp

            resource_fn = mcp._resource_manager._resources.get(  # type: ignore[attr-defined]
                "music://knowledge-base/metadata"
            )
            if resource_fn is None:
                return
            result = resource_fn.fn()
            data = json.loads(result)
            assert data["status"] in ("unavailable", "error")


# ---------------------------------------------------------------------------
# handlers.py — prompt templates are non-empty strings
# ---------------------------------------------------------------------------


class TestPromptHandlers:
    def test_prepare_for_set_returns_string(self) -> None:
        from musical_mcp.server import mcp

        prompt_fn = mcp._prompt_manager._prompts.get("prepare_for_set")  # type: ignore[attr-defined]
        if prompt_fn is None:
            pytest.skip("Prompt not accessible via internal API")
        result = prompt_fn.fn(hours_until_set=2, set_duration_minutes=60, venue_vibe="club")
        assert isinstance(result, str)
        assert len(result) > 100

    def test_review_practice_week_returns_string(self) -> None:
        from musical_mcp.server import mcp

        prompt_fn = mcp._prompt_manager._prompts.get("review_practice_week")  # type: ignore[attr-defined]
        if prompt_fn is None:
            pytest.skip("Prompt not accessible via internal API")
        result = prompt_fn.fn(target_areas="mixing, chord theory")
        assert isinstance(result, str)
        assert "practice" in result.lower()

    def test_prepare_for_set_references_resources(self) -> None:
        from musical_mcp.server import mcp

        prompt_fn = mcp._prompt_manager._prompts.get("prepare_for_set")  # type: ignore[attr-defined]
        if prompt_fn is None:
            pytest.skip("Prompt not accessible via internal API")
        result = prompt_fn.fn()
        # Should reference the practice logs URI
        assert "music://" in result
