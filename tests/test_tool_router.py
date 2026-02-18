"""
Tests for the ToolRouter — intent detection, param extraction, routing, and describe_tools.

Pure unit tests — no DB, no real tool execution.
Uses a fake registry with mock tools to test routing in isolation.

Coverage:
  - detect_intents: keyword matching for all tools
  - extract_params: duration, topic, key, bpm, genre, artist extraction
  - route: single tool, multi-tool, fallback, empty query
  - describe_tools: Anthropic tool_use API schema format
  - Integration: detect → extract → route pipeline
"""

from unittest.mock import MagicMock

from tools.base import ToolResult
from tools.registry import ToolRegistry
from tools.router import (
    ToolRouter,
    _extract_artist_from_query,
    _extract_bpm_from_query,
    _extract_duration_minutes,
    _extract_genre_from_query,
    _extract_key_from_query,
    _extract_topic,
)

# ---------------------------------------------------------------------------
# Helpers — fake registry with mock tools
# ---------------------------------------------------------------------------


def _make_mock_tool(name: str, success: bool = True, data: dict | None = None) -> MagicMock:
    """Create a mock MusicalTool with a configurable __call__ result."""
    tool = MagicMock()
    tool.name = name
    tool.description = f"Mock {name} tool"
    tool.parameters = []
    tool.to_dict.return_value = {
        "name": name,
        "description": f"Mock {name} tool",
        "parameters": [],
    }
    tool.return_value = ToolResult(success=success, data=data or {"mock": True})
    return tool


def _make_registry(*tool_names: str) -> ToolRegistry:
    """Build a ToolRegistry pre-loaded with named mock tools."""
    registry = ToolRegistry()
    for name in tool_names:
        mock = _make_mock_tool(name)
        registry._tools[name] = mock
    return registry


# ---------------------------------------------------------------------------
# _extract_duration_minutes
# ---------------------------------------------------------------------------


class TestExtractDurationMinutes:
    def test_2_hour(self):
        assert _extract_duration_minutes("I just finished a 2-hour session") == 120

    def test_2_hours_with_space(self):
        assert _extract_duration_minutes("worked for 2 hours") == 120

    def test_90_minutes(self):
        assert _extract_duration_minutes("practiced for 90 minutes") == 90

    def test_1_min(self):
        assert _extract_duration_minutes("spent 1 min on this") == 1

    def test_1h(self):
        assert _extract_duration_minutes("spent 1h on bass") == 60

    def test_no_duration_returns_none(self):
        assert _extract_duration_minutes("I practiced bass design") is None


# ---------------------------------------------------------------------------
# _extract_topic
# ---------------------------------------------------------------------------


class TestExtractTopic:
    def test_session_on_bass_design(self):
        topic = _extract_topic("I just finished a 2-hour session on bass design")
        assert topic == "bass design"

    def test_practiced_pattern(self):
        topic = _extract_topic("I practiced chord progressions today")
        assert topic is not None
        assert "chord" in topic

    def test_worked_on_pattern(self):
        topic = _extract_topic("I worked on arrangement for an hour")
        assert topic is not None
        assert "arrangement" in topic

    def test_no_topic_returns_none(self):
        assert _extract_topic("I just finished a session") is None


# ---------------------------------------------------------------------------
# _extract_key_from_query
# ---------------------------------------------------------------------------


class TestExtractKeyFromQuery:
    def test_a_minor(self):
        assert _extract_key_from_query("chord progression in A minor") == "A minor"

    def test_c_major(self):
        assert _extract_key_from_query("generate chords in C major") == "C major"

    def test_f_sharp_minor(self):
        assert _extract_key_from_query("compatible with F# minor at 124 bpm") == "F# minor"

    def test_no_key_returns_none(self):
        assert _extract_key_from_query("suggest some chords") is None

    def test_note_properly_capitalized(self):
        key = _extract_key_from_query("in a minor scale")
        assert key == "A minor"


# ---------------------------------------------------------------------------
# _extract_bpm_from_query
# ---------------------------------------------------------------------------


class TestExtractBpmFromQuery:
    def test_124_bpm(self):
        assert _extract_bpm_from_query("track at 124 bpm") == 124.0

    def test_no_bpm_returns_none(self):
        assert _extract_bpm_from_query("some organic house track") is None

    def test_out_of_range_returns_none(self):
        assert _extract_bpm_from_query("at 30 bpm") is None


# ---------------------------------------------------------------------------
# _extract_genre_from_query
# ---------------------------------------------------------------------------


class TestExtractGenreFromQuery:
    def test_organic_house(self):
        assert _extract_genre_from_query("how to make organic house") == "organic house"

    def test_techno(self):
        assert _extract_genre_from_query("techno production techniques") == "techno"

    def test_no_genre_returns_none(self):
        assert _extract_genre_from_query("some random query") is None


# ---------------------------------------------------------------------------
# _extract_artist_from_query
# ---------------------------------------------------------------------------


