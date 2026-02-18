"""
MCP Musical Intelligence — explicit JSON schemas for all musical tools.

Why this module exists:
    FastMCP auto-generates schemas from Python type hints. That's convenient
    but produces minimal schemas — no enum constraints, no range validation,
    no example values. Claude uses these schemas to decide *when* and *how*
    to call each tool. Richer schemas = better LLM routing decisions.

    This module defines the *canonical* schema for each tool as a pure Python
    dict (JSON-Schema draft-07 compatible). These schemas are:
        1. Validated at server startup (structure check)
        2. Used in tests to assert contract stability
        3. Available for inspection via the get_tool_schema() function
        4. Documented for the OpenDock edge/cloud integration spec

Schema design rules:
    - Every parameter has: type, description, and example
    - Required parameters are listed explicitly
    - Enum constraints for categorical fields (category, genre, mood)
    - Numeric ranges for bounded values (duration_minutes, bpm, bars)
    - Optional parameters have sensible defaults documented

Pure module — no I/O, no FastMCP imports, no side effects.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Individual tool schemas (JSON Schema draft-07)
# ---------------------------------------------------------------------------

_LOG_PRACTICE_SESSION_SCHEMA: dict[str, Any] = {
    "name": "log_practice_session",
    "description": (
        "Log a completed music production or practice session. "
        "Use when the user says they finished a session, practiced something, "
        "or worked on a specific topic for a measurable amount of time. "
        "Creates a persistent record used for gap detection and suggestions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "What was practiced (e.g. 'bass design', 'chord progressions', 'mixing')",
                "examples": ["bass design", "arrangement", "sidechain compression"],
                "minLength": 1,
                "maxLength": 200,
            },
            "duration_minutes": {
                "type": "integer",
                "description": "How long the session lasted in minutes (must be positive)",
                "minimum": 1,
                "maximum": 480,
                "examples": [30, 60, 90, 120],
            },
            "notes": {
                "type": "string",
                "description": "Optional free-text notes about the session",
                "default": "",
                "maxLength": 2000,
            },
            "bpm_practiced": {
                "type": "integer",
                "description": "Optional BPM of tracks worked on (0 = not specified)",
                "default": 0,
                "minimum": 0,
                "maximum": 300,
            },
            "key_practiced": {
                "type": "string",
                "description": "Optional musical key practiced (e.g. 'A minor', 'C# major')",
                "default": "",
                "examples": ["A minor", "C major", "F# minor", "Bb major"],
            },
        },
        "required": ["topic", "duration_minutes"],
    },
}

_CREATE_SESSION_NOTE_SCHEMA: dict[str, Any] = {
    "name": "create_session_note",
    "description": (
        "Save a musical discovery, idea, problem, or next step to the session knowledge journal. "
        "Use when the user says they discovered something, had an idea, wants to remember "
        "a technique, or has pending action items. Each note is tagged and searchable."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Type of note — determines how it is indexed and retrieved",
                "enum": ["discovery", "problem", "idea", "reference", "next_steps"],
                "examples": ["discovery", "next_steps"],
            },
            "title": {
                "type": "string",
                "description": "Short, descriptive title for the note (max 120 chars)",
                "minLength": 1,
                "maxLength": 120,
                "examples": ["Fast attack creates tight sidechain pump", "Finish stem export"],
            },
            "content": {
                "type": "string",
                "description": "Full note content with details (max 2000 chars)",
                "minLength": 1,
                "maxLength": 2000,
            },
            "tags": {
                "type": "array",
                "description": "Optional keyword tags for search and filtering",
                "items": {"type": "string", "minLength": 1, "maxLength": 50},
                "maxItems": 20,
                "default": [],
                "examples": [["sidechain", "attack", "compression"], ["arrangement", "stems"]],
            },
        },
        "required": ["category", "title", "content"],
    },
}

_ANALYZE_TRACK_SCHEMA: dict[str, Any] = {
    "name": "analyze_track",
    "description": (
        "Extract BPM, musical key, and energy level from an audio file. "
        "Uses librosa signal analysis when the file exists on disk, falls back "
        "to filename pattern matching otherwise. Use this when the user asks about "
        "track analysis, tempo detection, key identification, or wants to prepare "
        "a track for DJ mixing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": (
                    "Absolute path to an audio file (mp3, wav, flac, aiff, ogg, m4a) "
                    "or a filename string for filename-only pattern matching."
                ),
                "examples": [
                    "/Users/jd/Music/track_128bpm_Aminor.mp3",
                    "organic_house_124bpm.wav",
                    "/tmp/test.flac",
                ],
                "minLength": 1,
            },
            "analyze_audio": {
                "type": "boolean",
                "description": (
                    "Attempt audio signal analysis via librosa. "
                    "Set to false to use filename parsing only (faster, no file required)."
                ),
                "default": True,
            },
        },
        "required": ["file_path"],
    },
}

_SEARCH_PRODUCTION_KNOWLEDGE_SCHEMA: dict[str, Any] = {
    "name": "search_production_knowledge",
    "description": (
        "Search the music production knowledge base for techniques, tips, and tutorials. "
        "Queries the RAG vector store and returns grounded answers with citations from "
        "Pete Tong masterclass materials, YouTube transcripts, and production guides. "
        "Use this for 'how to' questions, technique explanations, mixing/mastering advice, "
        "and any music production question that requires knowledge base lookup."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language question about music production",
                "minLength": 3,
                "maxLength": 500,
                "examples": [
                    "How do I use sidechain compression for pumping?",
                    "What is parallel compression and when should I use it?",
                    "How to create tension in organic house arrangements?",
                ],
            },
            "top_k": {
                "type": "integer",
                "description": "Number of knowledge chunks to retrieve (more = richer context, slower)",
                "default": 5,
                "minimum": 1,
                "maximum": 20,
            },
            "confidence_threshold": {
                "type": "number",
                "description": (
                    "Minimum relevance score 0-1. Lower = more results but less precise. "
                    "0.58 is the recommended minimum for production queries."
                ),
                "default": 0.58,
                "minimum": 0.3,
                "maximum": 1.0,
            },
        },
        "required": ["query"],
    },
}

_SUGGEST_CHORD_PROGRESSION_SCHEMA: dict[str, Any] = {
    "name": "suggest_chord_progression",
    "description": (
        "Generate a musically coherent chord progression for a given key, genre, and mood. "
        "Produces chord names, Roman numeral analysis, voicing suggestions, and production tips. "
        "Use when the user asks for chord ideas, harmonic content, composition help, "
        "or wants to build a musical foundation for a track."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": (
                    "Musical key including mode (e.g. 'A minor', 'C# major', 'D dorian'). "
                    "Supports all 12 chromatic roots and major/minor/dorian/phrygian modes."
                ),
                "examples": ["A minor", "C major", "F# minor", "D dorian", "Bb major"],
                "minLength": 1,
            },
            "genre": {
                "type": "string",
                "description": "Music genre for stylistic context and voicing preferences",
                "default": "organic house",
                "enum": [
                    "acid",
                    "deep house",
                    "melodic house",
                    "organic house",
                    "progressive house",
                    "techno",
                ],
            },
            "mood": {
                "type": "string",
                "description": "Emotional quality of the progression",
                "default": "dark",
                "enum": [
                    "dark",
                    "dreamy",
                    "euphoric",
                    "neutral",
                    "tense",
                ],
            },
            "bars": {
                "type": "integer",
                "description": "Number of bars in the progression (affects chord repetition pattern)",
                "default": 8,
                "enum": [4, 8, 16],
            },
        },
        "required": ["key"],
    },
}

_SUGGEST_COMPATIBLE_TRACKS_SCHEMA: dict[str, Any] = {
    "name": "suggest_compatible_tracks",
    "description": (
        "Find tracks harmonically compatible for DJ mixing using the Camelot Wheel system. "
        "Returns keys that mix well: same Camelot position (energy shift), adjacent positions "
        "(key change), and relative major/minor (tonal shift). Optionally filters by BPM. "
        "Use for DJ set planning, harmonic mixing decisions, and track ordering."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Musical key to find compatible tracks for (e.g. 'A minor', 'C# major')",
                "examples": ["A minor", "G major", "F# minor", "Db major"],
                "minLength": 1,
            },
            "bpm": {
                "type": "number",
                "description": (
                    "Optional BPM for tempo-compatible suggestions. "
                    "0 = any tempo. Tolerance is ±6% of the reference BPM."
                ),
                "default": 0.0,
                "minimum": 0.0,
                "maximum": 300.0,
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of compatible keys to return",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
            },
        },
        "required": ["key"],
    },
}

# ---------------------------------------------------------------------------
# Schema registry
# ---------------------------------------------------------------------------

# All schemas indexed by tool name — single source of truth
_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "log_practice_session": _LOG_PRACTICE_SESSION_SCHEMA,
    "create_session_note": _CREATE_SESSION_NOTE_SCHEMA,
    "analyze_track": _ANALYZE_TRACK_SCHEMA,
    "search_production_knowledge": _SEARCH_PRODUCTION_KNOWLEDGE_SCHEMA,
    "suggest_chord_progression": _SUGGEST_CHORD_PROGRESSION_SCHEMA,
    "suggest_compatible_tracks": _SUGGEST_COMPATIBLE_TRACKS_SCHEMA,
}


def get_tool_schema(tool_name: str) -> dict[str, Any]:
    """
    Return the canonical JSON schema for a tool by name.

    Pure function — no I/O.

    Args:
        tool_name: Registered tool name

    Returns:
        Schema dict with keys: name, description, input_schema

    Raises:
        KeyError: If tool_name is not registered
    """
    if tool_name not in _TOOL_SCHEMAS:
        raise KeyError(f"No schema for tool {tool_name!r}. Known: {list(_TOOL_SCHEMAS)}")
    return _TOOL_SCHEMAS[tool_name]


def list_tool_names() -> list[str]:
    """
    Return sorted list of all registered tool names.

    Pure function — no I/O.

    Returns:
        Sorted list of tool name strings
    """
    return sorted(_TOOL_SCHEMAS.keys())


def validate_schema_structure(schema: dict[str, Any]) -> list[str]:
    """
    Validate that a schema dict has the expected top-level structure.

    Checks presence of required keys and basic type constraints.
    Does NOT validate against JSON Schema meta-schema (no external deps).

    Pure function — no I/O.

    Args:
        schema: Schema dict to validate

    Returns:
        List of error strings — empty list means valid
    """
    errors: list[str] = []

    if "name" not in schema:
        errors.append("missing 'name'")
    elif not isinstance(schema["name"], str) or not schema["name"]:
        errors.append("'name' must be a non-empty string")

    if "description" not in schema:
        errors.append("missing 'description'")
    elif not isinstance(schema["description"], str) or len(schema["description"]) < 20:
        errors.append("'description' must be at least 20 chars — be descriptive for the LLM")

    if "input_schema" not in schema:
        errors.append("missing 'input_schema'")
    else:
        inp = schema["input_schema"]
        if inp.get("type") != "object":
            errors.append("input_schema.type must be 'object'")
        if "properties" not in inp:
            errors.append("input_schema missing 'properties'")
        if "required" not in inp:
            errors.append("input_schema missing 'required' (use [] if no required params)")
        else:
            required = inp["required"]
            props = inp.get("properties", {})
            for r in required:
                if r not in props:
                    errors.append(f"required param {r!r} not in properties")

    return errors


def get_all_schemas() -> list[dict[str, Any]]:
    """
    Return all tool schemas as a list (Anthropic tool_use format compatible).

    Pure function — no I/O.

    Returns:
        List of all schema dicts, sorted by tool name
    """
    return [_TOOL_SCHEMAS[name] for name in sorted(_TOOL_SCHEMAS)]
