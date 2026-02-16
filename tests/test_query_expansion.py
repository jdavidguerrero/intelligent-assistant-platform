"""Tests for query expansion and intent detection.

Covers:
- Backward-compatible ``detect_mastering_intent()``
- Multi-intent ``detect_intents()``
- ``DomainConfig`` registry (custom domains, negative keywords)
- ``expand_query()`` with dedup and validation
"""

import pytest

from core.query_expansion import (
    DOMAIN_REGISTRY,
    DomainConfig,
    QueryIntent,
    detect_intents,
    detect_mastering_intent,
    expand_query,
)

# ---------------------------------------------------------------------------
# detect_mastering_intent (backward-compatible wrapper)
# ---------------------------------------------------------------------------


class TestDetectMasteringIntent:
    """Tests for detect_mastering_intent() function."""

    def test_explicit_mastering_query(self) -> None:
        """Detect explicit mastering query."""
        intent = detect_mastering_intent("mastering chain setup")
        assert intent.category == "mastering"
        assert intent.confidence > 0
        assert "mastering" in intent.keywords or "mastering chain" in intent.keywords

    def test_mixing_query(self) -> None:
        """Detect mixing query."""
        intent = detect_mastering_intent("EQ tips for mixing")
        assert intent.category == "mixing"
        assert intent.confidence > 0
        assert any(kw in ["eq", "mixing"] for kw in intent.keywords)

    def test_compression_query(self) -> None:
        """Compression is a mixing keyword."""
        intent = detect_mastering_intent("sidechain compression tutorial")
        assert intent.category == "mixing"
        assert intent.confidence > 0
        assert any(kw in ["compression", "sidechain"] for kw in intent.keywords)

    def test_general_query(self) -> None:
        """General query returns general intent."""
        intent = detect_mastering_intent("how to make a punchy kick")
        assert intent.category == "general"
        assert intent.confidence == 0.0
        assert intent.keywords == []

    def test_case_insensitive(self) -> None:
        """Intent detection is case-insensitive."""
        intent = detect_mastering_intent("MASTERING CHAIN SETUP")
        assert intent.category == "mastering"
        assert intent.confidence > 0

    def test_empty_string_returns_general(self) -> None:
        """Empty query → general fallback (no ValueError from wrapper)."""
        intent = detect_mastering_intent("")
        assert intent.category == "general"
        assert intent.confidence == 0.0

    def test_whitespace_only_returns_general(self) -> None:
        """Whitespace query → general fallback."""
        intent = detect_mastering_intent("   ")
        assert intent.category == "general"


# ---------------------------------------------------------------------------
# detect_intents (multi-intent, new API)
# ---------------------------------------------------------------------------


class TestDetectIntents:
    """Tests for detect_intents() multi-intent detection."""

    def test_mastering_query_returns_list(self) -> None:
        """Multi-intent returns a sorted list."""
        intents = detect_intents("mastering chain setup")
        assert len(intents) >= 1
        assert intents[0].category == "mastering"

    def test_multi_intent_mastering_and_mixing(self) -> None:
        """Query matching both domains returns both intents."""
        intents = detect_intents("mastering EQ compression chain")
        categories = [i.category for i in intents]
        assert "mastering" in categories
        assert "mixing" in categories
        # Mastering should rank first (higher base_confidence)
        assert intents[0].category == "mastering"

    def test_general_query_returns_empty(self) -> None:
        """No domain matches → empty list (caller treats as general)."""
        intents = detect_intents("how to make a punchy kick")
        assert intents == []

    def test_confidence_proportional_to_matches(self) -> None:
        """More keywords matched → higher confidence."""
        single = detect_intents("mastering")
        multi = detect_intents("mastering limiter loudness multiband")

        single_conf = single[0].confidence
        multi_conf = multi[0].confidence
        assert multi_conf > single_conf

    def test_empty_query_raises(self) -> None:
        """Empty query raises ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            detect_intents("")

    def test_whitespace_query_raises(self) -> None:
        """Whitespace-only query raises ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            detect_intents("   ")

    def test_sorted_by_confidence_desc(self) -> None:
        """Results are sorted by confidence descending."""
        intents = detect_intents("mixing compression mastering chain")
        if len(intents) >= 2:
            assert intents[0].confidence >= intents[1].confidence


# ---------------------------------------------------------------------------
# Negative keywords
# ---------------------------------------------------------------------------


