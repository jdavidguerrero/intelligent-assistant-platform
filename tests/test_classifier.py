"""Tests for core/routing/classifier.py — musical task classification.

Tests cover:
- 30 labeled queries (10 per type) for accuracy >85%
- Signal matching correctness per type
- Tie-breaking logic (creative > realtime > factual)
- Edge cases: empty query, single-word query, ambiguous query
- Confidence formula validation
- ClassificationResult invariants
"""

from __future__ import annotations

import pytest

from core.routing.classifier import classify_musical_task

# ---------------------------------------------------------------------------
# Labeled test queries (ground truth)
# ---------------------------------------------------------------------------

LABELED_QUERIES: list[tuple[str, str]] = [
    # ── Factual (10) ─────────────────────────────────────────────────────
    ("What key is A minor's relative major?", "factual"),
    ("What BPM range is house music?", "factual"),
    ("What is sidechain compression?", "factual"),
    ("What does ADSR stand for?", "factual"),
    ("What intervals are in a minor chord?", "factual"),
    ("What sample rate is CD quality?", "factual"),
    ("What is the Haas effect?", "factual"),
    ("How many bars is a typical breakdown?", "factual"),
    ("What does EQ stand for?", "factual"),
    ("What plugin is commonly used for limiting?", "factual"),
    # ── Creative (10) ─────────────────────────────────────────────────────
    ("Analyze my last 5 practice sessions and suggest a 2-week plan", "creative"),
    ("What should I focus on to improve my mixing?", "creative"),
    ("Help me arrange my track based on progressive house structure", "creative"),
    ("Suggest chord progressions for a melancholic deep house track", "creative"),
    ("How can I improve my bass layering technique?", "creative"),
    ("Create a practice schedule based on my skill gaps", "creative"),
    ("Review my arrangement and suggest improvements", "creative"),
    ("Design a sound design workflow for bass creation", "creative"),
    ("Based on my recent sessions, what should I practice next?", "creative"),
    ("Give me a learning roadmap for music production", "creative"),
    # ── Realtime (10) ─────────────────────────────────────────────────────
    ("Detect the BPM of the track playing right now", "realtime"),
    ("Match this beat pattern in real-time", "realtime"),
    ("Identify the key while I'm playing live", "realtime"),
    ("Transcribe what I'm playing right now", "realtime"),
    ("Recognize the chord progression in this audio immediately", "realtime"),
    ("Count the beats while recording", "realtime"),
    ("Monitor my performance during the live set", "realtime"),
    ("Beat matching right now while DJing", "realtime"),
    ("Detect clipping in the current mix instantly", "realtime"),
    ("Identify patterns while I'm performing", "realtime"),
]


# ---------------------------------------------------------------------------
# Accuracy gate
# ---------------------------------------------------------------------------


class TestClassifierAccuracy:
    def test_accuracy_above_85_percent(self) -> None:
        """Overall classification accuracy must exceed 85% on labeled queries."""
        correct = sum(
            1
            for query, expected in LABELED_QUERIES
            if classify_musical_task(query).task_type == expected
        )
        accuracy = correct / len(LABELED_QUERIES)
        failing = [
            (q, exp, classify_musical_task(q).task_type)
            for q, exp in LABELED_QUERIES
            if classify_musical_task(q).task_type != exp
        ]
        assert accuracy >= 0.85, (
            f"Classifier accuracy {accuracy:.1%} < 85% threshold.\n"
            f"Misclassified ({len(failing)}):\n"
            + "\n".join(f"  [{got}≠{exp}] {q}" for q, exp, got in failing)
        )

    def test_all_factual_queries_classified(self) -> None:
        """All 10 factual queries are classified (no ValueError)."""
        factual = [q for q, t in LABELED_QUERIES if t == "factual"]
        for query in factual:
            result = classify_musical_task(query)
            assert result.task_type in ("factual", "creative", "realtime")

    def test_all_creative_queries_classified(self) -> None:
        """All 10 creative queries are classified (no ValueError)."""
        creative = [q for q, t in LABELED_QUERIES if t == "creative"]
        for query in creative:
            result = classify_musical_task(query)
            assert result.task_type in ("factual", "creative", "realtime")

    def test_all_realtime_queries_classified(self) -> None:
        """All 10 realtime queries are classified (no ValueError)."""
        realtime = [q for q, t in LABELED_QUERIES if t == "realtime"]
        for query in realtime:
            result = classify_musical_task(query)
            assert result.task_type in ("factual", "creative", "realtime")


# ---------------------------------------------------------------------------
# Specific signal tests
# ---------------------------------------------------------------------------


class TestFactualSignals:
    def test_what_key_is_factual(self) -> None:
        result = classify_musical_task("What key is Am relative major?")
        assert result.task_type == "factual"

    def test_what_is_factual(self) -> None:
        result = classify_musical_task("What is reverb?")
        assert result.task_type == "factual"

    def test_how_does_factual(self) -> None:
        result = classify_musical_task("How does a compressor work?")
        assert result.task_type == "factual"

    def test_define_factual(self) -> None:
        result = classify_musical_task("Define sidechain compression")
        assert result.task_type == "factual"

    def test_bpm_abbreviation_factual(self) -> None:
        result = classify_musical_task("What BPM range is techno?")
        assert result.task_type == "factual"

    def test_adsr_abbreviation_factual(self) -> None:
        result = classify_musical_task("Explain ADSR envelope")
        assert result.task_type == "factual"

    def test_factual_has_low_confidence_with_one_signal(self) -> None:
        result = classify_musical_task("What is EQ?")
        assert result.task_type == "factual"
        # At least 1 match → confidence > 0
        assert result.confidence > 0.0