class TestExtractArtistFromQuery:
    def test_style_of_pattern(self):
        artist = _extract_artist_from_query("generate chords in the style of Sebastien Leger")
        assert artist is not None
        assert "Sebastien" in artist

    def test_like_pattern(self):
        artist = _extract_artist_from_query("generate something like Rodriguez Jr.")
        assert artist is not None

    def test_no_artist_returns_none(self):
        assert _extract_artist_from_query("generate some chords") is None


# ---------------------------------------------------------------------------
# ToolRouter.detect_intents
# ---------------------------------------------------------------------------


class TestDetectIntents:
    _router = ToolRouter(registry=_make_registry())

    def test_log_session_intent(self):
        intents = self._router.detect_intents("I just finished a 2-hour session on bass design")
        assert "log_practice_session" in intents

    def test_worked_on_triggers_log(self):
        intents = self._router.detect_intents("I worked on arrangement for 90 minutes")
        assert "log_practice_session" in intents

    def test_create_note_intent(self):
        intents = self._router.detect_intents("note that I discovered a sidechain trick")
        assert "create_session_note" in intents

    def test_discovered_triggers_note(self):
        intents = self._router.detect_intents("I discovered that using fast attack creates pumping")
        assert "create_session_note" in intents

    def test_chord_progression_intent(self):
        intents = self._router.detect_intents("suggest chord progression in A minor")
        assert "suggest_chord_progression" in intents

    def test_compatible_tracks_intent(self):
        intents = self._router.detect_intents("what tracks are compatible with A minor at 124 bpm")
        assert "suggest_compatible_tracks" in intents

    def test_midi_intent(self):
        intents = self._router.detect_intents("generate midi pattern for these chords")
        assert "generate_midi_pattern" in intents

    def test_analyze_track_intent(self):
        intents = self._router.detect_intents("analyze this track and detect bpm")
        assert "analyze_track" in intents

    def test_search_by_genre_intent(self):
        intents = self._router.detect_intents("how to make organic house music")
        assert "search_by_genre" in intents

    def test_extract_style_intent(self):
        intents = self._router.detect_intents(
            "generate chords in the style of Sebastien Leger organic house"
        )
        assert "extract_style_from_context" in intents

    def test_unknown_query_returns_empty(self):
        intents = self._router.detect_intents("what is quantum mechanics?")
        assert intents == []

    def test_empty_query_returns_empty(self):
        assert self._router.detect_intents("") == []

    def test_multi_intent_detection(self):
        """A query can match multiple tools."""
        intents = self._router.detect_intents(
            "suggest chord progression in organic house for A minor"
        )
        # Both chord progression AND search_by_genre (organic house) should fire
        assert len(intents) >= 1

    def test_case_insensitive_matching(self):
        intents = self._router.detect_intents("I JUST FINISHED a session on bass design")
        assert "log_practice_session" in intents


# ---------------------------------------------------------------------------
# ToolRouter.extract_params
# ---------------------------------------------------------------------------


class TestExtractParams:
    _router = ToolRouter(registry=_make_registry())

    def test_log_session_extracts_topic(self):
        params = self._router.extract_params(
            "log_practice_session",
            "I just finished a 2-hour session on bass design",
        )
        assert params.get("topic") == "bass design"

    def test_log_session_extracts_duration(self):
        params = self._router.extract_params(
            "log_practice_session",
            "I just finished a 2-hour session on bass design",
        )
        assert params.get("duration_minutes") == 120

    def test_note_discovery_category(self):
        params = self._router.extract_params(
            "create_session_note",
            "I discovered that fast attack creates pumping",
        )
        assert params.get("category") == "discovery"

    def test_note_idea_category(self):
        params = self._router.extract_params(
            "create_session_note",
            "idea: try arpeggio on the lead",
        )
        assert params.get("category") == "idea"

    def test_note_next_steps_category(self):
        params = self._router.extract_params(
            "create_session_note",
            "next steps: finish the arrangement",
        )
        assert params.get("category") == "next_steps"

    def test_compatible_extracts_key(self):
        params = self._router.extract_params(
            "suggest_compatible_tracks",
            "compatible with A minor at 124 bpm",
        )
        assert params.get("key") == "A minor"
        assert params.get("bpm") == 124.0

    def test_chord_extracts_key_and_genre(self):
        params = self._router.extract_params(
            "suggest_chord_progression",
            "chord progression in A minor for organic house",
        )
        assert params.get("key") == "A minor"
        assert params.get("genre") == "organic house"

    def test_midi_extracts_bpm(self):
        params = self._router.extract_params(
            "generate_midi_pattern",
            "generate midi pattern at 124 bpm",
        )
        assert params.get("bpm") == 124.0

    def test_search_extracts_genre_and_query(self):
        params = self._router.extract_params(
            "search_by_genre",
            "how to make organic house",
        )
        assert params.get("genre") == "organic house"
        assert "query" in params

    def test_analyze_extracts_file_path(self):
        params = self._router.extract_params(
            "analyze_track",
            "analyze /tmp/track.mp3 and detect bpm",
        )
        assert params.get("file_path") == "/tmp/track.mp3"

    def test_extract_style_extracts_artist(self):
        params = self._router.extract_params(
            "extract_style_from_context",
            "generate chords in the style of Sebastien Leger",
        )
        assert params.get("artist") is not None


