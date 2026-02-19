"""Tests for domains/music/sub_domains.py."""

from __future__ import annotations

import pytest

from domains.music.sub_domains import MUSIC_SUB_DOMAINS, SubDomainTag


class TestMusicSubDomains:
    """Tests for the MUSIC_SUB_DOMAINS constant."""

    def test_has_exactly_six_entries(self) -> None:
        assert len(MUSIC_SUB_DOMAINS) == 6

    def test_contains_sound_design(self) -> None:
        assert "sound_design" in MUSIC_SUB_DOMAINS

    def test_contains_arrangement(self) -> None:
        assert "arrangement" in MUSIC_SUB_DOMAINS

    def test_contains_mixing(self) -> None:
        assert "mixing" in MUSIC_SUB_DOMAINS

    def test_contains_genre_analysis(self) -> None:
        assert "genre_analysis" in MUSIC_SUB_DOMAINS

    def test_contains_live_performance(self) -> None:
        assert "live_performance" in MUSIC_SUB_DOMAINS

    def test_contains_practice(self) -> None:
        assert "practice" in MUSIC_SUB_DOMAINS

    def test_is_tuple(self) -> None:
        assert isinstance(MUSIC_SUB_DOMAINS, tuple)


class TestSubDomainTag:
    """Tests for the SubDomainTag frozen dataclass."""

    def test_valid_construction(self) -> None:
        tag = SubDomainTag(sub_domain="mixing", confidence=0.8, method="keyword")
        assert tag.sub_domain == "mixing"
        assert tag.confidence == 0.8
        assert tag.method == "keyword"

    def test_all_six_sub_domains_are_valid(self) -> None:
        for sd in MUSIC_SUB_DOMAINS:
            tag = SubDomainTag(sub_domain=sd, confidence=0.5, method="path")
            assert tag.sub_domain == sd

    def test_invalid_sub_domain_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="sub_domain must be one of"):
            SubDomainTag(sub_domain="beatmaking", confidence=0.5, method="keyword")

    def test_confidence_zero_is_valid(self) -> None:
        tag = SubDomainTag(sub_domain="practice", confidence=0.0, method="manual")
        assert tag.confidence == 0.0

    def test_confidence_one_is_valid(self) -> None:
        tag = SubDomainTag(sub_domain="practice", confidence=1.0, method="path")
        assert tag.confidence == 1.0

    def test_confidence_below_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="confidence must be in"):
            SubDomainTag(sub_domain="mixing", confidence=-0.1, method="keyword")

    def test_confidence_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="confidence must be in"):
            SubDomainTag(sub_domain="mixing", confidence=1.1, method="keyword")

    def test_is_frozen(self) -> None:
        tag = SubDomainTag(sub_domain="arrangement", confidence=0.7, method="path")
        with pytest.raises((AttributeError, TypeError)):
            tag.sub_domain = "mixing"  # type: ignore[misc]

    def test_method_path(self) -> None:
        tag = SubDomainTag(sub_domain="sound_design", confidence=1.0, method="path")
        assert tag.method == "path"

    def test_method_keyword(self) -> None:
        tag = SubDomainTag(sub_domain="sound_design", confidence=0.6, method="keyword")
        assert tag.method == "keyword"

    def test_method_manual(self) -> None:
        tag = SubDomainTag(sub_domain="genre_analysis", confidence=0.9, method="manual")
        assert tag.method == "manual"

    def test_equality_same_values(self) -> None:
        a = SubDomainTag(sub_domain="mixing", confidence=0.8, method="keyword")
        b = SubDomainTag(sub_domain="mixing", confidence=0.8, method="keyword")
        assert a == b

    def test_equality_different_values(self) -> None:
        a = SubDomainTag(sub_domain="mixing", confidence=0.8, method="keyword")
        b = SubDomainTag(sub_domain="practice", confidence=0.8, method="keyword")
        assert a != b
