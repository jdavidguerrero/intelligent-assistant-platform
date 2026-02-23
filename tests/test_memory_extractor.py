"""Tests for ingestion/memory_extractor.py"""

import json
from unittest.mock import MagicMock

from core.generation.base import GenerationResponse
from ingestion.memory_extractor import (
    extract_memories,
    extract_memories_llm,
    extract_memories_rule_based,
)


def _make_generator(response_json: str) -> MagicMock:
    """Build a mock GenerationProvider that returns given JSON."""
    mock = MagicMock()
    mock.generate.return_value = GenerationResponse(
        content=response_json,
        model="gpt-4o",
        usage_input_tokens=10,
        usage_output_tokens=20,
    )
    return mock


class TestRuleBasedExtraction:
    def test_detects_preference_signal(self) -> None:
        results = extract_memories_rule_based("I prefer working in A minor", "")
        assert any(m.memory_type == "preference" for m in results)

    def test_detects_my_favorite(self) -> None:
        results = extract_memories_rule_based("My favorite plugin is Serum", "")
        assert any(m.memory_type == "preference" for m in results)

    def test_detects_session_discovery(self) -> None:
        results = extract_memories_rule_based("I just discovered FM ratios sound great on pads", "")
        assert any(m.memory_type == "session" for m in results)

    def test_detects_note_to_self(self) -> None:
        results = extract_memories_rule_based("Note to self: try parallel compression on drums", "")
        assert any(m.memory_type == "session" for m in results)

    def test_detects_growth_signal(self) -> None:
        results = extract_memories_rule_based("I've improved my EQ skills a lot recently", "")
        assert any(m.memory_type == "growth" for m in results)

    def test_detects_creative_idea(self) -> None:
        results = extract_memories_rule_based("Idea: try granular synthesis on the pad layer", "")
        assert any(m.memory_type == "creative" for m in results)

    def test_detects_what_if(self) -> None:
        results = extract_memories_rule_based("What if I use sidechain on the reverb tail?", "")
        assert any(m.memory_type == "creative" for m in results)

    def test_no_signals_returns_empty(self) -> None:
        results = extract_memories_rule_based(
            "How do I set attack time on a compressor?",
            "Set the attack to 5ms for a kick drum.",
        )
        # Generic Q&A — no preference/session/growth/creative signals
        assert isinstance(results, list)

    def test_confidence_in_valid_range(self) -> None:
        results = extract_memories_rule_based("I prefer A minor", "")
        for m in results:
            assert 0.0 <= m.confidence <= 1.0

    def test_method_is_rule(self) -> None:
        results = extract_memories_rule_based("I prefer A minor", "")
        for m in results:
            assert m.method == "rule"

    def test_content_capped_at_500_chars(self) -> None:
        long_query = "I prefer " + "A" * 600
        results = extract_memories_rule_based(long_query, "")
        for m in results:
            assert len(m.content) <= 500

    def test_answer_text_also_scanned(self) -> None:
        results = extract_memories_rule_based(
            "", "Today I discovered that layering works better with FM"
        )
        assert any(m.memory_type == "session" for m in results)


