"""
tests/test_sub_domain_detector.py

Unit tests for core/sub_domain_detector.py

Covers:
- detect_sub_domains: keyword voting, threshold, max_results
- primary_sub_domain: convenience wrapper
- SubDomainDetectionResult: immutability, fields
- Edge cases: empty query, ambiguous query, no match
"""

from __future__ import annotations

import pytest

from core.sub_domain_detector import (
    SubDomainDetectionResult,
    detect_sub_domains,
    primary_sub_domain,
)


class TestDetectSubDomains:
    def test_mixing_query_detected(self) -> None:
        result = detect_sub_domains("how do I EQ the bass in my mix")
        assert "mixing" in result.active

    def test_sound_design_query_detected(self) -> None:
        result = detect_sub_domains("how do I design a bass sound in Serum")
        assert "sound_design" in result.active

    def test_arrangement_query_detected(self) -> None:
        result = detect_sub_domains("what is the typical arrangement structure for a drop")
        assert "arrangement" in result.active

    def test_genre_analysis_query_detected(self) -> None:
        result = detect_sub_domains("what BPM is organic house")
        assert "genre_analysis" in result.active

    def test_live_performance_query_detected(self) -> None:
        result = detect_sub_domains("how do I prepare my DJ set")
        assert "live_performance" in result.active

    def test_practice_query_detected(self) -> None:
        result = detect_sub_domains("how do I build a daily practice routine")
        assert "practice" in result.active

    def test_cross_domain_query_returns_multiple(self) -> None:
        # "How do I EQ the bass in organic house?" spans mixing + genre_analysis
        result = detect_sub_domains("how do I EQ the bass in organic house")
        assert "mixing" in result.active
        assert "genre_analysis" in result.active

    def test_active_ordered_by_votes_descending(self) -> None:
        # Query with many mixing keywords and one genre keyword
        result = detect_sub_domains(
            "compression sidechain reverb eq stereo width gain staging organic house"
        )
        assert result.active[0] == "mixing"

    def test_max_results_limits_output(self) -> None:
        result = detect_sub_domains(
            "compression sidechain reverb eq stereo width gain staging organic house dj set",
            max_results=2,
        )
        assert len(result.active) <= 2

    def test_no_match_returns_empty_active(self) -> None:
        result = detect_sub_domains("what is the weather in London")
        assert result.active == ()

    def test_empty_query_returns_empty_active(self) -> None:
        result = detect_sub_domains("")
        assert result.active == ()

    def test_votes_dict_has_all_six_sub_domains(self) -> None:
        result = detect_sub_domains("mixing")
        expected = {
            "sound_design",
            "arrangement",
            "mixing",
            "genre_analysis",
            "live_performance",
            "practice",
        }
        assert set(result.votes.keys()) == expected

    def test_votes_are_non_negative(self) -> None:
        result = detect_sub_domains("random query text")
        assert all(v >= 0 for v in result.votes.values())

    def test_query_stored_lowercase(self) -> None:
        result = detect_sub_domains("HOW DO I MIX")
        assert result.query == "how do i mix"

    def test_case_insensitive_matching(self) -> None:
        lower = detect_sub_domains("how do i mix")
        upper = detect_sub_domains("HOW DO I MIX")
        assert lower.active == upper.active

    def test_vote_threshold_2_excludes_single_match(self) -> None:
        # "mixing" has one keyword match — threshold=2 should exclude it
        result = detect_sub_domains("mix", vote_threshold=2)
        assert "mixing" not in result.active

    def test_vote_threshold_1_includes_single_match(self) -> None:
        result = detect_sub_domains("mixing", vote_threshold=1)
        assert "mixing" in result.active

    def test_invalid_vote_threshold_raises(self) -> None:
        with pytest.raises(ValueError, match="vote_threshold must be >= 1"):
            detect_sub_domains("mix", vote_threshold=0)

    def test_invalid_max_results_raises(self) -> None:
        with pytest.raises(ValueError, match="max_results must be >= 1"):
            detect_sub_domains("mix", max_results=0)

    def test_returns_sub_domain_detection_result(self) -> None:
        result = detect_sub_domains("mixing eq compression")
        assert isinstance(result, SubDomainDetectionResult)

    def test_result_is_immutable(self) -> None:
        result = detect_sub_domains("mixing")
        with pytest.raises((AttributeError, TypeError)):
            result.active = ("arrangement",)  # type: ignore[misc]

    def test_progressive_house_detects_genre_analysis(self) -> None:
        result = detect_sub_domains("what are the characteristics of progressive house")
        assert "genre_analysis" in result.active

    def test_serum_detects_sound_design(self) -> None:
        result = detect_sub_domains("serum bass patch tutorial")
        assert "sound_design" in result.active

    def test_dj_detects_live_performance(self) -> None:
        result = detect_sub_domains("how to beatmatch on CDJ")
        assert "live_performance" in result.active


class TestPrimarySubDomain:
    def test_returns_top_sub_domain(self) -> None:
        sd = primary_sub_domain("how do I EQ the mix with compression sidechain")
        assert sd == "mixing"

    def test_returns_none_for_unrelated_query(self) -> None:
        sd = primary_sub_domain("what is the capital of France")
        assert sd is None

    def test_returns_string_not_list(self) -> None:
        sd = primary_sub_domain("synthesis oscillator wavetable")
        assert isinstance(sd, str)

    def test_sound_design_from_synthesis(self) -> None:
        sd = primary_sub_domain("subtractive synthesis oscillator filter resonance")
        assert sd == "sound_design"

    def test_arrangement_from_structure(self) -> None:
        sd = primary_sub_domain("how should I structure my arrangement breakdown drop")
        assert sd == "arrangement"
