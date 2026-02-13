"""Tests for query expansion and intent detection."""

from core.query_expansion import QueryIntent, detect_mastering_intent, expand_query


class TestDetectMasteringIntent:
    """Tests for detect_mastering_intent() function."""

    def test_explicit_mastering_query(self) -> None:
        """Detect explicit mastering query."""
        intent = detect_mastering_intent("mastering chain setup")
        assert intent.category == "mastering"
        assert intent.confidence == 1.0
        assert "mastering" in intent.keywords or "mastering chain" in intent.keywords

    def test_mixing_query(self) -> None:
        """Detect mixing query."""
        intent = detect_mastering_intent("EQ tips for mixing")
        assert intent.category == "mixing"
        assert intent.confidence == 0.8
        assert any(kw in ["eq", "mixing"] for kw in intent.keywords)

    def test_compression_query(self) -> None:
        """Compression is a mixing keyword."""
        intent = detect_mastering_intent("sidechain compression tutorial")
        assert intent.category == "mixing"
        assert intent.confidence == 0.8
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
        assert intent.confidence == 1.0


class TestExpandQuery:
    """Tests for expand_query() function."""

    def test_expand_mastering_query(self) -> None:
        """Expand mastering query with domain terms."""
        intent = QueryIntent(category="mastering", confidence=1.0, keywords=["mastering"])
        expanded = expand_query("mastering chain setup", intent)

        # Should contain original query
        assert "mastering chain setup" in expanded

        # Should add relevant terms not already present
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

        # Should return original query unchanged
        assert expanded == "how to make a punchy kick"

    def test_no_duplicate_terms(self) -> None:
        """Don't add terms already in the query."""
        intent = QueryIntent(category="mastering", confidence=1.0, keywords=["mastering"])
        expanded = expand_query("mastering mixing audio processing", intent)

        # Should not duplicate existing terms
        # Count occurrences
        assert expanded.count("mastering") == 1
        assert expanded.count("mixing") == 1
        assert expanded.count("audio processing") == 1

    def test_empty_query(self) -> None:
        """Handle empty query gracefully."""
        intent = QueryIntent(category="mastering", confidence=1.0, keywords=["mastering"])
        expanded = expand_query("", intent)

        # Should add expansion terms even if query is empty
        assert "mastering" in expanded
        assert "final mix" in expanded