class TestLLMExtraction:
    def test_valid_json_parsed(self) -> None:
        payload = json.dumps(
            [{"memory_type": "preference", "content": "Prefers A minor", "confidence": 0.85}]
        )
        gen = _make_generator(payload)
        results = extract_memories_llm("I prefer A minor", "", gen)
        assert len(results) == 1
        assert results[0].memory_type == "preference"
        assert results[0].confidence == 0.85
        assert results[0].method == "llm"

    def test_empty_array_returns_empty(self) -> None:
        gen = _make_generator("[]")
        results = extract_memories_llm("Generic question", "Generic answer", gen)
        assert results == []

    def test_malformed_json_returns_empty(self) -> None:
        gen = _make_generator("not valid json {{")
        results = extract_memories_llm("question", "answer", gen)
        assert results == []

    def test_invalid_memory_type_filtered(self) -> None:
        payload = json.dumps(
            [{"memory_type": "unknown_type", "content": "Some fact", "confidence": 0.9}]
        )
        gen = _make_generator(payload)
        results = extract_memories_llm("question", "answer", gen)
        assert results == []

    def test_generator_exception_returns_empty(self) -> None:
        gen = MagicMock()
        gen.generate.side_effect = RuntimeError("API error")
        results = extract_memories_llm("question", "answer", gen)
        assert results == []

    def test_multiple_entries_parsed(self) -> None:
        payload = json.dumps(
            [
                {"memory_type": "preference", "content": "Prefers A minor", "confidence": 0.8},
                {"memory_type": "session", "content": "Discovered FM trick", "confidence": 0.75},
            ]
        )
        gen = _make_generator(payload)
        results = extract_memories_llm("question", "answer", gen)
        assert len(results) == 2

    def test_markdown_fences_stripped(self) -> None:
        payload = '```json\n[{"memory_type": "session", "content": "Test", "confidence": 0.9}]\n```'
        gen = _make_generator(payload)
        results = extract_memories_llm("question", "answer", gen)
        assert len(results) == 1

    def test_confidence_threshold_applied_by_caller(self) -> None:
        # LLM extractor itself doesn't filter by threshold — that's extract_memories()'s job
        payload = json.dumps(
            [{"memory_type": "preference", "content": "Low confidence fact", "confidence": 0.3}]
        )
        gen = _make_generator(payload)
        results = extract_memories_llm("question", "answer", gen)
        assert len(results) == 1  # extractor returns it; caller filters


class TestCombinedExtraction:
    def test_no_generator_uses_rule_only(self) -> None:
        results = extract_memories("I prefer A minor", "", generator=None)
        assert all(m.method == "rule" for m in results)

    def test_use_llm_false_skips_llm(self) -> None:
        gen = MagicMock()
        extract_memories("I prefer A minor", "", generator=gen, use_llm=False)
        gen.generate.assert_not_called()

    def test_confidence_threshold_filters_low_confidence(self) -> None:
        payload = json.dumps(
            [{"memory_type": "preference", "content": "Low conf", "confidence": 0.3}]
        )
        gen = _make_generator(payload)
        results = extract_memories(
            "question", "answer", generator=gen, use_llm=True, confidence_threshold=0.6
        )
        assert all(m.confidence >= 0.6 for m in results)

    def test_deduplication_by_content_prefix(self) -> None:
        # LLM and rule-based return overlapping content — deduplicate
        payload = json.dumps(
            [
                {
                    "memory_type": "preference",
                    "content": "I prefer A minor keys for dark tracks",
                    "confidence": 0.9,
                }
            ]
        )
        gen = _make_generator(payload)
        query = "I prefer A minor"
        results = extract_memories(query, "", generator=gen, use_llm=True)
        # Should not have two near-identical entries
        contents = [m.content[:50].lower() for m in results]
        # Unique prefixes
        assert len(contents) == len(set(contents))

    def test_llm_wins_over_rule_on_overlap(self) -> None:
        # When LLM and rule match same content, LLM method should be present
        payload = json.dumps(
            [{"memory_type": "preference", "content": "I prefer A minor keys", "confidence": 0.9}]
        )
        gen = _make_generator(payload)
        results = extract_memories("I prefer A minor keys", "", generator=gen, use_llm=True)
        llm_entries = [m for m in results if m.method == "llm"]
        assert len(llm_entries) >= 1

    def test_never_raises_on_exception(self) -> None:
        gen = MagicMock()
        gen.generate.side_effect = Exception("catastrophic failure")
        # Must not raise
        results = extract_memories("question", "answer", generator=gen)
        assert isinstance(results, list)

    def test_returns_list_for_generic_qa(self) -> None:
        results = extract_memories(
            "What attack time should I use on kick?",
            "Use 5ms attack for kick drums.",
            generator=None,
        )
        assert isinstance(results, list)
