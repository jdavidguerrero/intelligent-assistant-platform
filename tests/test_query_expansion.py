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
        """Query with no music production keywords returns general intent.

        Note: 'kick' is a rhythm domain keyword so 'punchy kick' now matches
        rhythm. Use a truly non-music query for the general fallback.
        """
        intent = detect_mastering_intent("what is the weather today")
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
        """No domain matches → empty list (caller treats as general).

        Note: with the expanded domain registry, many 'music' queries now
        match a domain. Use a truly non-music query here.
        """
        intents = detect_intents("what is the best coffee brand")
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


# ---------------------------------------------------------------------------
# New music production domains (Week 6)
# ---------------------------------------------------------------------------


class TestNewMusicDomains:
    """Tests for the expanded domain registry covering music production domains."""

    def test_registry_has_new_domains(self) -> None:
        """Registry includes all 10 music production domains."""
        names = {d.name for d in DOMAIN_REGISTRY}
        expected = {
            "mastering",
            "mixing",
            "sound_design",
            "synthesis",
            "rhythm",
            "chord_progressions",
            "organic_house",
            "afrobeat",
            "arrangement",
            "bass_design",
        }
        assert expected == names, f"Missing domains: {expected - names}"

    def test_sound_design_serum_query(self) -> None:
        """Serum-specific query detects sound_design intent."""
        intents = detect_intents("how to design a bass sound in Serum")
        categories = [i.category for i in intents]
        assert "sound_design" in categories or "bass_design" in categories

    def test_sound_design_wavetable_query(self) -> None:
        """Wavetable query detects sound_design."""
        intents = detect_intents("wavetable oscillator patch design")
        categories = [i.category for i in intents]
        assert "sound_design" in categories

    def test_synthesis_adsr_query(self) -> None:
        """ADSR envelope query detects synthesis."""
        intents = detect_intents("how to set attack and release on the envelope")
        categories = [i.category for i in intents]
        assert "synthesis" in categories

    def test_synthesis_lfo_filter_query(self) -> None:
        """LFO to filter cutoff modulation detects synthesis."""
        intents = detect_intents("LFO modulate filter cutoff resonance")
        categories = [i.category for i in intents]
        assert "synthesis" in categories

    def test_rhythm_drum_groove_query(self) -> None:
        """Drum groove query detects rhythm."""
        intents = detect_intents("how to program a groovy drum pattern with swing")
        categories = [i.category for i in intents]
        assert "rhythm" in categories

    def test_rhythm_quantize_query(self) -> None:
        """Quantization query detects rhythm."""
        intents = detect_intents("quantize vs swing drum timing")
        categories = [i.category for i in intents]
        assert "rhythm" in categories

    def test_chord_progressions_harmony_query(self) -> None:
        """Harmony/chord query detects chord_progressions."""
        intents = detect_intents("chord progressions in minor key for deep house")
        categories = [i.category for i in intents]
        assert "chord_progressions" in categories

    def test_chord_progressions_scale_query(self) -> None:
        """Scale/mode query detects chord_progressions."""
        intents = detect_intents("dorian mode scale intervals")
        categories = [i.category for i in intents]
        assert "chord_progressions" in categories

    def test_organic_house_query(self) -> None:
        """Organic house genre query detects organic_house."""
        intents = detect_intents("how to make organic house like All Day I Dream")
        categories = [i.category for i in intents]
        assert "organic_house" in categories

    def test_organic_house_deep_progressive_query(self) -> None:
        """Deep progressive house detects organic_house."""
        intents = detect_intents("deep progressive melodic house structure")
        categories = [i.category for i in intents]
        assert "organic_house" in categories

    def test_afrobeat_clave_query(self) -> None:
        """Clave/tresillo query detects afrobeat."""
        intents = detect_intents("son clave 3+3+2 tresillo pattern")
        categories = [i.category for i in intents]
        assert "afrobeat" in categories

    def test_afrobeat_black_coffee_query(self) -> None:
        """Black Coffee style query detects afrobeat."""
        intents = detect_intents("afro house Black Coffee production style")
        categories = [i.category for i in intents]
        assert "afrobeat" in categories

    def test_arrangement_drop_structure_query(self) -> None:
        """Drop/structure query detects arrangement."""
        intents = detect_intents("how to structure a track with intro drop breakdown")
        categories = [i.category for i in intents]
        assert "arrangement" in categories

    def test_arrangement_buildup_query(self) -> None:
        """Buildup/tension query detects arrangement."""
        intents = detect_intents("buildup tension release 16 bars before the drop")
        categories = [i.category for i in intents]
        assert "arrangement" in categories

    def test_bass_design_808_query(self) -> None:
        """808 bass query detects bass_design."""
        intents = detect_intents("how to design an 808 sub bass")
        categories = [i.category for i in intents]
        assert "bass_design" in categories

    def test_bass_design_kickbass_query(self) -> None:
        """Kick-bass relationship query detects bass_design."""
        intents = detect_intents("kick bass sidechain relationship low end")
        categories = [i.category for i in intents]
        assert "bass_design" in categories

    def test_multi_domain_sound_design_synthesis(self) -> None:
        """Serum synthesis query matches both sound_design and synthesis."""
        intents = detect_intents("Serum synthesis oscillator LFO filter modulation")
        categories = [i.category for i in intents]
        assert "sound_design" in categories
        assert "synthesis" in categories

    def test_multi_domain_organic_afro(self) -> None:
        """Organic + afro query can match multiple domains."""
        intents = detect_intents("afro house conga bongo organic percussion groove")
        categories = [i.category for i in intents]
        # At least one of these must be detected
        assert "afrobeat" in categories or "rhythm" in categories or "organic_house" in categories

    def test_negative_keywords_exclude_programming(self) -> None:
        """Programming keywords exclude all music domains."""
        for query in [
            "python synthesis algorithm",
            "java drum machine programming",
            "coding chord progression",
        ]:
            intents = detect_intents(query)
            categories = [i.category for i in intents]
            for cat in [
                "sound_design",
                "synthesis",
                "rhythm",
                "chord_progressions",
                "organic_house",
                "afrobeat",
                "arrangement",
                "bass_design",
            ]:
                assert (
                    cat not in categories
                ), f"Domain {cat!r} should be excluded for programming query: {query!r}"

    def test_expand_sound_design_query(self) -> None:
        """sound_design domain produces meaningful expansion."""
        intent = QueryIntent(category="sound_design", confidence=0.9, keywords=["serum"])
        expanded = expand_query("bass sound in Serum", intent)
        assert "bass sound in Serum" in expanded
        assert "sound design" in expanded or "synthesis" in expanded

    def test_expand_rhythm_query(self) -> None:
        """rhythm domain produces meaningful expansion."""
        intent = QueryIntent(category="rhythm", confidence=0.85, keywords=["groove"])
        expanded = expand_query("how to add groove to drums", intent)
        assert "how to add groove to drums" in expanded
        assert "rhythm" in expanded or "groove" in expanded

    def test_expand_organic_house_query(self) -> None:
        """organic_house domain produces meaningful expansion."""
        intent = QueryIntent(category="organic_house", confidence=0.9, keywords=["organic house"])
        expanded = expand_query("making organic house tracks", intent)
        assert "making organic house tracks" in expanded
        # Should add related terms
        assert len(expanded) > len("making organic house tracks")