class TestNegativeKeywords:
    """Tests for negative keyword exclusion."""

    def test_python_mastering_excluded(self) -> None:
        """'master' in 'how to master Python' is excluded by negative keyword."""
        intent = detect_mastering_intent("how to master python")
        assert intent.category == "general"

    def test_coding_compression_excluded(self) -> None:
        """Programming context excludes mixing detection."""
        intent = detect_mastering_intent("compression coding algorithm")
        assert intent.category == "general"

    def test_negative_keyword_does_not_affect_clean_query(self) -> None:
        """Clean audio query still works when negatives exist."""
        intent = detect_mastering_intent("loudness limiting for mastering")
        assert intent.category == "mastering"


# ---------------------------------------------------------------------------
# DomainConfig / custom registry
# ---------------------------------------------------------------------------


class TestDomainConfig:
    """Tests for DomainConfig and custom registries."""

    def test_custom_domain_detected(self) -> None:
        """Custom domain config works with detect_intents."""
        custom = [
            DomainConfig(
                name="sound_design",
                keywords=["synth", "wavetable", "oscillator"],
                expansion_terms=["synthesis", "sound design"],
                base_confidence=0.9,
            )
        ]
        intents = detect_intents("wavetable synth tutorial", domains=custom)
        assert len(intents) == 1
        assert intents[0].category == "sound_design"
        assert intents[0].confidence > 0

    def test_custom_negative_keyword(self) -> None:
        """Custom negative keyword blocks detection."""
        custom = [
            DomainConfig(
                name="sound_design",
                keywords=["synth"],
                expansion_terms=[],
                base_confidence=1.0,
                negative_keywords=["vintage"],
            )
        ]
        intents = detect_intents("vintage synth collection", domains=custom)
        assert intents == []

    def test_registry_has_expected_domains(self) -> None:
        """Default registry includes mastering and mixing."""
        names = [d.name for d in DOMAIN_REGISTRY]
        assert "mastering" in names
        assert "mixing" in names

    def test_all_domains_have_keywords(self) -> None:
        """Every domain in registry has at least one keyword."""
        for domain in DOMAIN_REGISTRY:
            assert len(domain.keywords) > 0, f"{domain.name} has no keywords"

    def test_all_domains_have_expansion_terms(self) -> None:
        """Every domain has expansion terms."""
        for domain in DOMAIN_REGISTRY:
            assert len(domain.expansion_terms) > 0, f"{domain.name} has no expansion"


# ---------------------------------------------------------------------------
# expand_query
# ---------------------------------------------------------------------------


class TestExpandQuery:
    """Tests for expand_query() function."""

    def test_expand_mastering_query(self) -> None:
        """Expand mastering query with domain terms."""
        intent = QueryIntent(category="mastering", confidence=1.0, keywords=["mastering"])
        expanded = expand_query("mastering chain setup", intent)

        assert "mastering chain setup" in expanded
        assert "final mix" in expanded
        assert "audio processing" in expanded

    def test_expand_mixing_query(self) -> None:
        """Expand mixing query with domain terms."""
        intent = QueryIntent(category="mixing", confidence=0.8, keywords=["eq"])
        expanded = expand_query("EQ tips", intent)

        assert "EQ tips" in expanded
        assert "mixing" in expanded
        assert "audio processing" in expanded
        assert "production" in expanded

    def test_no_expansion_for_general(self) -> None:
        """General queries are not expanded."""
        intent = QueryIntent(category="general", confidence=0.0, keywords=[])
        expanded = expand_query("how to make a punchy kick", intent)

        assert expanded == "how to make a punchy kick"

    def test_no_duplicate_terms(self) -> None:
        """Don't add terms already in the query."""
        intent = QueryIntent(category="mastering", confidence=1.0, keywords=["mastering"])
        expanded = expand_query("mastering mixing audio processing", intent)

        assert expanded.count("mastering") == 1
        assert expanded.count("mixing") == 1
        assert expanded.count("audio processing") == 1

    def test_empty_query_expands(self) -> None:
        """Empty string query still gets expansion terms."""
        intent = QueryIntent(category="mastering", confidence=1.0, keywords=["mastering"])
        expanded = expand_query("", intent)

        assert "mastering" in expanded
        assert "final mix" in expanded

    def test_none_query_raises(self) -> None:
        """None query raises ValueError."""
        intent = QueryIntent(category="mastering", confidence=1.0, keywords=[])
        with pytest.raises(ValueError, match="must not be None"):
            expand_query(None, intent)  # type: ignore[arg-type]

    def test_unknown_category_no_expansion(self) -> None:
        """Category not in registry → no expansion, no crash."""
        intent = QueryIntent(category="unknown_domain", confidence=0.5, keywords=["foo"])
        expanded = expand_query("some query", intent)
        assert expanded == "some query"