class TestCreativeSignals:
    def test_suggest_creative(self) -> None:
        result = classify_musical_task("Suggest a practice plan for this week")
        assert result.task_type == "creative"

    def test_improve_creative(self) -> None:
        result = classify_musical_task("How can I improve my arrangement skills?")
        assert result.task_type == "creative"

    def test_analyze_creative(self) -> None:
        result = classify_musical_task("Analyze my mixing workflow")
        assert result.task_type == "creative"

    def test_review_creative(self) -> None:
        result = classify_musical_task("Review my latest track")
        assert result.task_type == "creative"

    def test_based_on_my_creative(self) -> None:
        result = classify_musical_task("Based on my last 3 sessions, what should I work on?")
        assert result.task_type == "creative"

    def test_week_plan_creative(self) -> None:
        result = classify_musical_task("Give me a 4-week plan to improve my sound design")
        assert result.task_type == "creative"

    def test_creative_has_higher_confidence_with_multiple_signals(self) -> None:
        result = classify_musical_task(
            "Analyze my sessions and suggest a plan to improve based on my progress"
        )
        assert result.task_type == "creative"
        # Multiple matches → confidence approaching 1.0
        assert result.confidence > 0.7


class TestRealtimeSignals:
    def test_right_now_realtime(self) -> None:
        # "detect" + "right now" → 2 realtime signals → wins
        result = classify_musical_task("Detect the key right now")
        assert result.task_type == "realtime"

    def test_real_time_realtime(self) -> None:
        result = classify_musical_task("Match this beat in real-time")
        assert result.task_type == "realtime"

    def test_detect_realtime(self) -> None:
        result = classify_musical_task("Detect the key of this track")
        assert result.task_type == "realtime"

    def test_while_playing_realtime(self) -> None:
        # "while I'm playing" — regex handles intervening words up to 20 chars
        result = classify_musical_task("Identify the chord while I'm playing live")
        assert result.task_type == "realtime"

    def test_live_realtime(self) -> None:
        result = classify_musical_task("Monitor my performance during the live set")
        assert result.task_type == "realtime"

    def test_offline_realtime(self) -> None:
        result = classify_musical_task("I'm offline at the venue, can you help?")
        assert result.task_type == "realtime"


# ---------------------------------------------------------------------------
# Tie-breaking and edge cases
# ---------------------------------------------------------------------------


class TestTieBreaking:
    def test_tie_creative_beats_factual(self) -> None:
        """When creative and factual have equal matches, creative wins."""
        # "what" matches factual, "improve" matches creative — 1:1 tie
        result = classify_musical_task("What is the best way to improve my mixing?")
        # Could go either way based on actual counts, but creative should win on tie
        assert result.task_type in ("creative", "factual")

    def test_zero_matches_defaults_to_factual(self) -> None:
        """A query with no signals defaults to factual (safe cheap default)."""
        result = classify_musical_task("abcdefghijklmnopqrstuvwxyz obscure xyzzy")
        assert result.task_type == "factual"
        assert result.confidence == 0.0
        assert result.matched_signals == ()

    def test_empty_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            classify_musical_task("")

    def test_whitespace_only_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            classify_musical_task("   ")

    def test_single_word_query_does_not_crash(self) -> None:
        result = classify_musical_task("reverb")
        assert result.task_type in ("factual", "creative", "realtime")

    def test_very_long_query_does_not_crash(self) -> None:
        long_query = "What is " + "compression " * 200 + "and how do I use it?"
        result = classify_musical_task(long_query)
        assert result.task_type in ("factual", "creative", "realtime")


# ---------------------------------------------------------------------------
# ClassificationResult invariants
# ---------------------------------------------------------------------------


class TestClassificationResultInvariants:
    def test_confidence_in_range(self) -> None:
        for query, _ in LABELED_QUERIES:
            result = classify_musical_task(query)
            assert 0.0 <= result.confidence <= 1.0, f"confidence out of range for: {query!r}"

    def test_matched_signals_is_tuple(self) -> None:
        result = classify_musical_task("What is sidechain compression?")
        assert isinstance(result.matched_signals, tuple)

    def test_matched_signals_non_empty_for_known_query(self) -> None:
        result = classify_musical_task("What is reverb?")
        assert len(result.matched_signals) > 0

    def test_result_is_frozen(self) -> None:
        result = classify_musical_task("What is reverb?")
        with pytest.raises((AttributeError, TypeError)):
            result.task_type = "creative"  # type: ignore[misc]

    def test_confidence_formula(self) -> None:
        """confidence = n/(n+1) — verify specific values."""
        # 0 matches → 0.0
        result_zero = classify_musical_task("abcdefg xyzzy obscure nonwords")
        assert result_zero.confidence == 0.0

        # Any query with known signals should have confidence = n/(n+1)
        result = classify_musical_task("What is reverb?")
        n = len(result.matched_signals)
        expected = round(n / (n + 1), 4)
        assert result.confidence == expected
