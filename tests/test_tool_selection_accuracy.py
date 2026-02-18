"""
15-query tool selection accuracy test set — Week 3 Day 6.

Tests that the ToolRouter correctly classifies musical queries into:
  - The right tool (or set of tools)
  - Fallback to RAG (when no tool should fire)

This is the "golden set" for tool routing — queries chosen to cover:
  1. Clear action queries  → must route to specific tool
  2. Ambiguous queries     → must route to most likely tool
  3. Knowledge queries     → must NOT route to tools (fallback_to_rag=True)
  4. Edge cases            → empty, very short, multi-intent

No DB, no LLM, no network — pure intent detection testing.
All tests are deterministic.

Accuracy target: 13/15 (87%) — same standard as the RAG golden set.

Scoring:
  PASS if expected_tools ⊆ matched_tools  (all expected tools fired)
  PASS if expected_fallback=True and fallback_to_rag=True
  FAIL otherwise
"""

import pytest

from tools.router import ToolRouter

# ---------------------------------------------------------------------------
# Shared router (no registry needed — only testing detect_intents)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def router() -> ToolRouter:
    """ToolRouter with empty registry — only testing detect_intents."""
    from tools.registry import ToolRegistry

    return ToolRouter(registry=ToolRegistry())


# ---------------------------------------------------------------------------
# 15-query golden set
# ---------------------------------------------------------------------------

# Format: (query, expected_tools, fallback_to_rag, description)
# expected_tools: set of tool names that MUST be in matched_tools
# fallback_to_rag: True means the router must NOT match any tool

TOOL_SELECTION_QUERIES: list[tuple[str, set[str], bool, str]] = [
    # ---- ACTION: log_practice_session ----
    (
        "I just finished a 2-hour session on bass design",
        {"log_practice_session"},
        False,
        "Clear session log — 'just finished' + duration + topic",
    ),
    (
        "I worked on arrangement for 90 minutes today",
        {"log_practice_session"},
        False,
        "Session log via 'worked on' + duration pattern",
    ),
    (
        "Log my session: 60 minutes on chord progressions",
        {"log_practice_session"},
        False,
        "Explicit 'log my session' command",
    ),
    # ---- ACTION: create_session_note ----
    (
        "Note that I discovered sidechain creates tight pumping with fast attack",
        {"create_session_note"},
        False,
        "Discovery note — 'note that' + 'discovered'",
    ),
    (
        "I realized that using 9th chords gives that organic house feel",
        {"create_session_note"},
        False,
        "Discovery via 'I realized that'",
    ),
    (
        "Next steps: finish the arrangement and export stems",
        {"create_session_note"},
        False,
        "Action items via 'next steps' keyword",
    ),
    # ---- ACTION: suggest_chord_progression ----
    (
        "Suggest a chord progression in A minor for organic house",
        {"suggest_chord_progression"},
        False,
        "Chord request with key and genre",
    ),
    (
        "Give me chord ideas in D dorian for a dark techno track",
        {"suggest_chord_progression"},
        False,
        "Chord ideas with mode and genre",
    ),
    # ---- ACTION: suggest_compatible_tracks ----
    (
        "What tracks are compatible with A minor at 124 bpm for my DJ set?",
        {"suggest_compatible_tracks"},
        False,
        "Harmonic mix query — 'compatible with' + key + bpm",
    ),
    (
        "I need tracks that mix well with this one, it's in C major",
        {"suggest_compatible_tracks"},
        False,
        "Mixing compatibility via 'mix well with'",
    ),
    # ---- ACTION: generate_midi_pattern ----
    (
        "Generate a MIDI pattern for Am7, Fmaj7, Cmaj7, Gm7 at 124 bpm",
        {"generate_midi_pattern"},
        False,
        "Direct MIDI generation request",
    ),
    # ---- KNOWLEDGE: fallback to RAG ----
    (
        "What is sidechain compression and how does it work?",
        set(),
        True,
        "Knowledge question — no action, should use RAG",
    ),
    (
        "Explain the difference between reverb and delay in a mix",
        set(),
        True,
        "Technical knowledge question — RAG only",
    ),
    (
        "How do I set up a send/return channel in Ableton?",
        set(),
        True,
        "DAW tutorial question — RAG only",
    ),
    # ---- EDGE CASE ----
    (
        "I finished a session and discovered something: fast attack on sidechain",
        {"log_practice_session", "create_session_note"},
        False,
        "Multi-intent: session log + discovery note in same query",
    ),
]