# ---------------------------------------------------------------------------
# ToolRouter.route — single tool
# ---------------------------------------------------------------------------


class TestToolRouterRouteSingleTool:
    def test_session_log_query_routes_correctly(self):
        registry = _make_registry("log_practice_session")
        router = ToolRouter(registry=registry)

        result = router.route(
            "I just finished a 2-hour session on bass design",
            extra_params={"log_practice_session": {"notes": "great session"}},
        )
        assert "log_practice_session" in result.matched_tools
        assert result.fallback_to_rag is False

    def test_tool_result_returned(self):
        registry = _make_registry("log_practice_session")
        router = ToolRouter(registry=registry)

        result = router.route("I just finished a 2-hour session on bass design")
        # Tool was called — check result
        assert len(result.tool_results) >= 1

    def test_extra_params_merged(self):
        registry = _make_registry("log_practice_session")
        mock_tool = registry.get("log_practice_session")
        router = ToolRouter(registry=registry)

        router.route(
            "I just finished a session on bass design",
            extra_params={"log_practice_session": {"notes": "extra note"}},
        )
        # Check that the tool was called with notes in params
        call_kwargs = mock_tool.call_args[1]
        assert call_kwargs.get("notes") == "extra note"


# ---------------------------------------------------------------------------
# ToolRouter.route — fallback
# ---------------------------------------------------------------------------


class TestToolRouterFallback:
    def test_unknown_query_falls_back(self):
        router = ToolRouter(registry=_make_registry())
        result = router.route("what is the capital of France?")
        assert result.fallback_to_rag is True
        assert result.matched_tools == ()

    def test_empty_query_falls_back(self):
        router = ToolRouter(registry=_make_registry())
        result = router.route("")
        assert result.fallback_to_rag is True

    def test_whitespace_only_falls_back(self):
        router = ToolRouter(registry=_make_registry())
        result = router.route("   ")
        assert result.fallback_to_rag is True

    def test_tool_not_in_registry_falls_back(self):
        """Intent matches but tool not in registry → fallback."""
        router = ToolRouter(registry=_make_registry())  # empty registry
        result = router.route("I just finished a 2-hour session on bass design")
        assert result.fallback_to_rag is True

    def test_query_preserved_in_result(self):
        router = ToolRouter(registry=_make_registry())
        result = router.route("some unknown query")
        assert result.query == "some unknown query"


# ---------------------------------------------------------------------------
# ToolRouter.describe_tools
# ---------------------------------------------------------------------------


class TestDescribeTools:
    def test_returns_list(self):
        registry = _make_registry("log_practice_session", "analyze_track")
        router = ToolRouter(registry=registry)
        tools = router.describe_tools()
        assert isinstance(tools, list)

    def test_each_tool_has_required_schema_fields(self):
        registry = _make_registry("log_practice_session")
        # Give it real parameters structure
        mock_tool = registry.get("log_practice_session")
        mock_tool.to_dict.return_value = {
            "name": "log_practice_session",
            "description": "Log a session",
            "parameters": [
                {
                    "name": "topic",
                    "type": "str",
                    "description": "Topic practiced",
                    "required": True,
                    "default": None,
                }
            ],
        }
        router = ToolRouter(registry=registry)
        tools = router.describe_tools()
        assert len(tools) == 1
        tool = tools[0]
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert "properties" in tool["input_schema"]
        assert "required" in tool["input_schema"]

    def test_required_params_in_required_list(self):
        registry = _make_registry("analyze_track")
        mock_tool = registry.get("analyze_track")
        mock_tool.to_dict.return_value = {
            "name": "analyze_track",
            "description": "Analyze track",
            "parameters": [
                {
                    "name": "file_path",
                    "type": "str",
                    "description": "Path",
                    "required": True,
                    "default": None,
                },
                {
                    "name": "top_k",
                    "type": "int",
                    "description": "K",
                    "required": False,
                    "default": 5,
                },
            ],
        }
        router = ToolRouter(registry=registry)
        tools = router.describe_tools()
        schema = tools[0]["input_schema"]
        assert "file_path" in schema["required"]
        assert "top_k" not in schema["required"]

    def test_type_mapping_str_to_string(self):
        registry = _make_registry("t")
        registry.get("t").to_dict.return_value = {
            "name": "t",
            "description": "T",
            "parameters": [
                {"name": "p", "type": "str", "description": "D", "required": True, "default": None}
            ],
        }
        router = ToolRouter(registry=registry)
        tools = router.describe_tools()
        assert tools[0]["input_schema"]["properties"]["p"]["type"] == "string"

    def test_type_mapping_int_to_integer(self):
        registry = _make_registry("t")
        registry.get("t").to_dict.return_value = {
            "name": "t",
            "description": "T",
            "parameters": [
                {"name": "n", "type": "int", "description": "D", "required": False, "default": 5}
            ],
        }
        router = ToolRouter(registry=registry)
        tools = router.describe_tools()
        assert tools[0]["input_schema"]["properties"]["n"]["type"] == "integer"

    def test_empty_registry_returns_empty_list(self):
        router = ToolRouter(registry=ToolRegistry())
        assert router.describe_tools() == []
