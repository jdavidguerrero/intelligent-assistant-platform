"""
Tool router — intent detection and tool dispatch for musical queries.

The router decides which tool(s) to call based on a user's query,
executes them, and returns structured results. This is the orchestrator
that connects user intent to the tool registry.

Design:
  - NO LLM calls for routing — uses keyword/intent pattern matching.
    This keeps routing fast, deterministic, and testable without API keys.
  - ToolResult from each tool is returned as-is — the caller (API layer)
    decides how to format or summarize results.
  - Multi-tool routing: a single query can trigger multiple tools.
    Results are returned in a list, ordered by tool call sequence.
  - Fallback: if no tool matches, returns None — caller should use RAG.

Intent detection strategy:
  Each intent has a primary signal set (high-confidence keywords) and
  optional secondary signals. A match on any primary signal triggers
  the tool. This is intentionally simple — avoid over-engineering
  what a well-designed tool description + LLM routing can handle.

Integration with /ask:
  Future step (Day 6) will integrate this router into the ask endpoint
  as a pre-RAG tool dispatch layer:
      query → ToolRouter.route() → tool results → inject into RAG context
  For now, the router is standalone and testable independently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from tools.base import ToolResult
from tools.registry import ToolRegistry, get_registry

# ---------------------------------------------------------------------------
# Intent patterns — pure keyword matching
# ---------------------------------------------------------------------------

# Each entry: (tool_name, primary_signals, param_extractor_key)
# primary_signals: frozenset of lowercase substrings to match against query
# Any match → intent fires

_INTENT_PATTERNS: list[tuple[str, frozenset[str]]] = [
    # log_practice_session: user reporting a session they did
    (
        "log_practice_session",
        frozenset(
            {
                "just finished",
                "i finished",
                "practiced",
                "i practiced",
                "spent",
                "i spent",
                "worked on",
                "i worked on",
                "session on",
                "did a session",
                "completed a session",
                "log my session",
                "log session",
                "save my session",
            }
        ),
    ),
    # create_session_note: user capturing an insight or idea
    (
        "create_session_note",
        frozenset(
            {
                "note that",
                "note this",
                "remember that",
                "save this",
                "discovered that",
                "discovered something",
                "i discovered",
                "realized that",
                "i realized",
                "learned that",
                "i learned",
                "tip:",
                "idea:",
                "found out",
                "i found out",
                "write down",
                "capture this",
                "insight:",
                "next steps",
                "action item",
                "todo:",
            }
        ),
    ),
    # analyze_track: user wants audio analysis
    (
        "analyze_track",
        frozenset(
            {
                "analyze",
                "analyse",
                "bpm of",
                "key of",
                "what key is",
                "what bpm is",
                "detect bpm",
                "detect key",
                "what's the bpm",
                "what is the bpm",
                "what's the key",
                "what is the key",
                "energy of",
                "tempo of",
            }
        ),
    ),
    # suggest_compatible_tracks: DJ set planning / harmonic mixing
    (
        "suggest_compatible_tracks",
        frozenset(
            {
                "compatible with",
                "mix with",
                "mix well with",
                "plays well with",
                "works with",
                "harmonic mix",
                "camelot",
                "what tracks",
                "what songs",
                "dj set",
                "next track",
                "transition from",
                "transition to",
                "after this track",
                "before this track",
            }
        ),
    ),
    # suggest_chord_progression: music theory / chord requests
    (
        "suggest_chord_progression",
        frozenset(
            {
                "chord progression",
                "chord sequence",
                "suggest chords",
                "chords for",
                "chords in",
                "give me chords",
                "chord ideas",
                "harmony",
                "harmonic progression",
                "what chords",
                "music theory",
                "generate chords",
            }
        ),
    ),
    # generate_midi_pattern: MIDI / pattern generation
    (
        "generate_midi_pattern",
        frozenset(
            {
                "midi",
                "generate pattern",
                "make a pattern",
                "create pattern",
                "piano roll",
                "midi file",
                "generate midi",
                "create midi",
                "make midi",
                "musical pattern",
            }
        ),
    ),
    # search_by_genre: genre-specific knowledge search
    (
        "search_by_genre",
        frozenset(
            {
                "organic house",
                "melodic house",
                "techno",
                "deep house",
                "progressive house",
                "how to make",
                "production technique",
                "tutorials for",
                "lessons on",
                "how do i make",
                "how do producers",
                "genre style",
                "production style",
            }
        ),
    ),
    # extract_style_from_context: artist style analysis
    (
        "extract_style_from_context",
        frozenset(
            {
                "style of",
                "in the style of",
                "like",  # "like sebastien leger"
                "sound like",
                "sounds like",
                "inspired by",
                "based on",
                "artist style",
                "producer style",
                "production style of",
            }
        ),
    ),
]

# ---------------------------------------------------------------------------
# Parameter extraction — heuristic extraction of common params from text
# ---------------------------------------------------------------------------


def _extract_duration_minutes(query: str) -> int | None:
    """Extract duration in minutes from natural language."""
    patterns = [
        r"(\d+)[- ]hour",
        r"(\d+)[- ]hr",
        r"(\d+)\s*h\b",
        r"(\d+)[- ]minute",
        r"(\d+)[- ]min\b",
        r"(\d+)\s*hours?\b",
        r"(\d+)\s*minutes?\b",
    ]
    for i, pattern in enumerate(patterns):
        match = re.search(pattern, query.lower())
        if match:
            value = int(match.group(1))
            # Convert hours to minutes for first 3 patterns
            if i < 3:
                value *= 60
            return value
    return None


def _extract_topic(query: str) -> str | None:
    """Extract practice topic from session-logging queries."""
    patterns = [
        r"session (?:on|about|of) (.+?)(?:\.|,|!|\?|$)",
        r"practiced (.+?)(?:\.|,|!|\?|$)",
        r"working on (.+?)(?:\.|,|!|\?|$)",
        r"worked on (.+?)(?:\.|,|!|\?|$)",
        r"spent \d+ \w+ (?:on|doing) (.+?)(?:\.|,|!|\?|$)",
        r"finished (?:a |an )?(\w[\w\s]+?) session",
    ]
    for pattern in patterns:
        match = re.search(pattern, query.lower())
        if match:
            topic = match.group(1).strip()
            if 2 < len(topic) < 100:
                return topic
    return None


def _extract_key_from_query(query: str) -> str | None:
    """Extract musical key from query text."""
    pattern = re.compile(
        r"\b([A-G][#b]?\s+(?:major|minor|dorian|phrygian|lydian|mixolydian))\b",
        re.IGNORECASE,
    )
    match = pattern.search(query)
    if match:
        raw = match.group(1).strip()
        # Normalize: "a minor" → "A minor"
        parts = raw.split()
        return parts[0].upper() + (" " + " ".join(parts[1:]) if len(parts) > 1 else "")
    return None


def _extract_bpm_from_query(query: str) -> float | None:
    """Extract BPM from query text."""
    pattern = re.compile(r"\b(\d{2,3}(?:\.\d)?)\s*bpm\b", re.IGNORECASE)
    match = pattern.search(query)
    if match:
        value = float(match.group(1))
        if 60 <= value <= 220:
            return value
    return None


def _extract_genre_from_query(query: str) -> str | None:
    """Extract genre name from query text."""
    from tools.music.theory import GENRE_PROGRESSIONS

    query_lower = query.lower()
    for genre in GENRE_PROGRESSIONS.keys():
        if genre in query_lower:
            return genre
    return None


def _extract_artist_from_query(query: str) -> str | None:
    """Extract artist name from style-query patterns."""
    patterns = [
        r"style of ([A-Z][a-zA-Z\s.]+?)(?:\s+in|\s+for|\s*$|\.|,)",
        r"like ([A-Z][a-zA-Z\s.]+?)(?:\s+style|\s+music|\s+sound|\s*$|\.|,)",
        r"inspired by ([A-Z][a-zA-Z\s.]+?)(?:\s+style|\s+music|\s+sound|\s*$|\.|,)",
        r"([A-Z][a-zA-Z\s.]+?) style",
    ]
    for pattern in patterns:
        match = re.search(pattern, query)
        if match:
            artist = match.group(1).strip()
            if 2 < len(artist) < 60:
                return artist
    return None


# ---------------------------------------------------------------------------
# RouteResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteResult:
    """
    Result of routing a query to one or more tools.

    Attributes:
        matched_tools:   Names of tools that were called
        tool_results:    ToolResult for each matched tool (same order)
        params_used:     Extracted params passed to each tool (for debugging)
        fallback_to_rag: True if no tool matched — caller should use RAG
        query:           Original query that was routed
    """

    matched_tools: tuple[str, ...]
    tool_results: tuple[ToolResult, ...]
    params_used: tuple[dict, ...]
    fallback_to_rag: bool
    query: str


# ---------------------------------------------------------------------------
# ToolRouter
# ---------------------------------------------------------------------------


class ToolRouter:
    """
    Routes user queries to appropriate musical tools.

    Uses keyword-based intent detection to identify which tool(s) should
    handle a query, extracts parameters from natural language, and executes
    the tools. Returns structured RouteResult for the caller to use.

    Design goals:
      - Deterministic: same query → same routing decision (no LLM needed)
      - Testable: pure intent detection, mockable tool execution
      - Composable: multiple tools can fire on a single query
      - Graceful: unknown queries fall back to RAG (fallback_to_rag=True)

    Example:
        router = ToolRouter()
        result = router.route("I just finished a 2-hour session on bass design")
        # → matched_tools=("log_practice_session",)
        # → tool_results=(ToolResult(success=True, data={...}),)
        # → fallback_to_rag=False
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        """
        Args:
            registry: Tool registry to use. Defaults to global registry.
                      Inject a test registry to isolate routing tests.
        """
        self._registry = registry

    def _get_registry(self) -> ToolRegistry:
        if self._registry is not None:
            return self._registry
        return get_registry()

    def detect_intents(self, query: str) -> list[str]:
        """
        Identify which tools should handle a query.

        Pure function — no tool execution, no I/O.

        Args:
            query: User query string

        Returns:
            List of tool names that match (may be empty)
        """
        query_lower = query.lower()
        matched: list[str] = []

        for tool_name, signals in _INTENT_PATTERNS:
            for signal in signals:
                if signal in query_lower:
                    if tool_name not in matched:
                        matched.append(tool_name)
                    break

        return matched

    def extract_params(self, tool_name: str, query: str) -> dict[str, Any]:
        """
        Extract tool parameters from natural language query.

        Pure function — no tool execution, no I/O.

        Args:
            tool_name: Name of the tool to extract params for
            query: User query string

        Returns:
            Dict of extracted params (may be partial — tool validates remaining)
        """
        params: dict[str, Any] = {}

        if tool_name == "log_practice_session":
            topic = _extract_topic(query)
            if topic:
                params["topic"] = topic
            duration = _extract_duration_minutes(query)
            if duration:
                params["duration_minutes"] = duration

        elif tool_name == "create_session_note":
            # Detect category from keywords
            query_lower = query.lower()
            if any(kw in query_lower for kw in ("discovered", "realized", "learned", "found out")):
                params["category"] = "discovery"
            elif any(kw in query_lower for kw in ("idea", "concept", "try", "explore")):
                params["category"] = "idea"
            elif any(kw in query_lower for kw in ("next steps", "action item", "todo")):
                params["category"] = "next_steps"
            elif any(kw in query_lower for kw in ("problem", "issue", "bug", "fixed")):
                params["category"] = "problem"
            else:
                params["category"] = "reference"

        elif tool_name == "analyze_track":
            # File path extraction (simple heuristic: last token ending in audio ext)
            audio_exts = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".ogg", ".m4a"}
            for token in query.split():
                if any(token.lower().endswith(ext) for ext in audio_exts):
                    params["file_path"] = token
                    break

        elif tool_name == "suggest_compatible_tracks":
            key = _extract_key_from_query(query)
            if key:
                params["key"] = key
            bpm = _extract_bpm_from_query(query)
            if bpm:
                params["bpm"] = bpm

        elif tool_name == "suggest_chord_progression":
            key = _extract_key_from_query(query)
            if key:
                params["key"] = key
            genre = _extract_genre_from_query(query)
            if genre:
                params["genre"] = genre

        elif tool_name == "generate_midi_pattern":
            bpm = _extract_bpm_from_query(query)
            if bpm:
                params["bpm"] = bpm
            genre = _extract_genre_from_query(query)
            if genre:
                params["style"] = genre

        elif tool_name == "search_by_genre":
            genre = _extract_genre_from_query(query)
            if genre:
                params["genre"] = genre
            params["query"] = query

        elif tool_name == "extract_style_from_context":
            artist = _extract_artist_from_query(query)
            if artist:
                params["artist"] = artist
            genre = _extract_genre_from_query(query)
            if genre:
                params["genre_hint"] = genre

        return params

    def route(
        self,
        query: str,
        extra_params: dict[str, Any] | None = None,
    ) -> RouteResult:
        """
        Route a query to matching tools and execute them.

        Args:
            query: User query string
            extra_params: Additional params to merge into extracted params
                          (e.g., file_path already known from context).
                          Keys are tool_name → {param: value}.

        Returns:
            RouteResult with tool results and fallback flag
        """
        if not query or not query.strip():
            return RouteResult(
                matched_tools=(),
                tool_results=(),
                params_used=(),
                fallback_to_rag=True,
                query=query,
            )

        registry = self._get_registry()
        matched_names = self.detect_intents(query)

        if not matched_names:
            return RouteResult(
                matched_tools=(),
                tool_results=(),
                params_used=(),
                fallback_to_rag=True,
                query=query,
            )

        tool_results: list[ToolResult] = []
        params_list: list[dict] = []
        called_names: list[str] = []

        for tool_name in matched_names:
            tool = registry.get(tool_name)
            if tool is None:
                # Tool not in registry — skip silently
                continue

            # Extract params from query
            params = self.extract_params(tool_name, query)

            # Merge extra_params if provided for this tool
            if extra_params and tool_name in extra_params:
                params.update(extra_params[tool_name])

            # Execute tool
            result = tool(**params)

            tool_results.append(result)
            params_list.append(params)
            called_names.append(tool_name)

        if not called_names:
            return RouteResult(
                matched_tools=(),
                tool_results=(),
                params_used=(),
                fallback_to_rag=True,
                query=query,
            )

        return RouteResult(
            matched_tools=tuple(called_names),
            tool_results=tuple(tool_results),
            params_used=tuple(params_list),
            fallback_to_rag=False,
            query=query,
        )

    def describe_tools(self) -> list[dict]:
        """
        Return tool descriptions for LLM tool_use API.

        Formats all registered tools in the schema expected by
        Claude's tool_use API (name, description, input_schema).

        Returns:
            List of tool definition dicts ready for Anthropic tool_use API
        """
        registry = self._get_registry()
        tools = []
        for tool_dict in registry.list_tools():
            # Convert to Anthropic tool_use schema
            properties = {}
            required = []
            for param in tool_dict["parameters"]:
                prop: dict[str, Any] = {"description": param["description"]}
                # Map Python types to JSON Schema types
                type_map = {
                    "str": "string",
                    "int": "integer",
                    "float": "number",
                    "bool": "boolean",
                    "list": "array",
                }
                prop["type"] = type_map.get(param["type"], "string")
                properties[param["name"]] = prop
                if param["required"]:
                    required.append(param["name"])

            tools.append(
                {
                    "name": tool_dict["name"],
                    "description": tool_dict["description"],
                    "input_schema": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                }
            )
        return tools
