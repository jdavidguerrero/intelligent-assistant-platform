"""
MCP Musical Intelligence — tool_schemas.py tests.

Verifies that the canonical JSON schemas for all musical tools are:
    1. Structurally valid (name, description, input_schema present)
    2. Complete (all 6 tools registered)
    3. Correctly typed (required params have proper types)
    4. Enum-constrained where expected (category, genre, mood, bars)
    5. Range-bounded where expected (duration_minutes, bpm, top_k)
    6. Contract-stable (schema for known tool doesn't change shape)

These tests protect the LLM routing contract. A broken schema means
Claude calls tools with wrong parameters — silent failures in production.

Pure unit tests — no I/O, no network, no FastMCP instantiation.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------


class TestSchemaRegistry:
    def test_all_six_tools_registered(self) -> None:
        from musical_mcp.tool_schemas import list_tool_names

        names = set(list_tool_names())
        expected = {
            "log_practice_session",
            "create_session_note",
            "analyze_track",
            "search_production_knowledge",
            "suggest_chord_progression",
            "suggest_compatible_tracks",
        }
        assert expected == names, f"Missing: {expected - names}, extra: {names - expected}"

    def test_list_tool_names_is_sorted(self) -> None:
        from musical_mcp.tool_schemas import list_tool_names

        names = list_tool_names()
        assert names == sorted(names)

    def test_get_tool_schema_unknown_raises_key_error(self) -> None:
        from musical_mcp.tool_schemas import get_tool_schema

        with pytest.raises(KeyError):
            get_tool_schema("nonexistent_tool")

    def test_get_all_schemas_returns_all_six(self) -> None:
        from musical_mcp.tool_schemas import get_all_schemas

        schemas = get_all_schemas()
        assert len(schemas) == 6

    def test_get_all_schemas_sorted_by_name(self) -> None:
        from musical_mcp.tool_schemas import get_all_schemas

        schemas = get_all_schemas()
        names = [s["name"] for s in schemas]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# Structure validation — every schema must pass
# ---------------------------------------------------------------------------


class TestSchemaStructureValidation:
    """validate_schema_structure returns no errors for all registered schemas."""

    def test_all_schemas_pass_structure_validation(self) -> None:
        from musical_mcp.tool_schemas import get_all_schemas, validate_schema_structure

        for schema in get_all_schemas():
            errors = validate_schema_structure(schema)
            assert errors == [], f"Schema {schema.get('name', '?')} has validation errors: {errors}"

    def test_missing_name_caught(self) -> None:
        from musical_mcp.tool_schemas import validate_schema_structure

        errors = validate_schema_structure(
            {
                "description": "A" * 25,
                "input_schema": {"type": "object", "properties": {}, "required": []},
            }
        )
        assert any("name" in e for e in errors)

    def test_short_description_caught(self) -> None:
        from musical_mcp.tool_schemas import validate_schema_structure

        errors = validate_schema_structure(
            {
                "name": "t",
                "description": "Short",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            }
        )
        assert any("description" in e for e in errors)

    def test_missing_required_key_in_properties_caught(self) -> None:
        from musical_mcp.tool_schemas import validate_schema_structure

        errors = validate_schema_structure(
            {
                "name": "t",
                "description": "A" * 25,
                "input_schema": {
                    "type": "object",
                    "properties": {"a": {"type": "string"}},
                    "required": ["a", "b_missing"],  # b_missing not in properties
                },
            }
        )
        assert any("b_missing" in e for e in errors)

    def test_wrong_input_schema_type_caught(self) -> None:
        from musical_mcp.tool_schemas import validate_schema_structure

        errors = validate_schema_structure(
            {
                "name": "t",
                "description": "A" * 25,
                "input_schema": {"type": "array", "properties": {}, "required": []},
            }
        )
        assert any("object" in e for e in errors)


# ---------------------------------------------------------------------------
# log_practice_session schema
# ---------------------------------------------------------------------------


class TestLogPracticeSessionSchema:
    def _schema(self):
        from musical_mcp.tool_schemas import get_tool_schema

        return get_tool_schema("log_practice_session")

    def test_required_params(self) -> None:
        s = self._schema()
        required = s["input_schema"]["required"]
        assert "topic" in required
        assert "duration_minutes" in required

    def test_optional_params_have_defaults(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        assert "default" in props["notes"]
        assert "default" in props["bpm_practiced"]
        assert "default" in props["key_practiced"]

    def test_duration_minutes_is_integer_with_range(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        dm = props["duration_minutes"]
        assert dm["type"] == "integer"
        assert dm["minimum"] >= 1
        assert dm["maximum"] <= 480

    def test_topic_is_string_with_length_constraint(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        assert props["topic"]["type"] == "string"
        assert "maxLength" in props["topic"]

    def test_description_mentions_session(self) -> None:
        assert "session" in self._schema()["description"].lower()


# ---------------------------------------------------------------------------
# create_session_note schema
# ---------------------------------------------------------------------------


class TestCreateSessionNoteSchema:
    def _schema(self):
        from musical_mcp.tool_schemas import get_tool_schema

        return get_tool_schema("create_session_note")

    def test_required_params(self) -> None:
        required = self._schema()["input_schema"]["required"]
        assert "category" in required
        assert "title" in required
        assert "content" in required

    def test_category_has_enum(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        enum = props["category"]["enum"]
        assert "discovery" in enum
        assert "problem" in enum
        assert "idea" in enum
        assert "reference" in enum
        assert "next_steps" in enum

    def test_category_enum_has_exactly_five_values(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        assert len(props["category"]["enum"]) == 5

    def test_tags_is_array_of_strings(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        tags = props["tags"]
        assert tags["type"] == "array"
        assert tags["items"]["type"] == "string"

    def test_content_has_max_length(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        assert props["content"]["maxLength"] >= 500


# ---------------------------------------------------------------------------
# analyze_track schema
# ---------------------------------------------------------------------------


class TestAnalyzeTrackSchema:
    def _schema(self):
        from musical_mcp.tool_schemas import get_tool_schema

        return get_tool_schema("analyze_track")

    def test_file_path_is_required(self) -> None:
        required = self._schema()["input_schema"]["required"]
        assert "file_path" in required

    def test_analyze_audio_is_boolean_with_default(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        aa = props["analyze_audio"]
        assert aa["type"] == "boolean"
        assert aa["default"] is True

    def test_description_mentions_bpm_and_key(self) -> None:
        desc = self._schema()["description"].lower()
        assert "bpm" in desc
        assert "key" in desc

    def test_file_path_has_examples(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        assert "examples" in props["file_path"]
        assert len(props["file_path"]["examples"]) >= 2


# ---------------------------------------------------------------------------
# search_production_knowledge schema
# ---------------------------------------------------------------------------


class TestSearchProductionKnowledgeSchema:
    def _schema(self):
        from musical_mcp.tool_schemas import get_tool_schema

        return get_tool_schema("search_production_knowledge")

    def test_query_is_required(self) -> None:
        required = self._schema()["input_schema"]["required"]
        assert "query" in required

    def test_top_k_has_range(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        assert props["top_k"]["minimum"] >= 1
        assert props["top_k"]["maximum"] <= 20

    def test_confidence_threshold_is_float_with_range(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        ct = props["confidence_threshold"]
        assert ct["type"] == "number"
        assert ct["minimum"] >= 0.0
        assert ct["maximum"] <= 1.0
        assert ct["default"] == 0.58

    def test_query_has_min_and_max_length(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        q = props["query"]
        assert "minLength" in q
        assert "maxLength" in q


# ---------------------------------------------------------------------------
# suggest_chord_progression schema
# ---------------------------------------------------------------------------


class TestSuggestChordProgressionSchema:
    def _schema(self):
        from musical_mcp.tool_schemas import get_tool_schema

        return get_tool_schema("suggest_chord_progression")

    def test_key_is_required(self) -> None:
        required = self._schema()["input_schema"]["required"]
        assert "key" in required

    def test_genre_has_enum_with_organic_house(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        assert "organic house" in props["genre"]["enum"]

    def test_mood_has_enum(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        mood_enum = props["mood"]["enum"]
        assert "melancholic" in mood_enum
        assert "uplifting" in mood_enum
        assert "dark" in mood_enum

    def test_bars_enum_is_4_8_16(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        assert set(props["bars"]["enum"]) == {4, 8, 16}

    def test_genre_default_is_organic_house(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        assert props["genre"]["default"] == "organic house"


# ---------------------------------------------------------------------------
# suggest_compatible_tracks schema
# ---------------------------------------------------------------------------


class TestSuggestCompatibleTracksSchema:
    def _schema(self):
        from musical_mcp.tool_schemas import get_tool_schema

        return get_tool_schema("suggest_compatible_tracks")

    def test_key_is_required(self) -> None:
        required = self._schema()["input_schema"]["required"]
        assert "key" in required

    def test_bpm_is_optional_float(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        bpm = props["bpm"]
        assert bpm["type"] == "number"
        assert bpm["default"] == 0.0

    def test_bpm_has_zero_minimum(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        assert props["bpm"]["minimum"] == 0.0

    def test_max_results_is_integer(self) -> None:
        props = self._schema()["input_schema"]["properties"]
        assert props["max_results"]["type"] == "integer"
        assert props["max_results"]["default"] == 10

    def test_description_mentions_camelot(self) -> None:
        desc = self._schema()["description"].lower()
        assert "camelot" in desc