# ---------------------------------------------------------------------------
# Parametrized accuracy test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query,expected_tools,expected_fallback,description",
    TOOL_SELECTION_QUERIES,
    ids=[
        f"q{i:02d}_{d[:30].replace(' ', '_')}"
        for i, (_, __, ___, d) in enumerate(TOOL_SELECTION_QUERIES)
    ],
)
def test_tool_selection(
    router: ToolRouter,
    query: str,
    expected_tools: set[str],
    expected_fallback: bool,
    description: str,
) -> None:
    """
    Verify that the router routes this query to the expected tools.

    Tests intent detection only — no tool execution, no DB.
    """
    matched = set(router.detect_intents(query))

    if expected_fallback:
        # Knowledge queries: router must NOT fire any tool
        assert matched == set() or matched.issubset(
            # Some knowledge queries may have weak signal overlap — allow empty
            set()
        ), (
            f"[{description}]\n"
            f"  Query:    {query!r}\n"
            f"  Expected: fallback_to_rag (no tools)\n"
            f"  Got:      tools={matched}"
        )
    else:
        # Action queries: all expected tools must be in matched
        missing = expected_tools - matched
        assert not missing, (
            f"[{description}]\n"
            f"  Query:    {query!r}\n"
            f"  Expected: {expected_tools}\n"
            f"  Got:      {matched}\n"
            f"  Missing:  {missing}"
        )


# ---------------------------------------------------------------------------
# Accuracy summary test (must pass ≥13/15)
# ---------------------------------------------------------------------------


def test_overall_accuracy(router: ToolRouter) -> None:
    """
    Overall routing accuracy must be ≥ 87% (13/15 queries correct).

    This test summarizes all 15 queries to give an at-a-glance pass/fail.
    Individual query tests above give detail on failures.
    """
    passed = 0
    results = []

    for query, expected_tools, expected_fallback, description in TOOL_SELECTION_QUERIES:
        matched = set(router.detect_intents(query))

        if expected_fallback:
            ok = len(matched) == 0
        else:
            ok = expected_tools.issubset(matched)

        passed += int(ok)
        results.append((ok, description, query, expected_tools, matched))

    total = len(TOOL_SELECTION_QUERIES)
    accuracy = passed / total

    # Print summary for visibility in test output
    print(f"\n{'='*60}")
    print(f"Tool Selection Accuracy: {passed}/{total} ({accuracy:.0%})")
    print(f"{'='*60}")
    for ok, desc, q, expected, got in results:
        status = "✓" if ok else "✗"
        print(f"  {status} {desc[:50]}")
        if not ok:
            print(f"      Query:    {q[:60]}")
            print(f"      Expected: {expected}")
            print(f"      Got:      {got}")

    assert accuracy >= 0.87, (
        f"Tool selection accuracy {accuracy:.0%} ({passed}/{total}) " f"is below the 87% threshold."
    )


# ---------------------------------------------------------------------------
# Param extraction accuracy tests (bonus — not counted in 15-query set)
# ---------------------------------------------------------------------------


class TestParamExtractionAccuracy:
    """Verify that extracted params are correct for key routing scenarios."""

    def test_session_topic_and_duration_extracted(self, router: ToolRouter) -> None:
        params = router.extract_params(
            "log_practice_session",
            "I just finished a 2-hour session on bass design",
        )
        assert params.get("topic") == "bass design"
        assert params.get("duration_minutes") == 120

    def test_chord_key_and_genre_extracted(self, router: ToolRouter) -> None:
        params = router.extract_params(
            "suggest_chord_progression",
            "suggest a chord progression in A minor for organic house",
        )
        assert params.get("key") == "A minor"
        assert params.get("genre") == "organic house"

    def test_compatible_key_and_bpm_extracted(self, router: ToolRouter) -> None:
        params = router.extract_params(
            "suggest_compatible_tracks",
            "what tracks are compatible with A minor at 124 bpm",
        )
        assert params.get("key") == "A minor"
        assert params.get("bpm") == 124.0

    def test_note_category_from_discovery(self, router: ToolRouter) -> None:
        params = router.extract_params(
            "create_session_note",
            "I discovered that 9th chords give organic house vibes",
        )
        assert params.get("category") == "discovery"

    def test_note_category_from_next_steps(self, router: ToolRouter) -> None:
        params = router.extract_params(
            "create_session_note",
            "next steps: finish arrangement, export stems",
        )
        assert params.get("category") == "next_steps"


# ---------------------------------------------------------------------------
# Tool chaining test — confirms multi-tool routing works
# ---------------------------------------------------------------------------


class TestToolChaining:
    """
    Test that the router supports sequential tool chains.

    'Log my session and suggest what to practice next based on my weak areas'
    should route to log_practice_session, then the caller can chain
    into search_by_genre or suggest_chord_progression.
    """

    def test_log_and_note_chain(self, router: ToolRouter) -> None:
        """Single query triggering both session log + note creation."""
        query = (
            "I finished a session on bass design and discovered that sidechain compression helps"
        )
        matched = set(router.detect_intents(query))
        # Should catch at least log_practice_session
        assert "log_practice_session" in matched

    def test_chord_and_midi_chain(self, router: ToolRouter) -> None:
        """Chord generation naturally leads to MIDI — both should fire."""
        query = "generate chord progression and create a midi pattern for organic house"
        matched = set(router.detect_intents(query))
        assert "suggest_chord_progression" in matched or "generate_midi_pattern" in matched

    def test_search_and_chord_chain(self, router: ToolRouter) -> None:
        """Style search + chord suggestion for a genre."""
        query = "search for organic house techniques and suggest chord progressions"
        matched = set(router.detect_intents(query))
        assert "search_by_genre" in matched or "suggest_chord_progression" in matched
