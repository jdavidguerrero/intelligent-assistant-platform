"""Tests for domains/music/tagger_logic.py."""

from __future__ import annotations

import pytest

from domains.music.tagger_logic import infer_sub_domain


class TestPathBasedInference:
    """Pass-1 tests: path patterns take precedence, confidence=1.0, method=path."""

    def test_synthesis_path_yields_sound_design(self) -> None:
        tag = infer_sub_domain("/courses/synthesis/week1")
        assert tag is not None
        assert tag.sub_domain == "sound_design"
        assert tag.confidence == 1.0
        assert tag.method == "path"

    def test_serum_in_path_yields_sound_design(self) -> None:
        tag = infer_sub_domain("/courses/serum-masterclass/lesson1")
        assert tag is not None
        assert tag.sub_domain == "sound_design"

    def test_sound_design_path_fragment(self) -> None:
        tag = infer_sub_domain("/sound-design/fundamentals")
        assert tag is not None
        assert tag.sub_domain == "sound_design"

    def test_mixing_the_beat_path_yields_mixing(self) -> None:
        tag = infer_sub_domain("/pete-tong/mixing-the-beat/lesson3")
        assert tag is not None
        assert tag.sub_domain == "mixing"
        assert tag.confidence == 1.0
        assert tag.method == "path"

    def test_mastering_path_yields_mixing(self) -> None:
        tag = infer_sub_domain("/courses/mastering/chapter2")
        assert tag is not None
        assert tag.sub_domain == "mixing"

    def test_arrangement_path_yields_arrangement(self) -> None:
        tag = infer_sub_domain("/courses/arrangement/section1")
        assert tag is not None
        assert tag.sub_domain == "arrangement"
        assert tag.confidence == 1.0
        assert tag.method == "path"

    def test_mindset_path_yields_practice(self) -> None:
        tag = infer_sub_domain("/pete-tong/mindset/lesson1")
        assert tag is not None
        assert tag.sub_domain == "practice"
        assert tag.confidence == 1.0
        assert tag.method == "path"

    def test_wellbeing_path_yields_practice(self) -> None:
        tag = infer_sub_domain("/courses/wellbeing/module1")
        assert tag is not None
        assert tag.sub_domain == "practice"

    def test_studio_workflow_path_yields_live_performance(self) -> None:
        tag = infer_sub_domain("/pete-tong/studio-workflow/lesson2")
        assert tag is not None
        assert tag.sub_domain == "live_performance"
        assert tag.confidence == 1.0
        assert tag.method == "path"

    def test_harmony_path_yields_genre_analysis(self) -> None:
        tag = infer_sub_domain("/courses/harmony/intro")
        assert tag is not None
        assert tag.sub_domain == "genre_analysis"
        assert tag.confidence == 1.0
        assert tag.method == "path"

    def test_the_kick_path_yields_genre_analysis(self) -> None:
        tag = infer_sub_domain("/pete-tong/the-kick/fundamentals")
        assert tag is not None
        assert tag.sub_domain == "genre_analysis"

    def test_path_match_is_case_insensitive(self) -> None:
        tag = infer_sub_domain("/Courses/SYNTHESIS/WEEK1")
        assert tag is not None
        assert tag.sub_domain == "sound_design"


class TestKeywordBasedInference:
    """Pass-2 tests: keyword fallback when path does not match."""

    def test_mixing_keywords_yield_mixing(self) -> None:
        text = "Use equalizer compression sidechain gain staging and mastering."
        tag = infer_sub_domain("/unknown/path", text)
        assert tag is not None
        assert tag.sub_domain == "mixing"
        assert tag.method == "keyword"

    def test_sound_design_keywords_yield_sound_design(self) -> None:
        text = "synthesis oscillator wavetable lfo envelope filter resonance"
        tag = infer_sub_domain("/unknown/path", text)
        assert tag is not None
        assert tag.sub_domain == "sound_design"
        assert tag.method == "keyword"

    def test_arrangement_keywords_yield_arrangement(self) -> None:
        text = "The arrangement intro breakdown drop buildup structure"
        tag = infer_sub_domain("/generic/file", text)
        assert tag is not None
        assert tag.sub_domain == "arrangement"
        assert tag.method == "keyword"

    def test_practice_keywords_yield_practice(self) -> None:
        text = "mindset creativity wellbeing discipline routine habit"
        tag = infer_sub_domain("/generic/file", text)
        assert tag is not None
        assert tag.sub_domain == "practice"
        assert tag.method == "keyword"

    def test_genre_analysis_keywords_yield_genre_analysis(self) -> None:
        text = "organic house melodic techno camelot bpm groove swing percussion"
        tag = infer_sub_domain("/generic/file", text)
        assert tag is not None
        assert tag.sub_domain == "genre_analysis"
        assert tag.method == "keyword"

    def test_live_performance_keywords_yield_live_performance(self) -> None:
        text = "djing beatmatch rekordbox pioneer cdj crowd phrasing"
        tag = infer_sub_domain("/generic/file", text)
        assert tag is not None
        assert tag.sub_domain == "live_performance"
        assert tag.method == "keyword"

    def test_keyword_match_is_case_insensitive(self) -> None:
        text = "SYNTHESIS OSCILLATOR WAVETABLE LFO FILTER"
        tag = infer_sub_domain("/unknown/path", text)
        assert tag is not None
        assert tag.sub_domain == "sound_design"

    def test_single_keyword_below_threshold_returns_none(self) -> None:
        tag = infer_sub_domain("/unknown/path", "synthesis")
        assert tag is None

    def test_confidence_scales_with_keyword_count(self) -> None:
        text = "equalizer compression sidechain reverb delay gain staging headroom"
        tag = infer_sub_domain("/unknown/path", text)
        assert tag is not None
        assert tag.confidence > 0.5
        assert tag.confidence <= 0.9

    def test_confidence_capped_at_0_9(self) -> None:
        # Load many mixing keywords to push past the cap
        text = (
            "equalizer compression compressor mastering sidechain reverb delay "
            "stereo width gain staging headroom loudness lufs frequency high-pass "
            "low-pass transient bus stem multiband limiter saturation parallel mixing"
        )
        tag = infer_sub_domain("/unknown/path", text)
        assert tag is not None
        assert tag.confidence == 0.9


class TestNoMatch:
    """Tests for when neither pass produces a result."""

    def test_unknown_path_empty_text_returns_none(self) -> None:
        assert infer_sub_domain("/totally/unknown/path") is None

    def test_unknown_path_and_text_returns_none(self) -> None:
        assert infer_sub_domain("/totally/unknown/path", "") is None

    def test_zero_keywords_returns_none(self) -> None:
        assert infer_sub_domain("/unknown", "hello world foo bar") is None

    def test_one_keyword_returns_none(self) -> None:
        # Only 1 keyword match — below threshold of 2
        assert infer_sub_domain("/unknown", "synthesis") is None

    def test_path_takes_priority_over_keywords(self) -> None:
        # Path matches live_performance, text has many mixing keywords
        text = (
            "equalizer compression sidechain mastering reverb delay "
            "gain staging headroom loudness"
        )
        tag = infer_sub_domain("/studio-workflow/session1", text)
        assert tag is not None
        assert tag.sub_domain == "live_performance"
        assert tag.method == "path"
