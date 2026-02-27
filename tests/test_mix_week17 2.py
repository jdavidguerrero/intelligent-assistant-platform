"""
tests/test_mix_week17.py — Week 17 prescriptive layer test suite.

Covers:
    - core/mix_analysis/recommendations.py  (8 fix generators + public API)
    - core/mix_analysis/mastering.py        (LUFS windows, true peak, scoring)
    - core/mix_analysis/chains.py           (YAML loader, cache, validation)
    - ingestion/mix_engine.py               (MixAnalysisEngine orchestrator)
    - tools/music/analyze_mix.py            (MCP tool)
    - tools/music/recommend_chain.py        (MCP tool)
    - tools/music/analyze_master.py         (MCP tool)

All tests are deterministic. Audio analysis tests use synthetic numpy arrays.
No real audio files required. Engine tests mock load_audio.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from core.mix_analysis.types import (
    BandProfile,
    DynamicProfile,
    FixStep,
    FrequencyProfile,
    MasterAnalysis,
    MasterReport,
    MixProblem,
    MixReport,
    Processor,
    ProcessorParam,
    SectionDynamics,
    SignalChain,
    StereoImage,
    TransientProfile,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SR = 44100
ONE_SEC = np.zeros(SR, dtype=float)
TWO_SEC_STEREO = np.zeros((2, SR * 2), dtype=float)


def _make_band_profile(
    *,
    sub: float = -10.0,
    low: float = -8.0,
    low_mid: float = -6.0,
    mid: float = -9.0,
    high_mid: float = -10.0,
    high: float = -12.0,
    air: float = -15.0,
) -> BandProfile:
    return BandProfile(
        sub=sub,
        low=low,
        low_mid=low_mid,
        mid=mid,
        high_mid=high_mid,
        high=high,
        air=air,
    )


def _make_freq(
    bands: BandProfile | None = None,
    centroid: float = 1200.0,
    tilt: float = -4.5,
    flatness: float = 0.3,
    rms_db: float = -14.0,
) -> FrequencyProfile:
    return FrequencyProfile(
        bands=bands or _make_band_profile(),
        spectral_centroid=centroid,
        spectral_tilt=tilt,
        spectral_flatness=flatness,
        overall_rms_db=rms_db,
    )


def _make_dynamics(
    rms_db: float = -14.0,
    peak_db: float = -4.0,
    lufs: float = -8.0,
    crest: float = 10.0,
    dyn_range: float = 12.0,
    lra: float = 4.0,
) -> DynamicProfile:
    return DynamicProfile(
        rms_db=rms_db,
        peak_db=peak_db,
        lufs=lufs,
        crest_factor=crest,
        dynamic_range=dyn_range,
        loudness_range=lra,
    )


def _make_stereo(
    width: float = 0.5,
    corr: float = 0.0,
    ms_ratio: float = 5.0,
) -> StereoImage:
    bw = BandProfile(sub=0.05, low=0.10, low_mid=0.25, mid=0.45, high_mid=0.55, high=0.60, air=0.65)
    return StereoImage(
        width=width,
        lr_correlation=corr,
        mid_side_ratio=ms_ratio,
        band_widths=bw,
        is_mono=False,
    )


def _make_problem(
    category: str = "muddiness",
    severity: float = 5.0,
    freq_range: tuple[float, float] = (200.0, 500.0),
    description: str = "test problem",
    recommendation: str = "test fix",
) -> MixProblem:
    return MixProblem(
        category=category,
        frequency_range=freq_range,
        severity=severity,
        description=description,
        recommendation=recommendation,
    )


# ===========================================================================
# 1. TestRecommendations — core/mix_analysis/recommendations.py
# ===========================================================================


class TestRecommendFix:
    """Test recommend_fix() for all 8 problem categories."""

    def test_fix_muddiness_returns_recommendation(self) -> None:
        from core.mix_analysis.recommendations import recommend_fix

        freq = _make_freq(bands=_make_band_profile(low_mid=-2.0))  # high low_mid
        problem = _make_problem("muddiness", severity=6.0)
        rec = recommend_fix(problem, freq, None, _make_dynamics(), "organic house")

        assert rec.problem_category == "muddiness"
        assert rec.genre == "organic house"
        assert rec.severity == 6.0
        assert len(rec.steps) >= 1
        assert "Hz" in rec.steps[0].action
        assert "dB" in rec.steps[0].action

    def test_fix_muddiness_step_params_are_present(self) -> None:
        from core.mix_analysis.recommendations import recommend_fix

        freq = _make_freq(bands=_make_band_profile(low_mid=-2.0))
        problem = _make_problem("muddiness")
        rec = recommend_fix(problem, freq, None, _make_dynamics(), "organic house")

        step = rec.steps[0]
        param_names = {p.name for p in step.params}
        assert "frequency" in param_names
        assert "gain" in param_names

    def test_fix_harshness_returns_recommendation(self) -> None:
        from core.mix_analysis.recommendations import recommend_fix

        freq = _make_freq(bands=_make_band_profile(high_mid=-4.0))
        problem = _make_problem("harshness", severity=4.0)
        rec = recommend_fix(problem, freq, None, _make_dynamics(), "organic house")

        assert rec.problem_category == "harshness"
        assert len(rec.steps) >= 1
        assert "Hz" in rec.summary

    def test_fix_boominess_has_three_steps(self) -> None:
        from core.mix_analysis.recommendations import recommend_fix

        freq = _make_freq(bands=_make_band_profile(sub=-3.0, low=-4.0))
        problem = _make_problem("boominess", severity=5.0, freq_range=(20.0, 200.0))
        rec = recommend_fix(problem, freq, None, _make_dynamics(crest=6.0), "organic house")

        assert rec.problem_category == "boominess"
        assert len(rec.steps) == 3
        # Step 3 should mention sidechain
        assert "sidechain" in rec.steps[2].action.lower()

    def test_fix_thinness_boost_is_positive(self) -> None:
        from core.mix_analysis.recommendations import recommend_fix

        freq = _make_freq(bands=_make_band_profile(low_mid=-18.0))  # very thin
        problem = _make_problem("thinness", severity=4.0, freq_range=(100.0, 500.0))
        rec = recommend_fix(problem, freq, None, _make_dynamics(), "organic house")

        assert rec.problem_category == "thinness"
        # Action should be a BOOST, not a cut
        assert "boost" in rec.steps[0].action.lower() or "+" in rec.steps[0].action

    def test_fix_narrow_stereo_with_stereo_input(self) -> None:
        from core.mix_analysis.recommendations import recommend_fix

        stereo = _make_stereo(width=0.15)
        problem = _make_problem("narrow_stereo", severity=3.0, freq_range=(0.0, 20000.0))
        rec = recommend_fix(problem, _make_freq(), stereo, _make_dynamics(), "organic house")

        assert rec.problem_category == "narrow_stereo"
        assert len(rec.steps) >= 2
        # Should mention Haas or width
        all_actions = " ".join(s.action for s in rec.steps).lower()
        assert "haas" in all_actions or "width" in all_actions

    def test_fix_narrow_stereo_mono_input_returns_empty_steps(self) -> None:
        from core.mix_analysis.recommendations import recommend_fix

        problem = _make_problem("narrow_stereo", severity=3.0)
        rec = recommend_fix(problem, _make_freq(), None, _make_dynamics(), "organic house")

        assert rec.summary == "Mono input — stereo fix not applicable"
        assert len(rec.steps) == 0

    def test_fix_phase_issues_with_stereo_input(self) -> None:
        from core.mix_analysis.recommendations import recommend_fix

        stereo = _make_stereo(corr=-0.5)
        problem = _make_problem("phase_issues", severity=5.0, freq_range=(20.0, 500.0))
        rec = recommend_fix(problem, _make_freq(), stereo, _make_dynamics(), "organic house")

        assert rec.problem_category == "phase_issues"
        assert len(rec.steps) == 3

    def test_fix_over_compression_mentions_attack(self) -> None:
        from core.mix_analysis.recommendations import recommend_fix

        dyn = _make_dynamics(crest=4.0)  # very low crest
        problem = _make_problem("over_compression", severity=7.0)
        rec = recommend_fix(problem, _make_freq(), None, dyn, "organic house")

        assert rec.problem_category == "over_compression"
        assert len(rec.steps) >= 2
        all_text = " ".join(s.action for s in rec.steps).lower()
        assert "attack" in all_text

    def test_fix_under_compression_returns_recommendation(self) -> None:
        from core.mix_analysis.recommendations import recommend_fix

        dyn = _make_dynamics(crest=20.0)  # very high crest
        problem = _make_problem("under_compression", severity=4.0)
        rec = recommend_fix(problem, _make_freq(), None, dyn, "organic house")

        assert rec.problem_category == "under_compression"
        assert len(rec.steps) >= 1

    def test_unknown_category_raises_value_error(self) -> None:
        from core.mix_analysis.recommendations import recommend_fix

        problem = _make_problem("nonexistent_problem")
        with pytest.raises(ValueError, match="nonexistent_problem"):
            recommend_fix(problem, _make_freq(), None, _make_dynamics(), "organic house")

    def test_recommendation_has_rag_query(self) -> None:
        from core.mix_analysis.recommendations import recommend_fix

        freq = _make_freq(bands=_make_band_profile(low_mid=-2.0))
        problem = _make_problem("muddiness")
        rec = recommend_fix(problem, freq, None, _make_dynamics(), "organic house")

        assert len(rec.rag_query) > 0
        assert "organic house" in rec.rag_query

    def test_rag_citations_empty_before_engine(self) -> None:
        from core.mix_analysis.recommendations import recommend_fix

        problem = _make_problem("muddiness")
        rec = recommend_fix(problem, _make_freq(), None, _make_dynamics(), "organic house")
        assert rec.rag_citations == ()

    def test_recommendation_is_frozen(self) -> None:
        from core.mix_analysis.recommendations import recommend_fix

        problem = _make_problem("muddiness")
        rec = recommend_fix(problem, _make_freq(), None, _make_dynamics(), "organic house")
        with pytest.raises((AttributeError, TypeError)):
            rec.severity = 0.0  # type: ignore[misc]


class TestRecommendAll:
    """Test recommend_all() batch API."""

    def test_recommend_all_returns_list(self) -> None:
        from core.mix_analysis.recommendations import recommend_all

        problems = [
            _make_problem("muddiness", severity=6.0),
            _make_problem("harshness", severity=4.0),
        ]
        recs = recommend_all(
            problems, _make_freq(), _make_stereo(), _make_dynamics(), "organic house"
        )
        assert isinstance(recs, list)
        assert len(recs) == 2

    def test_recommend_all_respects_max(self) -> None:
        from core.mix_analysis.recommendations import recommend_all

        problems = [_make_problem("muddiness", severity=float(10 - i)) for i in range(6)]
        recs = recommend_all(
            problems,
            _make_freq(),
            _make_stereo(),
            _make_dynamics(),
            "organic house",
            max_recommendations=3,
        )
        assert len(recs) <= 3

    def test_recommend_all_skips_zero_severity(self) -> None:
        from core.mix_analysis.recommendations import recommend_all

        problems = [
            _make_problem("muddiness", severity=0.0),
            _make_problem("harshness", severity=5.0),
        ]
        recs = recommend_all(
            problems, _make_freq(), _make_stereo(), _make_dynamics(), "organic house"
        )
        assert len(recs) == 1
        assert recs[0].problem_category == "harshness"

    def test_recommend_all_empty_problems_returns_empty(self) -> None:
        from core.mix_analysis.recommendations import recommend_all

        recs = recommend_all([], _make_freq(), None, _make_dynamics(), "organic house")
        assert recs == []

    def test_all_genres_work(self) -> None:
        from core.mix_analysis.recommendations import recommend_all

        genres = [
            "organic house",
            "melodic techno",
            "deep house",
            "progressive house",
            "afro house",
        ]
        problems = [_make_problem("muddiness", severity=5.0)]
        for genre in genres:
            recs = recommend_all(problems, _make_freq(), None, _make_dynamics(), genre)
            assert len(recs) == 1


# ===========================================================================
# 2. TestMastering — core/mix_analysis/mastering.py
# ===========================================================================


class TestLUFSMomentary:
    """_lufs_momentary — 400 ms windows, no gating."""

    def test_silence_returns_minus_70(self) -> None:
        from core.mix_analysis.mastering import _lufs_momentary

        channels = [np.zeros(SR * 2)]
        result = _lufs_momentary(channels, SR)
        assert result == pytest.approx(-70.0, abs=1.0)

    def test_loud_tone_above_minus_70(self) -> None:
        from core.mix_analysis.mastering import _lufs_momentary

        t = np.linspace(0, 2.0, SR * 2)
        tone = 0.5 * np.sin(2 * np.pi * 1000 * t)
        channels = [tone]
        result = _lufs_momentary(channels, SR)
        assert result > -30.0

    def test_momentary_max_gte_integrated(self) -> None:
        """Momentary (no gating) is always >= integrated (gated)."""
        from core.mix_analysis.dynamics import _compute_lufs
        from core.mix_analysis.mastering import _lufs_momentary

        t = np.linspace(0, 3.0, SR * 3)
        tone = 0.3 * np.sin(2 * np.pi * 1000 * t)
        channels = [tone]
        mom = _lufs_momentary(channels, SR)
        integrated = _compute_lufs(channels, SR)
        assert mom >= integrated - 1.0  # allow 1 LU tolerance


class TestLUFSShortTermMax:
    """_lufs_short_term_max — 3 s windows, no gating."""

    def test_silence_returns_minus_70(self) -> None:
        from core.mix_analysis.mastering import _lufs_short_term_max

        channels = [np.zeros(SR * 5)]
        result = _lufs_short_term_max(channels, SR)
        assert result == pytest.approx(-70.0, abs=1.0)

    def test_returns_max_over_windows(self) -> None:
        """Short-term max should capture the loudest 3-second window."""
        from core.mix_analysis.mastering import _lufs_short_term_max

        # First 3s quiet, next 3s loud
        quiet = np.zeros(SR * 3)
        t = np.linspace(0, 3.0, SR * 3)
        loud = 0.6 * np.sin(2 * np.pi * 440 * t)
        signal = np.concatenate([quiet, loud])
        channels = [signal]
        result = _lufs_short_term_max(channels, SR)
        assert result > -20.0


class TestTruePeak:
    """_true_peak — 4x oversampling."""

    def test_silent_signal_near_minus_96(self) -> None:
        from core.mix_analysis.mastering import _true_peak

        mono = np.zeros(SR)
        result = _true_peak(mono)
        assert result <= -60.0  # very low for silence (eps adds small floor)

    def test_full_scale_near_0_dbfs(self) -> None:
        from core.mix_analysis.mastering import _true_peak

        # DC signal at 0 dBFS. After 4x polyphase interpolation, DC passes
        # through unchanged but the transient edges of the block can produce
        # inter-sample peaks slightly above 0 dBTP — that's the whole point of
        # the 4x oversampling measurement. We just verify it's in the expected
        # range (close to 0, not wildly wrong).
        mono = np.ones(SR, dtype=float)
        result = _true_peak(mono)
        assert -2.0 <= result <= 3.0  # near 0 dBFS, possibly slightly above

    def test_half_amplitude_near_minus_6(self) -> None:
        from core.mix_analysis.mastering import _true_peak

        mono = 0.5 * np.ones(SR, dtype=float)
        result = _true_peak(mono)
        assert result == pytest.approx(-6.0, abs=1.5)

    def test_empty_array_returns_low_value(self) -> None:
        from core.mix_analysis.mastering import _true_peak

        result = _true_peak(np.array([]))
        assert result <= -60.0


class TestInterSamplePeaks:
    """_count_inter_sample_peaks — counts 4x frames above ceiling."""

    def test_silence_has_zero_peaks(self) -> None:
        from core.mix_analysis.mastering import _count_inter_sample_peaks

        result = _count_inter_sample_peaks(np.zeros(SR))
        assert result == 0

    def test_soft_signal_has_few_peaks(self) -> None:
        from core.mix_analysis.mastering import _count_inter_sample_peaks

        mono = 0.1 * np.ones(SR, dtype=float)
        result = _count_inter_sample_peaks(mono, ceiling_db=-0.5)
        assert result == 0

    def test_loud_signal_has_many_peaks(self) -> None:
        from core.mix_analysis.mastering import _count_inter_sample_peaks

        mono = np.ones(SR, dtype=float)  # 0 dBFS DC — guaranteed over -0.5
        result = _count_inter_sample_peaks(mono, ceiling_db=-0.5)
        assert result > 0

    def test_returns_int(self) -> None:
        from core.mix_analysis.mastering import _count_inter_sample_peaks

        result = _count_inter_sample_peaks(np.zeros(SR))
        assert isinstance(result, int)


class TestSectionDynamics:
    """_section_dynamics — 4 equal sections."""

    def test_returns_four_sections(self) -> None:
        from core.mix_analysis.mastering import _section_dynamics

        mono = 0.3 * np.ones(SR * 10, dtype=float)
        sections = _section_dynamics(mono, SR)
        assert len(sections) == 4

    def test_section_labels(self) -> None:
        from core.mix_analysis.mastering import _section_dynamics

        mono = 0.3 * np.ones(SR * 10, dtype=float)
        sections = _section_dynamics(mono, SR)
        labels = [s.label for s in sections]
        assert labels == ["intro", "build", "drop", "outro"]

    def test_start_times_are_ordered(self) -> None:
        from core.mix_analysis.mastering import _section_dynamics

        mono = 0.3 * np.ones(SR * 10, dtype=float)
        sections = _section_dynamics(mono, SR)
        times = [s.start_sec for s in sections]
        assert times == sorted(times)

    def test_crest_factor_non_negative(self) -> None:
        from core.mix_analysis.mastering import _section_dynamics

        t = np.linspace(0, 10.0, SR * 10)
        mono = 0.3 * np.sin(2 * np.pi * 440 * t)
        sections = _section_dynamics(mono, SR)
        for s in sections:
            assert s.crest_factor >= 0.0

    def test_sections_are_section_dynamics_type(self) -> None:
        from core.mix_analysis.mastering import _section_dynamics

        mono = 0.3 * np.ones(SR * 8, dtype=float)
        sections = _section_dynamics(mono, SR)
        for s in sections:
            assert isinstance(s, SectionDynamics)


class TestSpectralBalanceLabel:
    """_spectral_balance_label — maps tilt to label."""

    def test_dark_below_minus_7(self) -> None:
        from core.mix_analysis.mastering import _spectral_balance_label

        assert _spectral_balance_label(-8.0, "organic house") == "dark"

    def test_slightly_dark(self) -> None:
        from core.mix_analysis.mastering import _spectral_balance_label

        assert _spectral_balance_label(-6.5, "organic house") == "slightly dark"

    def test_neutral(self) -> None:
        from core.mix_analysis.mastering import _spectral_balance_label

        assert _spectral_balance_label(-4.0, "organic house") == "neutral"

    def test_slightly_bright(self) -> None:
        from core.mix_analysis.mastering import _spectral_balance_label

        assert _spectral_balance_label(-1.5, "organic house") == "slightly bright"

    def test_bright_above_minus_1(self) -> None:
        from core.mix_analysis.mastering import _spectral_balance_label

        assert _spectral_balance_label(0.0, "organic house") == "bright"


class TestReadinessScore:
    """_readiness_score — 0-100 score computation."""

    def test_perfect_track_scores_100(self) -> None:
        from core.mix_analysis.mastering import _readiness_score

        # Within LUFS range, good true peak, good crest, no ISPs, neutral tilt
        score, issues = _readiness_score(
            lufs=-7.0, true_peak=-2.0, crest=10.0, inter_sample=0, tilt=-4.5, genre="organic house"
        )
        assert score == pytest.approx(100.0)
        assert len(issues) == 0

    def test_too_quiet_reduces_score(self) -> None:
        from core.mix_analysis.mastering import _readiness_score

        score, issues = _readiness_score(
            lufs=-20.0, true_peak=-2.0, crest=10.0, inter_sample=0, tilt=-4.5, genre="organic house"
        )
        assert score < 100.0
        assert any("LUFS" in issue or "below" in issue for issue in issues)

    def test_clipped_true_peak_reduces_score(self) -> None:
        from core.mix_analysis.mastering import _readiness_score

        # true_peak=+0.5 dBTP → excess=1.5 → deduct min(20, 10+1.5×5)=17.5 pts
        # → score=82.5. Assert it's reduced from 100 and an issue is listed.
        score, issues = _readiness_score(
            lufs=-7.0, true_peak=0.5, crest=10.0, inter_sample=0, tilt=-4.5, genre="organic house"
        )
        assert score < 100.0
        assert any("true peak" in issue.lower() or "peak" in issue.lower() for issue in issues)

    def test_many_inter_sample_peaks_reduces_score(self) -> None:
        from core.mix_analysis.mastering import _readiness_score

        score, issues = _readiness_score(
            lufs=-7.0,
            true_peak=-2.0,
            crest=10.0,
            inter_sample=600,
            tilt=-4.5,
            genre="organic house",
        )
        assert score < 100.0
        assert any("inter-sample" in issue.lower() or "peak" in issue.lower() for issue in issues)

    def test_score_never_below_zero(self) -> None:
        from core.mix_analysis.mastering import _readiness_score

        score, _ = _readiness_score(
            lufs=-30.0, true_peak=2.0, crest=1.0, inter_sample=1000, tilt=3.0, genre="organic house"
        )
        assert score >= 0.0

    def test_score_never_above_100(self) -> None:
        from core.mix_analysis.mastering import _readiness_score

        score, _ = _readiness_score(
            lufs=-7.0, true_peak=-3.0, crest=12.0, inter_sample=0, tilt=-4.5, genre="organic house"
        )
        assert score <= 100.0


class TestAnalyzeMaster:
    """analyze_master() — public API integration."""

    def _make_tone(self, duration_sec: float = 5.0, amplitude: float = 0.3) -> np.ndarray:
        t = np.linspace(0, duration_sec, int(SR * duration_sec))
        return (amplitude * np.sin(2 * np.pi * 440 * t)).astype(float)

    def test_returns_master_analysis(self) -> None:
        from core.mix_analysis.mastering import analyze_master

        mono = self._make_tone()
        result = analyze_master(mono, SR, genre="organic house")
        assert isinstance(result, MasterAnalysis)

    def test_lufs_integrated_in_range(self) -> None:
        from core.mix_analysis.mastering import analyze_master

        mono = self._make_tone()
        result = analyze_master(mono, SR, genre="organic house")
        assert -70.0 <= result.lufs_integrated <= 0.0

    def test_true_peak_is_float(self) -> None:
        from core.mix_analysis.mastering import analyze_master

        mono = self._make_tone()
        result = analyze_master(mono, SR, genre="organic house")
        assert isinstance(result.true_peak_db, float)

    def test_readiness_score_in_range(self) -> None:
        from core.mix_analysis.mastering import analyze_master

        mono = self._make_tone()
        result = analyze_master(mono, SR, genre="organic house")
        assert 0.0 <= result.readiness_score <= 100.0

    def test_four_sections_returned(self) -> None:
        from core.mix_analysis.mastering import analyze_master

        mono = self._make_tone(duration_sec=10.0)
        result = analyze_master(mono, SR, genre="organic house")
        assert len(result.sections) == 4

    def test_inter_sample_peaks_non_negative_int(self) -> None:
        from core.mix_analysis.mastering import analyze_master

        mono = self._make_tone()
        result = analyze_master(mono, SR, genre="organic house")
        assert result.inter_sample_peaks >= 0
        assert isinstance(result.inter_sample_peaks, int)

    def test_spectral_balance_is_string(self) -> None:
        from core.mix_analysis.mastering import analyze_master

        mono = self._make_tone()
        result = analyze_master(mono, SR, genre="organic house")
        valid_labels = {"dark", "slightly dark", "neutral", "slightly bright", "bright"}
        assert result.spectral_balance in valid_labels

    def test_stereo_input_works(self) -> None:
        from core.mix_analysis.mastering import analyze_master

        tone = self._make_tone()
        stereo = np.stack([tone, tone * 0.9])
        result = analyze_master(stereo, SR, genre="organic house")
        assert isinstance(result, MasterAnalysis)

    def test_zero_sr_raises_value_error(self) -> None:
        from core.mix_analysis.mastering import analyze_master

        with pytest.raises(ValueError, match="Sample rate"):
            analyze_master(self._make_tone(), 0)

    def test_empty_array_raises_value_error(self) -> None:
        from core.mix_analysis.mastering import analyze_master

        with pytest.raises(ValueError, match="empty"):
            analyze_master(np.array([]), SR)

    def test_issues_is_tuple_of_strings(self) -> None:
        from core.mix_analysis.mastering import analyze_master

        mono = self._make_tone()
        result = analyze_master(mono, SR, genre="organic house")
        assert isinstance(result.issues, tuple)
        for issue in result.issues:
            assert isinstance(issue, str)


# ===========================================================================
# 3. TestChains — core/mix_analysis/chains.py
# ===========================================================================


class TestGetChain:
    """get_chain() — loads YAML, returns SignalChain."""

    @pytest.mark.parametrize(
        "genre",
        ["organic house", "melodic techno", "deep house", "progressive house", "afro house"],
    )
    def test_mix_bus_chain_loads_for_all_genres(self, genre: str) -> None:
        from core.mix_analysis.chains import get_chain

        chain = get_chain(genre, "mix_bus")
        assert isinstance(chain, SignalChain)
        assert chain.genre == genre
        assert chain.stage == "mix_bus"
        assert len(chain.processors) >= 1

    @pytest.mark.parametrize(
        "genre",
        ["organic house", "melodic techno", "deep house", "progressive house", "afro house"],
    )
    def test_master_chain_loads_for_all_genres(self, genre: str) -> None:
        from core.mix_analysis.chains import get_chain

        chain = get_chain(genre, "master")
        assert isinstance(chain, SignalChain)
        assert chain.stage == "master"

    def test_chain_processors_have_params(self) -> None:
        from core.mix_analysis.chains import get_chain

        chain = get_chain("organic house", "mix_bus")
        for proc in chain.processors:
            assert isinstance(proc, Processor)
            assert proc.plugin_primary
            assert proc.plugin_fallback

    def test_processor_params_are_processor_param_type(self) -> None:
        from core.mix_analysis.chains import get_chain

        chain = get_chain("organic house", "mix_bus")
        for proc in chain.processors:
            for param in proc.params:
                assert isinstance(param, ProcessorParam)
                assert isinstance(param.name, str)
                assert isinstance(param.value, str)

    def test_unknown_genre_raises_value_error(self) -> None:
        from core.mix_analysis.chains import get_chain

        with pytest.raises(ValueError, match="Unknown genre"):
            get_chain("dubstep", "mix_bus")

    def test_unknown_stage_raises_value_error(self) -> None:
        from core.mix_analysis.chains import get_chain

        with pytest.raises(ValueError, match="Unknown stage"):
            get_chain("organic house", "preamp")

    def test_cache_is_used(self) -> None:
        """Calling get_chain twice with same args returns same object (cache hit)."""
        from core.mix_analysis.chains import get_chain

        chain1 = get_chain("organic house", "mix_bus")
        chain2 = get_chain("organic house", "mix_bus")
        assert chain1 is chain2

    def test_case_insensitive_genre(self) -> None:
        from core.mix_analysis.chains import get_chain

        chain = get_chain("Organic House", "mix_bus")
        assert chain.genre == "organic house"

    def test_description_is_non_empty(self) -> None:
        from core.mix_analysis.chains import get_chain

        chain = get_chain("organic house", "mix_bus")
        assert len(chain.description) > 0

    def test_get_param_method(self) -> None:
        from core.mix_analysis.chains import get_chain

        chain = get_chain("organic house", "mix_bus")
        # At least one processor should have a recognisable param
        proc = chain.processors[0]
        # get_param returns None for missing, str for present
        result = proc.get_param("nonexistent_param")
        assert result is None


class TestAvailableStagesAndGenres:
    def test_available_stages_returns_list(self) -> None:
        from core.mix_analysis.chains import available_stages

        stages = available_stages()
        assert "mix_bus" in stages
        assert "master" in stages

    def test_available_genres_returns_5_genres(self) -> None:
        from core.mix_analysis.chains import available_genres

        genres = available_genres("mix_bus")
        assert len(genres) == 5

    def test_available_genres_unknown_stage_raises(self) -> None:
        from core.mix_analysis.chains import available_genres

        with pytest.raises(ValueError, match="Unknown stage"):
            available_genres("drums")


# ===========================================================================
# 4. TestMixEngine — ingestion/mix_engine.py
# ===========================================================================


def _make_mix_report(genre: str = "organic house") -> MixReport:
    """Build a minimal MixReport for tool tests."""
    freq = _make_freq()
    stereo = _make_stereo()
    dyn = _make_dynamics()
    trans = TransientProfile(density=2.0, sharpness=0.6, attack_ratio=0.3)
    return MixReport(
        frequency=freq,
        stereo=stereo,
        dynamics=dyn,
        transients=trans,
        problems=(_make_problem("muddiness", severity=5.0),),
        recommendations=(),
        genre=genre,
        duration_sec=30.0,
        sample_rate=SR,
    )


def _make_master_report(genre: str = "organic house") -> MasterReport:
    """Build a minimal MasterReport for tool tests."""
    from core.mix_analysis.chains import get_chain

    master = MasterAnalysis(
        lufs_integrated=-7.5,
        lufs_short_term_max=-6.0,
        lufs_momentary_max=-5.0,
        true_peak_db=-1.5,
        inter_sample_peaks=12,
        crest_factor=10.0,
        sections=(
            SectionDynamics(
                label="intro", start_sec=0.0, rms_db=-16.0, peak_db=-6.0, crest_factor=10.0
            ),
            SectionDynamics(
                label="build", start_sec=7.5, rms_db=-14.0, peak_db=-4.0, crest_factor=10.0
            ),
            SectionDynamics(
                label="drop", start_sec=15.0, rms_db=-12.0, peak_db=-2.0, crest_factor=10.0
            ),
            SectionDynamics(
                label="outro", start_sec=22.5, rms_db=-16.0, peak_db=-6.0, crest_factor=10.0
            ),
        ),
        spectral_balance="neutral",
        readiness_score=92.0,
        issues=(),
    )
    chain = get_chain(genre, "master")
    return MasterReport(
        master=master,
        suggested_chain=chain,
        genre=genre,
        duration_sec=30.0,
        sample_rate=SR,
    )


class TestMixAnalysisEngine:
    """MixAnalysisEngine — unit tests with mocked audio loading."""

    def _make_stereo_audio(self) -> np.ndarray:
        t = np.linspace(0, 3.0, SR * 3)
        tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(float)
        return np.stack([tone, tone * 0.95])

    @patch("ingestion.mix_engine.load_audio")
    def test_full_mix_analysis_returns_mix_report(self, mock_load: MagicMock) -> None:
        from ingestion.mix_engine import MixAnalysisEngine

        audio = self._make_stereo_audio()
        mock_load.return_value = (audio, SR)

        engine = MixAnalysisEngine()
        report = engine.full_mix_analysis("/fake/track.wav", genre="organic house")

        assert isinstance(report, MixReport)
        assert report.genre == "organic house"
        assert report.sample_rate == SR

    @patch("ingestion.mix_engine.load_audio")
    def test_full_mix_analysis_has_all_fields(self, mock_load: MagicMock) -> None:
        from ingestion.mix_engine import MixAnalysisEngine

        audio = self._make_stereo_audio()
        mock_load.return_value = (audio, SR)

        engine = MixAnalysisEngine()
        report = engine.full_mix_analysis("/fake/track.wav")

        assert isinstance(report.frequency, FrequencyProfile)
        assert report.stereo is not None
        assert isinstance(report.dynamics, DynamicProfile)
        assert isinstance(report.transients, TransientProfile)
        assert isinstance(report.problems, tuple)
        assert isinstance(report.recommendations, tuple)

    @patch("ingestion.mix_engine.load_audio")
    def test_master_analysis_returns_master_report(self, mock_load: MagicMock) -> None:
        from ingestion.mix_engine import MixAnalysisEngine

        audio = self._make_stereo_audio()
        mock_load.return_value = (audio, SR)

        engine = MixAnalysisEngine()
        report = engine.master_analysis("/fake/track.wav", genre="organic house")

        assert isinstance(report, MasterReport)
        assert isinstance(report.master, MasterAnalysis)
        assert report.suggested_chain is not None

    @patch("ingestion.mix_engine.load_audio")
    def test_mono_input_sets_stereo_none(self, mock_load: MagicMock) -> None:
        from ingestion.mix_engine import MixAnalysisEngine

        t = np.linspace(0, 3.0, SR * 3)
        mono = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(float)
        mock_load.return_value = (mono, SR)

        engine = MixAnalysisEngine()
        report = engine.full_mix_analysis("/fake/mono.wav")
        # Mono input → stereo is None
        assert report.stereo is None

    @patch("ingestion.mix_engine.load_audio")
    def test_rag_enhancement_injects_citations(self, mock_load: MagicMock) -> None:
        from ingestion.mix_engine import MixAnalysisEngine

        audio = self._make_stereo_audio()
        mock_load.return_value = (audio, SR)

        citations_returned = ["citation 1", "citation 2"]
        mock_search = MagicMock(return_value=citations_returned)

        engine = MixAnalysisEngine(search_fn=mock_search)
        report = engine.full_mix_analysis("/fake/track.wav")

        # If there were any recommendations, they should have citations
        for rec in report.recommendations:
            assert rec.rag_citations == tuple(citations_returned)

    @patch("ingestion.mix_engine.load_audio")
    def test_rag_failure_does_not_crash(self, mock_load: MagicMock) -> None:
        from ingestion.mix_engine import MixAnalysisEngine

        audio = self._make_stereo_audio()
        mock_load.return_value = (audio, SR)

        def failing_search(query: str) -> list[str]:
            raise RuntimeError("RAG unavailable")

        engine = MixAnalysisEngine(search_fn=failing_search)
        # Should not raise
        report = engine.full_mix_analysis("/fake/track.wav")
        assert isinstance(report, MixReport)

    def test_recommend_processing_pure_call(self) -> None:
        from ingestion.mix_engine import MixAnalysisEngine

        engine = MixAnalysisEngine()
        problems = [_make_problem("muddiness", severity=5.0)]
        recs = engine.recommend_processing(
            problems, _make_freq(), _make_stereo(), _make_dynamics(), "organic house"
        )
        assert isinstance(recs, list)


# ===========================================================================
# 5. TestAnalyzeMixTool — tools/music/analyze_mix.py
# ===========================================================================


class TestAnalyzeMixTool:
    """AnalyzeMix MCP tool."""

    def _run(self, **kwargs: object) -> object:
        from tools.music.analyze_mix import AnalyzeMix

        tool = AnalyzeMix()
        return tool.execute(**kwargs)

    def test_missing_file_path_returns_error(self) -> None:
        result = self._run(file_path="", genre="organic house")
        assert not result.success
        assert "file_path" in result.error.lower() or "empty" in result.error.lower()

    def test_unknown_genre_returns_error(self) -> None:
        result = self._run(file_path="/fake/track.wav", genre="jazz")
        assert not result.success
        assert "genre" in result.error.lower()

    @patch("ingestion.mix_engine.load_audio")
    def test_successful_analysis_returns_all_sections(self, mock_load: MagicMock) -> None:
        from tools.music.analyze_mix import AnalyzeMix

        t = np.linspace(0, 3.0, SR * 3)
        tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(float)
        stereo = np.stack([tone, tone * 0.95])
        mock_load.return_value = (stereo, SR)

        tool = AnalyzeMix()
        result = tool.execute(file_path="/fake/track.wav", genre="organic house")

        assert result.success
        assert "spectral" in result.data
        assert "stereo" in result.data
        assert "dynamics" in result.data
        assert "transients" in result.data
        assert "problems" in result.data
        assert "recommendations" in result.data

    @patch("ingestion.mix_engine.load_audio")
    def test_spectral_data_has_bands(self, mock_load: MagicMock) -> None:
        from tools.music.analyze_mix import AnalyzeMix

        t = np.linspace(0, 3.0, SR * 3)
        tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(float)
        mock_load.return_value = (tone, SR)

        tool = AnalyzeMix()
        result = tool.execute(file_path="/fake/track.wav")

        assert result.success
        spectral = result.data["spectral"]
        assert "bands" in spectral
        assert "spectral_centroid_hz" in spectral
        assert "spectral_tilt_db_oct" in spectral

    @patch("ingestion.mix_engine.load_audio")
    def test_dynamics_data_has_lufs(self, mock_load: MagicMock) -> None:
        from tools.music.analyze_mix import AnalyzeMix

        t = np.linspace(0, 3.0, SR * 3)
        tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(float)
        mock_load.return_value = (tone, SR)

        tool = AnalyzeMix()
        result = tool.execute(file_path="/fake/track.wav")

        assert result.success
        dynamics = result.data["dynamics"]
        assert "lufs" in dynamics
        assert "crest_factor_db" in dynamics

    def test_file_not_found_returns_error(self) -> None:
        result = self._run(file_path="/nonexistent/track.wav", genre="organic house")
        assert not result.success

    def test_tool_name(self) -> None:
        from tools.music.analyze_mix import AnalyzeMix

        assert AnalyzeMix().name == "analyze_mix"

    def test_tool_has_description(self) -> None:
        from tools.music.analyze_mix import AnalyzeMix

        assert len(AnalyzeMix().description) > 20

    def test_tool_has_three_parameters(self) -> None:
        from tools.music.analyze_mix import AnalyzeMix

        assert len(AnalyzeMix().parameters) == 3


# ===========================================================================
# 6. TestRecommendChainTool — tools/music/recommend_chain.py
# ===========================================================================


class TestRecommendChainTool:
    """RecommendChain MCP tool."""

    def _run(self, **kwargs: object) -> object:
        from tools.music.recommend_chain import RecommendChain

        tool = RecommendChain()
        return tool.execute(**kwargs)

    def test_returns_mix_bus_chain(self) -> None:
        result = self._run(genre="organic house", stage="mix_bus")
        assert result.success
        data = result.data
        assert data["genre"] == "organic house"
        assert data["stage"] == "mix_bus"
        assert len(data["processors"]) >= 1

    def test_returns_master_chain(self) -> None:
        result = self._run(genre="organic house", stage="master")
        assert result.success
        assert result.data["stage"] == "master"

    def test_all_genres_return_success(self) -> None:
        genres = [
            "organic house",
            "melodic techno",
            "deep house",
            "progressive house",
            "afro house",
        ]
        for genre in genres:
            result = self._run(genre=genre, stage="mix_bus")
            assert result.success, f"Failed for genre={genre}"

    def test_unknown_genre_returns_error(self) -> None:
        result = self._run(genre="drum and bass", stage="mix_bus")
        assert not result.success

    def test_unknown_stage_returns_error(self) -> None:
        result = self._run(genre="organic house", stage="drums")
        assert not result.success

    def test_processors_have_expected_fields(self) -> None:
        result = self._run(genre="organic house", stage="mix_bus")
        assert result.success
        for proc in result.data["processors"]:
            assert "name" in proc
            assert "proc_type" in proc
            assert "plugin_primary" in proc
            assert "plugin_fallback" in proc
            assert "params" in proc

    def test_params_have_name_and_value(self) -> None:
        result = self._run(genre="organic house", stage="mix_bus")
        assert result.success
        for proc in result.data["processors"]:
            for param in proc["params"]:
                assert "name" in param
                assert "value" in param

    def test_default_genre_is_organic_house(self) -> None:
        result = self._run()
        assert result.success
        assert result.data["genre"] == "organic house"

    def test_default_stage_is_mix_bus(self) -> None:
        result = self._run(genre="organic house")
        assert result.success
        assert result.data["stage"] == "mix_bus"

    def test_tool_name(self) -> None:
        from tools.music.recommend_chain import RecommendChain

        assert RecommendChain().name == "recommend_chain"

    def test_description_is_non_empty(self) -> None:
        from tools.music.recommend_chain import RecommendChain

        assert len(RecommendChain().description) > 20

    def test_metadata_has_processor_count(self) -> None:
        result = self._run(genre="organic house", stage="mix_bus")
        assert result.success
        assert "processor_count" in result.metadata
        assert result.metadata["processor_count"] >= 1


# ===========================================================================
# 7. TestAnalyzeMasterTool — tools/music/analyze_master.py
# ===========================================================================


class TestAnalyzeMasterTool:
    """AnalyzeMaster MCP tool."""

    def _run(self, **kwargs: object) -> object:
        from tools.music.analyze_master import AnalyzeMaster

        tool = AnalyzeMaster()
        return tool.execute(**kwargs)

    def test_missing_file_path_returns_error(self) -> None:
        result = self._run(file_path="", genre="organic house")
        assert not result.success

    def test_unknown_genre_returns_error(self) -> None:
        result = self._run(file_path="/fake/master.wav", genre="jazz")
        assert not result.success

    @patch("ingestion.mix_engine.load_audio")
    def test_successful_analysis_returns_all_sections(self, mock_load: MagicMock) -> None:
        from tools.music.analyze_master import AnalyzeMaster

        t = np.linspace(0, 5.0, SR * 5)
        tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(float)
        stereo = np.stack([tone, tone * 0.95])
        mock_load.return_value = (stereo, SR)

        tool = AnalyzeMaster()
        result = tool.execute(file_path="/fake/master.wav", genre="organic house")

        assert result.success
        assert "loudness" in result.data
        assert "dynamics" in result.data
        assert "spectral_balance" in result.data
        assert "readiness_score" in result.data
        assert "issues" in result.data
        assert "mastering_chain" in result.data

    @patch("ingestion.mix_engine.load_audio")
    def test_loudness_has_three_lufs_values(self, mock_load: MagicMock) -> None:
        from tools.music.analyze_master import AnalyzeMaster

        t = np.linspace(0, 5.0, SR * 5)
        tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(float)
        mock_load.return_value = (tone, SR)

        tool = AnalyzeMaster()
        result = tool.execute(file_path="/fake/master.wav")

        assert result.success
        loudness = result.data["loudness"]
        assert "lufs_integrated" in loudness
        assert "lufs_short_term_max" in loudness
        assert "lufs_momentary_max" in loudness
        assert "true_peak_db" in loudness
        assert "inter_sample_peaks" in loudness

    @patch("ingestion.mix_engine.load_audio")
    def test_dynamics_has_four_sections(self, mock_load: MagicMock) -> None:
        from tools.music.analyze_master import AnalyzeMaster

        t = np.linspace(0, 10.0, SR * 10)
        tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(float)
        mock_load.return_value = (tone, SR)

        tool = AnalyzeMaster()
        result = tool.execute(file_path="/fake/master.wav")

        assert result.success
        sections = result.data["dynamics"]["sections"]
        assert len(sections) == 4

    @patch("ingestion.mix_engine.load_audio")
    def test_readiness_score_in_0_100(self, mock_load: MagicMock) -> None:
        from tools.music.analyze_master import AnalyzeMaster

        t = np.linspace(0, 5.0, SR * 5)
        tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(float)
        mock_load.return_value = (tone, SR)

        tool = AnalyzeMaster()
        result = tool.execute(file_path="/fake/master.wav")

        assert result.success
        score = result.data["readiness_score"]
        assert 0.0 <= score <= 100.0

    @patch("ingestion.mix_engine.load_audio")
    def test_mastering_chain_has_processors(self, mock_load: MagicMock) -> None:
        from tools.music.analyze_master import AnalyzeMaster

        t = np.linspace(0, 5.0, SR * 5)
        tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(float)
        mock_load.return_value = (tone, SR)

        tool = AnalyzeMaster()
        result = tool.execute(file_path="/fake/master.wav")

        assert result.success
        chain = result.data["mastering_chain"]
        assert len(chain["processors"]) >= 1

    def test_file_not_found_returns_error(self) -> None:
        result = self._run(file_path="/nonexistent/master.wav")
        assert not result.success

    def test_tool_name(self) -> None:
        from tools.music.analyze_master import AnalyzeMaster

        assert AnalyzeMaster().name == "analyze_master"

    def test_tool_has_three_parameters(self) -> None:
        from tools.music.analyze_master import AnalyzeMaster

        assert len(AnalyzeMaster().parameters) == 3

    @patch("ingestion.mix_engine.load_audio")
    def test_is_ready_metadata_flag(self, mock_load: MagicMock) -> None:
        from tools.music.analyze_master import AnalyzeMaster

        t = np.linspace(0, 5.0, SR * 5)
        tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(float)
        mock_load.return_value = (tone, SR)

        tool = AnalyzeMaster()
        result = tool.execute(file_path="/fake/master.wav", genre="organic house")

        assert result.success
        assert "is_ready" in result.metadata
        assert isinstance(result.metadata["is_ready"], bool)


# ===========================================================================
# 8. Integration — end-to-end with synthetic audio
# ===========================================================================


class TestWeek17Integration:
    """Full pipeline smoke tests with synthetic audio arrays."""

    def _make_sine(
        self, freq_hz: float = 440.0, duration: float = 5.0, amp: float = 0.3
    ) -> np.ndarray:
        t = np.linspace(0, duration, int(SR * duration))
        return (amp * np.sin(2 * np.pi * freq_hz * t)).astype(float)

    def test_analyze_master_full_pipeline(self) -> None:
        """End-to-end: raw audio → MasterAnalysis with all fields populated."""
        from core.mix_analysis.mastering import analyze_master

        mono = self._make_sine()
        result = analyze_master(mono, SR, genre="organic house")

        assert isinstance(result, MasterAnalysis)
        assert result.lufs_integrated <= result.lufs_short_term_max
        assert result.lufs_short_term_max <= result.lufs_momentary_max + 1.0
        assert len(result.sections) == 4

    def test_chains_and_recommendations_compatible_genres(self) -> None:
        """All genres work with both chains.py and recommendations.py."""
        from core.mix_analysis.chains import get_chain
        from core.mix_analysis.recommendations import recommend_all

        genres = [
            "organic house",
            "melodic techno",
            "deep house",
            "progressive house",
            "afro house",
        ]
        problems = [_make_problem("muddiness", severity=5.0)]

        for genre in genres:
            chain = get_chain(genre, "mix_bus")
            assert chain is not None
            recs = recommend_all(problems, _make_freq(), None, _make_dynamics(), genre)
            assert len(recs) == 1

    def test_recommendation_steps_are_fix_step_type(self) -> None:
        from core.mix_analysis.recommendations import recommend_fix

        problem = _make_problem("muddiness", severity=5.0)
        rec = recommend_fix(problem, _make_freq(), None, _make_dynamics(), "organic house")

        for step in rec.steps:
            assert isinstance(step, FixStep)
            assert len(step.action) > 0
            assert len(step.bus) > 0

    def test_readiness_score_increases_toward_target(self) -> None:
        """A louder mix (closer to target) should score higher than a very quiet one."""
        from core.mix_analysis.mastering import analyze_master

        quiet = self._make_sine(amp=0.01, duration=5.0)  # very quiet
        loud = self._make_sine(amp=0.3, duration=5.0)  # moderate

        score_quiet = analyze_master(quiet, SR, genre="organic house").readiness_score
        score_loud = analyze_master(loud, SR, genre="organic house").readiness_score

        # Quiet mix has LUFS too far below target → lower score
        # This is not guaranteed in all cases but is expected for extreme quiet
        # Allow a tolerance of 1 point
        assert score_loud >= score_quiet - 1.0
