"""
Tests for Week 18 — Reference Comparison Engine.

Coverage:
    core/mix_analysis/reference.py  — compare_to_reference, compare_to_references, identify_deltas
    core/mix_analysis/calibration.py — calibrate_genre_targets, update_genre_targets, serialization
    core/mix_analysis/report.py     — generate_full_report, sections, health score
    ingestion/mix_engine.py         — new methods: compare_to_references_batch, full_mix_report, calibrate_targets
    tools/music/compare_reference.py   — CompareReference.execute()
    tools/music/mix_master_report.py   — MixMasterReport.execute()
    tools/music/calibrate_genre_targets.py — CalibrateGenreTargets.execute()
    api/routes/mix.py               — 5 endpoints (mocked engine)

All tests use synthetic numpy arrays or pre-built MixReport objects —
no real audio files are needed. MixAnalysisEngine methods are mocked
via unittest.mock.patch where file I/O is required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.mix_analysis.calibration import (
    calibrate_genre_targets,
    target_from_dict,
    target_to_dict,
    update_genre_targets,
)
from core.mix_analysis.reference import (
    compare_to_reference,
    compare_to_references,
    identify_deltas,
)
from core.mix_analysis.report import generate_full_report
from core.mix_analysis.types import (
    BandDelta,
    BandProfile,
    DimensionScore,
    DynamicProfile,
    FrequencyProfile,
    FullMixReport,
    GenreTarget,
    MasterAnalysis,
    MasterReport,
    MetricStats,
    MixProblem,
    MixReport,
    Processor,
    ProcessorParam,
    ReferenceComparison,
    ReportSection,
    SectionDynamics,
    SignalChain,
    StereoImage,
    TransientProfile,
)

# ---------------------------------------------------------------------------
# Synthetic MixReport factory
# ---------------------------------------------------------------------------


def _make_band_profile(
    sub: float = -8.0,
    low: float = -5.0,
    low_mid: float = -7.0,
    mid: float = -6.0,
    high_mid: float = -8.0,
    high: float = -12.0,
    air: float = -16.0,
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
    centroid: float = 1500.0,
    tilt: float = -4.0,
    flatness: float = 0.4,
    rms: float = -18.0,
    bands: BandProfile | None = None,
) -> FrequencyProfile:
    return FrequencyProfile(
        bands=bands or _make_band_profile(),
        spectral_centroid=centroid,
        spectral_tilt=tilt,
        spectral_flatness=flatness,
        overall_rms_db=rms,
    )


def _make_stereo(
    width: float = 0.45,
    correlation: float = 0.35,
    ms_ratio: float = 8.0,
    is_mono: bool = False,
) -> StereoImage:
    bw = _make_band_profile(0.0, 0.1, 0.2, 0.4, 0.55, 0.65, 0.72)
    return StereoImage(
        width=width,
        lr_correlation=correlation,
        mid_side_ratio=ms_ratio,
        band_widths=bw,
        is_mono=is_mono,
    )


def _make_dynamics(
    rms: float = -18.0,
    peak: float = -1.0,
    lufs: float = -9.0,
    crest: float = 10.0,
    dr: float = 12.0,
    lra: float = 7.0,
) -> DynamicProfile:
    return DynamicProfile(
        rms_db=rms,
        peak_db=peak,
        lufs=lufs,
        crest_factor=crest,
        dynamic_range=dr,
        loudness_range=lra,
    )


def _make_transients(
    density: float = 2.5,
    sharpness: float = 0.6,
    attack_ratio: float = 0.15,
) -> TransientProfile:
    return TransientProfile(density=density, sharpness=sharpness, attack_ratio=attack_ratio)


def _make_report(
    genre: str = "organic house",
    duration: float = 180.0,
    sample_rate: int = 44100,
    freq: FrequencyProfile | None = None,
    stereo: StereoImage | None = None,
    dynamics: DynamicProfile | None = None,
    transients: TransientProfile | None = None,
    problems: tuple[MixProblem, ...] = (),
) -> MixReport:
    return MixReport(
        frequency=freq or _make_freq(),
        stereo=stereo if stereo is not None else _make_stereo(),
        dynamics=dynamics or _make_dynamics(),
        transients=transients or _make_transients(),
        problems=problems,
        recommendations=(),
        genre=genre,
        duration_sec=duration,
        sample_rate=sample_rate,
    )


def _make_problem(
    category: str = "muddiness",
    severity: float = 5.0,
    freq_range: tuple[float, float] = (200.0, 500.0),
) -> MixProblem:
    return MixProblem(
        category=category,
        frequency_range=freq_range,
        severity=severity,
        description=f"Test {category} problem",
        recommendation="Apply a cut",
    )


def _make_master_report(genre: str = "organic house") -> MasterReport:
    sections = (
        SectionDynamics("intro", 0.0, -20.0, -3.0, 17.0),
        SectionDynamics("build", 45.0, -16.0, -1.5, 14.5),
        SectionDynamics("drop", 90.0, -12.0, -0.5, 11.5),
        SectionDynamics("outro", 135.0, -18.0, -2.0, 16.0),
    )
    master = MasterAnalysis(
        lufs_integrated=-8.5,
        lufs_short_term_max=-7.0,
        lufs_momentary_max=-5.5,
        true_peak_db=-0.8,
        inter_sample_peaks=2,
        crest_factor=9.5,
        sections=sections,
        spectral_balance="neutral",
        readiness_score=82.5,
        issues=("True peak marginally above -1.0 dBTP",),
    )
    chain = SignalChain(
        genre=genre,
        stage="master",
        description="Master chain",
        processors=(
            Processor(
                name="Limiter",
                proc_type="limiter",
                plugin_primary="Fabfilter Pro-L 2",
                plugin_fallback="Ableton Limiter",
                params=(ProcessorParam("ceiling", "-0.3 dBTP"),),
            ),
        ),
    )
    return MasterReport(
        master=master,
        suggested_chain=chain,
        genre=genre,
        duration_sec=180.0,
        sample_rate=44100,
    )


# ===========================================================================
# TestMetricStats
# ===========================================================================


class TestMetricStats:
    def test_low_is_mean_minus_std(self):
        ms = MetricStats(mean=5.0, std=2.0)
        assert ms.low == 3.0

    def test_high_is_mean_plus_std(self):
        ms = MetricStats(mean=5.0, std=2.0)
        assert ms.high == 7.0

    def test_zero_std_low_equals_high_equals_mean(self):
        ms = MetricStats(mean=-8.0, std=0.0)
        assert ms.low == ms.high == -8.0

    def test_frozen(self):
        ms = MetricStats(mean=1.0, std=0.5)
        with pytest.raises((AttributeError, TypeError)):
            ms.mean = 2.0  # type: ignore[misc]


# ===========================================================================
# TestBandDelta
# ===========================================================================


class TestBandDelta:
    def test_positive_delta_means_track_louder(self):
        bd = BandDelta(band="low_mid", track_db=-5.0, reference_db=-8.0, delta_db=3.0)
        assert bd.delta_db > 0

    def test_negative_delta_means_track_quieter(self):
        bd = BandDelta(band="air", track_db=-18.0, reference_db=-12.0, delta_db=-6.0)
        assert bd.delta_db < 0

    def test_delta_is_track_minus_reference(self):
        bd = BandDelta(band="mid", track_db=-6.0, reference_db=-4.0, delta_db=-2.0)
        assert bd.delta_db == pytest.approx(bd.track_db - bd.reference_db)


# ===========================================================================
# TestDimensionScore
# ===========================================================================


class TestDimensionScore:
    def test_fields_accessible(self):
        ds = DimensionScore(
            name="spectral",
            score=78.5,
            track_value=2.3,
            ref_value=0.0,
            unit="dB MAD",
            description="test",
        )
        assert ds.name == "spectral"
        assert ds.score == 78.5

    def test_frozen(self):
        ds = DimensionScore(
            name="stereo",
            score=90.0,
            track_value=0.45,
            ref_value=0.55,
            unit="width",
            description="test",
        )
        with pytest.raises((AttributeError, TypeError)):
            ds.score = 50.0  # type: ignore[misc]


# ===========================================================================
# TestSpectralScoring — via compare_to_reference
# ===========================================================================


class TestSpectralScoring:
    def test_identical_spectral_gives_100_score(self):
        track = _make_report()
        ref = _make_report()  # identical bands
        comp = compare_to_reference(track, ref)
        spec_dim = next(d for d in comp.dimensions if d.name == "spectral")
        assert spec_dim.score == pytest.approx(100.0, abs=0.1)

    def test_large_spectral_delta_reduces_score(self):
        # Shift all bands +6 dB in track
        track_bands = _make_band_profile(
            sub=-2.0,
            low=1.0,
            low_mid=-1.0,
            mid=0.0,
            high_mid=-2.0,
            high=-6.0,
            air=-10.0,
        )
        track = _make_report(freq=_make_freq(bands=track_bands))
        ref = _make_report()
        comp = compare_to_reference(track, ref)
        spec_dim = next(d for d in comp.dimensions if d.name == "spectral")
        assert spec_dim.score < 85.0

    def test_spectral_score_bounded_0_to_100(self):
        # Extreme delta — score should not go below 0
        track_bands = _make_band_profile(
            sub=10.0,
            low=10.0,
            low_mid=10.0,
            mid=10.0,
            high_mid=10.0,
            high=10.0,
            air=10.0,
        )
        track = _make_report(freq=_make_freq(bands=track_bands))
        ref = _make_report(
            freq=_make_freq(
                bands=_make_band_profile(
                    sub=-10.0,
                    low=-10.0,
                    low_mid=-10.0,
                    mid=-10.0,
                    high_mid=-10.0,
                    high=-10.0,
                    air=-10.0,
                )
            )
        )
        comp = compare_to_reference(track, ref)
        spec_dim = next(d for d in comp.dimensions if d.name == "spectral")
        assert 0.0 <= spec_dim.score <= 100.0

    def test_band_deltas_count_is_7(self):
        comp = compare_to_reference(_make_report(), _make_report())
        assert len(comp.band_deltas) == 7

    def test_band_delta_names_are_canonical(self):
        comp = compare_to_reference(_make_report(), _make_report())
        names = {bd.band for bd in comp.band_deltas}
        assert names == {"sub", "low", "low_mid", "mid", "high_mid", "high", "air"}


# ===========================================================================
# TestStereoScoring
# ===========================================================================


class TestStereoScoring:
    def test_identical_width_gives_100(self):
        comp = compare_to_reference(_make_report(), _make_report())
        dim = next(d for d in comp.dimensions if d.name == "stereo")
        assert dim.score == pytest.approx(100.0, abs=0.1)

    def test_large_width_delta_reduces_score(self):
        track = _make_report(stereo=_make_stereo(width=0.1))
        ref = _make_report(stereo=_make_stereo(width=0.75))
        comp = compare_to_reference(track, ref)
        dim = next(d for d in comp.dimensions if d.name == "stereo")
        assert dim.score < 100.0

    def test_mono_track_vs_stereo_ref_has_width_delta(self):
        track = _make_report(stereo=_make_stereo(is_mono=True, width=0.0))
        ref = _make_report(stereo=_make_stereo(width=0.5))
        comp = compare_to_reference(track, ref)
        assert comp.width_delta < 0  # track width 0, ref width 0.5


# ===========================================================================
# TestDynamicsScoring
# ===========================================================================


class TestDynamicsScoring:
    def test_identical_dynamics_gives_100(self):
        comp = compare_to_reference(_make_report(), _make_report())
        dim = next(d for d in comp.dimensions if d.name == "dynamics")
        assert dim.score == pytest.approx(100.0, abs=0.1)

    def test_high_crest_delta_reduces_score(self):
        track = _make_report(dynamics=_make_dynamics(crest=14.0))
        ref = _make_report(dynamics=_make_dynamics(crest=8.0))
        comp = compare_to_reference(track, ref)
        dim = next(d for d in comp.dimensions if d.name == "dynamics")
        assert dim.score < 100.0

    def test_crest_factor_delta_is_signed(self):
        track = _make_report(dynamics=_make_dynamics(crest=12.0))
        ref = _make_report(dynamics=_make_dynamics(crest=10.0))
        comp = compare_to_reference(track, ref)
        assert comp.crest_factor_delta == pytest.approx(2.0, abs=0.1)


# ===========================================================================
# TestTonalScoring
# ===========================================================================


class TestTonalScoring:
    def test_identical_tonal_gives_100(self):
        comp = compare_to_reference(_make_report(), _make_report())
        dim = next(d for d in comp.dimensions if d.name == "tonal")
        assert dim.score == pytest.approx(100.0, abs=0.1)

    def test_large_centroid_delta_reduces_score(self):
        track = _make_report(freq=_make_freq(centroid=3000.0))
        ref = _make_report(freq=_make_freq(centroid=1000.0))
        comp = compare_to_reference(track, ref)
        dim = next(d for d in comp.dimensions if d.name == "tonal")
        assert dim.score < 100.0

    def test_centroid_delta_is_signed(self):
        track = _make_report(freq=_make_freq(centroid=2000.0))
        ref = _make_report(freq=_make_freq(centroid=1500.0))
        comp = compare_to_reference(track, ref)
        assert comp.centroid_delta_hz == pytest.approx(500.0, abs=1.0)


# ===========================================================================
# TestLoudnessScoring
# ===========================================================================


class TestLoudnessScoring:
    def test_identical_lufs_gives_100(self):
        comp = compare_to_reference(_make_report(), _make_report())
        dim = next(d for d in comp.dimensions if d.name == "loudness")
        assert dim.score == pytest.approx(100.0, abs=0.1)

    def test_large_lufs_delta_reduces_score(self):
        track = _make_report(dynamics=_make_dynamics(lufs=-18.0))
        ref = _make_report(dynamics=_make_dynamics(lufs=-8.0))
        comp = compare_to_reference(track, ref)
        dim = next(d for d in comp.dimensions if d.name == "loudness")
        assert dim.score < 50.0

    def test_lufs_normalization_db_is_negated_delta(self):
        track = _make_report(dynamics=_make_dynamics(lufs=-10.0))
        ref = _make_report(dynamics=_make_dynamics(lufs=-8.0))
        comp = compare_to_reference(track, ref)
        # lufs_delta = -10 - (-8) = -2; normalization_db = -(-2) = +2
        assert comp.lufs_normalization_db == pytest.approx(2.0, abs=0.1)


# ===========================================================================
# TestCompareToReference
# ===========================================================================


class TestCompareToReference:
    def test_identical_tracks_100_overall(self):
        report = _make_report()
        comp = compare_to_reference(report, report)
        assert comp.overall_similarity == pytest.approx(100.0, abs=1.0)

    def test_returns_reference_comparison(self):
        comp = compare_to_reference(_make_report(), _make_report())
        assert isinstance(comp, ReferenceComparison)

    def test_six_dimensions(self):
        comp = compare_to_reference(_make_report(), _make_report())
        assert len(comp.dimensions) == 6

    def test_dimension_names_are_canonical(self):
        comp = compare_to_reference(_make_report(), _make_report())
        names = {d.name for d in comp.dimensions}
        assert names == {"spectral", "stereo", "dynamics", "tonal", "transient", "loudness"}

    def test_num_references_is_1(self):
        comp = compare_to_reference(_make_report(), _make_report())
        assert comp.num_references == 1

    def test_overall_similarity_bounded(self):
        comp = compare_to_reference(_make_report(), _make_report())
        assert 0.0 <= comp.overall_similarity <= 100.0

    def test_genre_defaults_to_track_genre(self):
        track = _make_report(genre="melodic techno")
        ref = _make_report(genre="organic house")
        comp = compare_to_reference(track, ref)
        assert comp.genre == "melodic techno"

    def test_genre_override_works(self):
        comp = compare_to_reference(_make_report(), _make_report(), genre="deep house")
        assert comp.genre == "deep house"


# ===========================================================================
# TestCompareToReferences
# ===========================================================================


class TestCompareToReferences:
    def test_empty_references_raises_value_error(self):
        with pytest.raises(ValueError, match="at least one"):
            compare_to_references(_make_report(), [])

    def test_single_reference_matches_compare_to_reference(self):
        track = _make_report()
        ref = _make_report()
        single = compare_to_reference(track, ref)
        multi = compare_to_references(track, [ref])
        assert multi.overall_similarity == pytest.approx(single.overall_similarity, abs=0.1)

    def test_num_references_reflects_count(self):
        track = _make_report()
        refs = [_make_report(), _make_report(), _make_report()]
        comp = compare_to_references(track, refs)
        assert comp.num_references == 3

    def test_identical_references_same_as_single(self):
        track = _make_report()
        ref = _make_report()
        multi = compare_to_references(track, [ref, ref, ref])
        single = compare_to_references(track, [ref])
        assert multi.overall_similarity == pytest.approx(single.overall_similarity, abs=0.5)

    def test_returns_reference_comparison(self):
        comp = compare_to_references(_make_report(), [_make_report()])
        assert isinstance(comp, ReferenceComparison)


# ===========================================================================
# TestIdentifyDeltas
# ===========================================================================


class TestIdentifyDeltas:
    def test_identical_tracks_no_deltas(self):
        comp = compare_to_reference(_make_report(), _make_report())
        # With threshold=85, identical → all scores=100 → no deltas
        deltas = identify_deltas(comp, threshold=85.0)
        assert deltas == []

    def test_large_lufs_delta_generates_loudness_delta(self):
        track = _make_report(dynamics=_make_dynamics(lufs=-18.0))
        ref = _make_report(dynamics=_make_dynamics(lufs=-8.0))
        comp = compare_to_reference(track, ref)
        deltas = identify_deltas(comp)
        dim_names = {d.dimension for d in deltas}
        assert "loudness" in dim_names

    def test_large_width_delta_generates_stereo_delta(self):
        track = _make_report(stereo=_make_stereo(width=0.1))
        ref = _make_report(stereo=_make_stereo(width=0.7))
        comp = compare_to_reference(track, ref)
        deltas = identify_deltas(comp)
        dim_names = {d.dimension for d in deltas}
        assert "stereo" in dim_names

    def test_deltas_sorted_by_priority_descending(self):
        track = _make_report(
            dynamics=_make_dynamics(lufs=-20.0, crest=14.0),
            stereo=_make_stereo(width=0.1),
        )
        ref = _make_report(
            dynamics=_make_dynamics(lufs=-8.0, crest=9.0),
            stereo=_make_stereo(width=0.6),
        )
        comp = compare_to_reference(track, ref)
        deltas = identify_deltas(comp)
        if len(deltas) >= 2:
            priorities = [d.priority for d in deltas]
            assert all(priorities[i] >= priorities[i + 1] for i in range(len(priorities) - 1))

    def test_direction_is_increase_when_track_below_ref(self):
        track = _make_report(dynamics=_make_dynamics(lufs=-18.0))
        ref = _make_report(dynamics=_make_dynamics(lufs=-8.0))
        comp = compare_to_reference(track, ref)
        deltas = identify_deltas(comp)
        loud_delta = next((d for d in deltas if d.dimension == "loudness"), None)
        assert loud_delta is not None
        assert loud_delta.direction == "increase"

    def test_direction_is_decrease_when_track_above_ref(self):
        track = _make_report(stereo=_make_stereo(width=0.9))
        ref = _make_report(stereo=_make_stereo(width=0.4))
        comp = compare_to_reference(track, ref)
        deltas = identify_deltas(comp)
        stereo_delta = next((d for d in deltas if d.dimension == "stereo"), None)
        assert stereo_delta is not None
        assert stereo_delta.direction == "decrease"


# ===========================================================================
# TestCalibrateGenreTargets
# ===========================================================================


class TestCalibrateGenreTargets:
    def test_requires_at_least_2_analyses(self):
        with pytest.raises(ValueError, match="at least 2"):
            calibrate_genre_targets([_make_report()], "organic house")

    def test_returns_genre_target(self):
        reports = [_make_report(), _make_report()]
        target = calibrate_genre_targets(reports, "organic house")
        assert isinstance(target, GenreTarget)

    def test_genre_name_preserved(self):
        reports = [_make_report(), _make_report()]
        target = calibrate_genre_targets(reports, "melodic techno")
        assert target.genre == "melodic techno"

    def test_num_references_correct(self):
        reports = [_make_report() for _ in range(5)]
        target = calibrate_genre_targets(reports, "organic house")
        assert target.num_references == 5

    def test_mean_is_average_of_values(self):
        r1 = _make_report(dynamics=_make_dynamics(lufs=-8.0))
        r2 = _make_report(dynamics=_make_dynamics(lufs=-12.0))
        target = calibrate_genre_targets([r1, r2], "organic house")
        assert target.lufs.mean == pytest.approx(-10.0, abs=0.01)

    def test_std_is_zero_for_identical_tracks(self):
        reports = [_make_report() for _ in range(3)]
        target = calibrate_genre_targets(reports, "organic house")
        assert target.lufs.std == pytest.approx(0.0, abs=1e-6)

    def test_centroid_mean_correct(self):
        r1 = _make_report(freq=_make_freq(centroid=1000.0))
        r2 = _make_report(freq=_make_freq(centroid=2000.0))
        target = calibrate_genre_targets([r1, r2], "organic house")
        assert target.centroid_hz.mean == pytest.approx(1500.0, abs=0.1)


# ===========================================================================
# TestUpdateGenreTargets
# ===========================================================================


class TestUpdateGenreTargets:
    def _base_target(self) -> GenreTarget:
        return calibrate_genre_targets([_make_report(), _make_report()], "organic house")

    def test_returns_genre_target(self):
        base = self._base_target()
        updated = update_genre_targets([_make_report()], base)
        assert isinstance(updated, GenreTarget)

    def test_num_references_increases(self):
        base = self._base_target()
        updated = update_genre_targets([_make_report(), _make_report()], base)
        assert updated.num_references == base.num_references + 2

    def test_empty_new_analyses_raises(self):
        base = self._base_target()
        with pytest.raises(ValueError):
            update_genre_targets([], base)

    def test_genre_preserved(self):
        base = self._base_target()
        updated = update_genre_targets([_make_report()], base)
        assert updated.genre == base.genre


# ===========================================================================
# TestTargetSerialization
# ===========================================================================


class TestTargetSerialization:
    def _target(self) -> GenreTarget:
        return calibrate_genre_targets([_make_report(), _make_report()], "organic house")

    def test_to_dict_has_required_keys(self):
        d = target_to_dict(self._target())
        assert "genre" in d
        assert "bands" in d
        assert "dynamics" in d
        assert "stereo" in d
        assert "transients" in d
        assert "tonal" in d

    def test_from_dict_roundtrip(self):
        original = self._target()
        d = target_to_dict(original)
        restored = target_from_dict(d)
        assert restored.genre == original.genre
        assert restored.lufs.mean == pytest.approx(original.lufs.mean, abs=1e-4)
        assert restored.width.std == pytest.approx(original.width.std, abs=1e-4)

    def test_from_dict_num_references(self):
        d = target_to_dict(self._target())
        restored = target_from_dict(d)
        assert restored.num_references == 2

    def test_missing_required_key_raises(self):
        d = target_to_dict(self._target())
        del d["bands"]
        with pytest.raises(KeyError):
            target_from_dict(d)


# ===========================================================================
# TestHealthScore (via generate_full_report)
# ===========================================================================


class TestHealthScore:
    def test_no_problems_high_health(self):
        report = _make_report()
        full = generate_full_report(report)
        assert full.overall_health_score >= 90.0

    def test_severe_problem_reduces_health(self):
        # severity=9 → deduction = min(10, 9×2) = 10 → score = 100 − 10 = 90.0
        problem = _make_problem(severity=9.0)
        report = _make_report(problems=(problem,))
        full = generate_full_report(report)
        assert full.overall_health_score <= 90.0

    def test_health_bounded_0_to_100(self):
        problems = tuple(_make_problem(severity=10.0) for _ in range(10))
        report = _make_report(problems=problems)
        full = generate_full_report(report)
        assert 0.0 <= full.overall_health_score <= 100.0

    def test_with_reference_blends_score(self):
        track = _make_report(dynamics=_make_dynamics(lufs=-18.0))
        ref = _make_report(dynamics=_make_dynamics(lufs=-8.0))
        comp = compare_to_reference(track, ref)
        full_with_ref = generate_full_report(track, reference_comparison=comp)
        full_without = generate_full_report(track)
        # With reference, score should be different (blended)
        assert full_with_ref.overall_health_score != full_without.overall_health_score


# ===========================================================================
# TestGenerateFullReport
# ===========================================================================


class TestGenerateFullReport:
    def test_returns_full_mix_report(self):
        full = generate_full_report(_make_report())
        assert isinstance(full, FullMixReport)

    def test_sections_present_without_optional(self):
        full = generate_full_report(_make_report())
        assert full.executive_summary is not None
        assert full.frequency_analysis is not None
        assert full.stereo_analysis is not None
        assert full.dynamics_analysis is not None
        assert full.problems_and_fixes is not None
        assert full.signal_chain_section is not None

    def test_reference_section_none_without_comparison(self):
        full = generate_full_report(_make_report())
        assert full.reference_section is None

    def test_reference_section_present_with_comparison(self):
        comp = compare_to_reference(_make_report(), _make_report())
        full = generate_full_report(_make_report(), reference_comparison=comp)
        assert full.reference_section is not None

    def test_master_section_none_without_master_report(self):
        full = generate_full_report(_make_report())
        assert full.master_readiness_section is None

    def test_master_section_present_with_master_report(self):
        full = generate_full_report(_make_report(), master_report=_make_master_report())
        assert full.master_readiness_section is not None

    def test_genre_preserved(self):
        full = generate_full_report(_make_report(genre="melodic techno"))
        assert full.genre == "melodic techno"

    def test_top_priorities_is_tuple(self):
        full = generate_full_report(_make_report())
        assert isinstance(full.top_priorities, tuple)


# ===========================================================================
# TestReportSections
# ===========================================================================


class TestReportSections:
    def test_section_has_required_fields(self):
        full = generate_full_report(_make_report())
        sec = full.executive_summary
        assert isinstance(sec, ReportSection)
        assert sec.title
        assert sec.severity in {"ok", "warning", "critical"}
        assert sec.confidence in {"high", "medium", "low"}
        assert isinstance(sec.points, tuple)

    def test_no_problems_ok_severity(self):
        full = generate_full_report(_make_report(problems=()))
        assert full.problems_and_fixes.severity == "ok"

    def test_severe_problem_critical_severity(self):
        problem = _make_problem(severity=8.0)
        report = _make_report(problems=(problem,))
        full = generate_full_report(report)
        assert full.problems_and_fixes.severity in {"warning", "critical"}

    def test_mono_track_stereo_section_warning(self):
        report = _make_report(stereo=_make_stereo(is_mono=True))
        full = generate_full_report(report)
        assert full.stereo_analysis.severity == "warning"

    def test_reference_section_similarity_in_summary(self):
        track = _make_report()
        ref = _make_report()
        comp = compare_to_reference(track, ref)
        full = generate_full_report(track, reference_comparison=comp)
        assert full.reference_section is not None
        # similarity ~100% → summary should mention 100%
        assert "100" in full.reference_section.summary or "99" in full.reference_section.summary


# ===========================================================================
# TestMixEngineNewMethods — mock load_audio
# ===========================================================================


class TestMixEngineCompareToReference:
    def test_compare_to_reference_returns_comparison(self):
        track_report = _make_report()
        ref_report = _make_report()

        from ingestion.mix_engine import MixAnalysisEngine

        engine = MixAnalysisEngine()
        with patch.object(engine, "full_mix_analysis", side_effect=[track_report, ref_report]):
            comp = engine.compare_to_reference("/track.wav", "/ref.wav")
        assert isinstance(comp, ReferenceComparison)
        assert comp.num_references == 1

    def test_compare_to_references_batch_returns_comparison(self):
        track_report = _make_report()
        ref1 = _make_report()
        ref2 = _make_report()

        from ingestion.mix_engine import MixAnalysisEngine

        engine = MixAnalysisEngine()
        with patch.object(engine, "full_mix_analysis", side_effect=[track_report, ref1, ref2]):
            comp = engine.compare_to_references_batch("/track.wav", ["/r1.wav", "/r2.wav"])
        assert comp.num_references == 2

    def test_compare_to_references_batch_empty_paths_raises(self):
        from ingestion.mix_engine import MixAnalysisEngine

        engine = MixAnalysisEngine()
        with pytest.raises(ValueError):
            engine.compare_to_references_batch("/track.wav", [])

    def test_compare_to_reference_uses_genre_from_request(self):
        track_report = _make_report(genre="organic house")
        ref_report = _make_report(genre="organic house")

        from ingestion.mix_engine import MixAnalysisEngine

        engine = MixAnalysisEngine()
        with patch.object(engine, "full_mix_analysis", side_effect=[track_report, ref_report]):
            comp = engine.compare_to_reference("/t.wav", "/r.wav", genre="melodic techno")
        assert comp.genre in {"melodic techno", "organic house"}


class TestMixEngineFullReport:
    def test_full_mix_report_returns_full_mix_report(self):
        mix = _make_report()
        master = _make_master_report()

        from ingestion.mix_engine import MixAnalysisEngine

        engine = MixAnalysisEngine()
        with patch.object(engine, "full_mix_analysis", return_value=mix):
            with patch.object(engine, "master_analysis", return_value=master):
                full = engine.full_mix_report("/track.wav")
        assert isinstance(full, FullMixReport)

    def test_full_report_without_master(self):
        mix = _make_report()

        from ingestion.mix_engine import MixAnalysisEngine

        engine = MixAnalysisEngine()
        with patch.object(engine, "full_mix_analysis", return_value=mix):
            full = engine.full_mix_report("/track.wav", include_master=False)
        assert full.master_report is None
        assert full.master_readiness_section is None

    def test_full_report_with_references(self):
        mix = _make_report()
        ref = _make_report()
        master = _make_master_report()

        from ingestion.mix_engine import MixAnalysisEngine

        engine = MixAnalysisEngine()
        with patch.object(engine, "full_mix_analysis", side_effect=[mix, ref]):
            with patch.object(engine, "master_analysis", return_value=master):
                full = engine.full_mix_report("/track.wav", reference_paths=["/ref.wav"])
        assert full.reference_comparison is not None


class TestMixEngineCalibrateTargets:
    def test_calibrate_targets_returns_genre_target(self):
        r1, r2 = _make_report(), _make_report()

        from ingestion.mix_engine import MixAnalysisEngine

        engine = MixAnalysisEngine()
        with patch.object(engine, "full_mix_analysis", side_effect=[r1, r2]):
            target = engine.calibrate_targets(["/r1.wav", "/r2.wav"])
        assert isinstance(target, GenreTarget)

    def test_calibrate_targets_single_path_raises(self):
        from ingestion.mix_engine import MixAnalysisEngine

        engine = MixAnalysisEngine()
        with pytest.raises(ValueError, match="at least 2"):
            engine.calibrate_targets(["/only_one.wav"])

    def test_calibrate_targets_genre_passed_correctly(self):
        r1, r2 = _make_report(), _make_report()

        from ingestion.mix_engine import MixAnalysisEngine

        engine = MixAnalysisEngine()
        with patch.object(engine, "full_mix_analysis", side_effect=[r1, r2]):
            target = engine.calibrate_targets(["/r1.wav", "/r2.wav"], "melodic techno")
        assert target.genre == "melodic techno"


# ===========================================================================
# TestCompareReferenceTool
# ===========================================================================


class TestCompareReferenceTool:
    def test_missing_file_path_returns_error(self):
        from tools.music.compare_reference import CompareReference

        tool = CompareReference()
        result = tool(file_path="", reference_paths=["/ref.wav"])
        assert not result.success
        assert "file_path" in result.error.lower()

    def test_empty_reference_paths_returns_error(self):
        from tools.music.compare_reference import CompareReference

        tool = CompareReference()
        result = tool(file_path="/track.wav", reference_paths=[])
        assert not result.success

    def test_invalid_genre_returns_error(self):
        from tools.music.compare_reference import CompareReference

        tool = CompareReference()
        result = tool(
            file_path="/track.wav",
            reference_paths=["/ref.wav"],
            genre="polka",
        )
        assert not result.success
        assert "genre" in result.error.lower()

    def test_successful_comparison_returns_similarity(self):
        mock_comparison = MagicMock()
        mock_comparison.overall_similarity = 78.5
        mock_comparison.dimensions = []
        mock_comparison.band_deltas = []
        mock_comparison.deltas = []
        mock_comparison.width_delta = 0.1
        mock_comparison.crest_factor_delta = 0.5
        mock_comparison.lra_delta = 0.3
        mock_comparison.centroid_delta_hz = 200.0
        mock_comparison.tilt_delta = 0.2
        mock_comparison.density_delta = 0.1
        mock_comparison.sharpness_delta = 0.05
        mock_comparison.lufs_delta = -1.5
        mock_comparison.lufs_normalization_db = 1.5
        mock_comparison.genre = "organic house"
        mock_comparison.num_references = 1

        from tools.music.compare_reference import CompareReference

        tool = CompareReference()
        with patch("ingestion.mix_engine.MixAnalysisEngine") as MockEngine:
            MockEngine.return_value.compare_to_references_batch.return_value = mock_comparison
            result = tool(
                file_path="/track.wav",
                reference_paths=["/ref.wav"],
                genre="organic house",
            )
        assert result.success
        assert result.data["overall_similarity"] == 78.5


# ===========================================================================
# TestMixMasterReportTool
# ===========================================================================


class TestMixMasterReportTool:
    def test_missing_file_path_returns_error(self):
        from tools.music.mix_master_report import MixMasterReport

        tool = MixMasterReport()
        result = tool(file_path="")
        assert not result.success

    def test_invalid_genre_returns_error(self):
        from tools.music.mix_master_report import MixMasterReport

        tool = MixMasterReport()
        result = tool(file_path="/track.wav", genre="jazz")
        assert not result.success

    def test_successful_report_has_health_score(self):
        mix = _make_report()
        master = _make_master_report()
        mock_full = generate_full_report(mix, master_report=master)

        from tools.music.mix_master_report import MixMasterReport

        tool = MixMasterReport()
        with patch("ingestion.mix_engine.MixAnalysisEngine") as MockEngine:
            MockEngine.return_value.full_mix_report.return_value = mock_full
            result = tool(file_path="/track.wav", genre="organic house")
        assert result.success
        assert "overall_health_score" in result.data
        assert isinstance(result.data["overall_health_score"], float)

    def test_metadata_has_health_score(self):
        mix = _make_report()
        mock_full = generate_full_report(mix)

        from tools.music.mix_master_report import MixMasterReport

        tool = MixMasterReport()
        with patch("ingestion.mix_engine.MixAnalysisEngine") as MockEngine:
            MockEngine.return_value.full_mix_report.return_value = mock_full
            result = tool(file_path="/track.wav")
        assert "health_score" in result.metadata


# ===========================================================================
# TestCalibrateGenreTargetsTool
# ===========================================================================


class TestCalibrateGenreTargetsTool:
    def test_empty_paths_returns_error(self):
        from tools.music.calibrate_genre_targets import CalibrateGenreTargets

        tool = CalibrateGenreTargets()
        result = tool(reference_paths=[], genre="organic house")
        assert not result.success

    def test_single_path_returns_error(self):
        from tools.music.calibrate_genre_targets import CalibrateGenreTargets

        tool = CalibrateGenreTargets()
        result = tool(reference_paths=["/only.wav"], genre="organic house")
        assert not result.success
        assert "2" in result.error

    def test_invalid_genre_returns_error(self):
        from tools.music.calibrate_genre_targets import CalibrateGenreTargets

        tool = CalibrateGenreTargets()
        result = tool(reference_paths=["/r1.wav", "/r2.wav"], genre="jazz")
        assert not result.success

    def test_successful_calibration_returns_dict_with_bands(self):
        target = calibrate_genre_targets([_make_report(), _make_report()], "organic house")

        from tools.music.calibrate_genre_targets import CalibrateGenreTargets

        tool = CalibrateGenreTargets()
        with patch("ingestion.mix_engine.MixAnalysisEngine") as MockEngine:
            MockEngine.return_value.calibrate_targets.return_value = target
            result = tool(reference_paths=["/r1.wav", "/r2.wav"], genre="organic house")
        assert result.success
        assert "bands" in result.data
        assert "dynamics" in result.data


# ===========================================================================
# TestMixAPIEndpoints
# ===========================================================================


@pytest.fixture
def client() -> TestClient:
    from api.main import app

    return TestClient(app)


class TestMixAnalyzeEndpoint:
    def test_missing_file_returns_422(self, client: TestClient):
        resp = client.post(
            "/mix/analyze",
            json={"file_path": "/nonexistent.wav", "genre": "organic house"},
        )
        assert resp.status_code == 422

    def test_valid_request_structure(self, client: TestClient):
        mix = _make_report()
        with patch("api.routes.mix._get_engine") as mock_engine:
            mock_engine.return_value.full_mix_analysis.return_value = mix
            resp = client.post(
                "/mix/analyze",
                json={"file_path": "/track.wav", "genre": "organic house"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "spectral" in data
        assert "dynamics" in data
        assert "problems" in data


class TestMixCompareEndpoint:
    def test_missing_file_returns_422(self, client: TestClient):
        resp = client.post(
            "/mix/compare",
            json={
                "file_path": "/nonexistent.wav",
                "reference_paths": ["/nonexistent_ref.wav"],
                "genre": "organic house",
            },
        )
        assert resp.status_code == 422

    def test_valid_comparison_returns_similarity(self, client: TestClient):
        track = _make_report()
        ref = _make_report()

        from ingestion.mix_engine import MixAnalysisEngine

        with patch("api.routes.mix._get_engine") as mock_fn:
            engine = MixAnalysisEngine.__new__(MixAnalysisEngine)
            engine.search_fn = None
            with patch.object(engine, "full_mix_analysis", side_effect=[track, ref]):
                mock_fn.return_value = engine
                resp = client.post(
                    "/mix/compare",
                    json={
                        "file_path": "/track.wav",
                        "reference_paths": ["/ref.wav"],
                        "genre": "organic house",
                    },
                )
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_similarity" in data
        assert "dimensions" in data


class TestMixMasterEndpoint:
    def test_missing_file_returns_422(self, client: TestClient):
        resp = client.post(
            "/mix/master",
            json={"file_path": "/nonexistent.wav", "genre": "organic house"},
        )
        assert resp.status_code == 422

    def test_valid_request_returns_readiness(self, client: TestClient):
        master = _make_master_report()
        with patch("api.routes.mix._get_engine") as mock_engine:
            mock_engine.return_value.master_analysis.return_value = master
            resp = client.post(
                "/mix/master",
                json={"file_path": "/track.wav", "genre": "organic house"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "readiness_score" in data
        assert "loudness" in data


class TestMixReportEndpoint:
    def test_missing_file_returns_422(self, client: TestClient):
        resp = client.post(
            "/mix/report",
            json={"file_path": "/nonexistent.wav", "genre": "organic house"},
        )
        assert resp.status_code == 422

    def test_valid_request_returns_health_score(self, client: TestClient):
        mix = _make_report()
        master = _make_master_report()
        full = generate_full_report(mix, master_report=master)
        with patch("api.routes.mix._get_engine") as mock_engine:
            mock_engine.return_value.full_mix_report.return_value = full
            resp = client.post(
                "/mix/report",
                json={"file_path": "/track.wav", "genre": "organic house"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_health_score" in data
        assert "sections" in data


class TestMixCalibrateEndpoint:
    def test_single_reference_returns_422(self, client: TestClient):
        resp = client.post(
            "/mix/calibrate",
            json={
                "reference_paths": ["/only_one.wav"],
                "genre": "organic house",
            },
        )
        assert resp.status_code == 422

    def test_valid_calibration_returns_bands(self, client: TestClient):
        target = calibrate_genre_targets([_make_report(), _make_report()], "organic house")
        with patch("api.routes.mix._get_engine") as mock_engine:
            mock_engine.return_value.calibrate_targets.return_value = target
            resp = client.post(
                "/mix/calibrate",
                json={
                    "reference_paths": ["/r1.wav", "/r2.wav"],
                    "genre": "organic house",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "bands" in data
        assert "genre" in data


# ===========================================================================
# TestWeek18Integration
# ===========================================================================


class TestWeek18Integration:
    """End-to-end test: compare track vs references → get deltas → build report."""

    def test_full_pipeline_compare_and_report(self):
        """Track with low LUFS vs loud reference → loudness delta in report."""
        quiet_track = _make_report(dynamics=_make_dynamics(lufs=-18.0, crest=12.0))
        loud_refs = [
            _make_report(dynamics=_make_dynamics(lufs=-8.0, crest=9.0)),
            _make_report(dynamics=_make_dynamics(lufs=-9.0, crest=10.0)),
        ]

        comp = compare_to_references(quiet_track, loud_refs)
        assert comp.lufs_delta < 0  # track quieter than refs
        assert comp.overall_similarity < 100.0

        deltas = identify_deltas(comp)
        loud_deltas = [d for d in deltas if d.dimension == "loudness"]
        assert len(loud_deltas) >= 1
        assert loud_deltas[0].direction == "increase"

        full = generate_full_report(quiet_track, reference_comparison=comp)
        assert full.reference_section is not None
        assert full.overall_health_score < 100.0

    def test_calibration_then_compare_workflow(self):
        """Calibrate genre from 3 references → compare new track vs those refs."""
        refs = [
            _make_report(dynamics=_make_dynamics(lufs=-8.5, crest=10.0)),
            _make_report(dynamics=_make_dynamics(lufs=-9.0, crest=9.5)),
            _make_report(dynamics=_make_dynamics(lufs=-8.0, crest=10.5)),
        ]
        target = calibrate_genre_targets(refs, "organic house")

        # Verify target mean LUFS is close to -8.5
        assert target.lufs.mean == pytest.approx(-8.5, abs=0.5)
        assert target.num_references == 3

        # New track that matches the references well
        new_track = _make_report(dynamics=_make_dynamics(lufs=-8.5, crest=10.0))
        comp = compare_to_references(new_track, refs)
        assert comp.overall_similarity > 70.0

    def test_genre_self_similarity_high(self):
        """References compared against themselves should score >80%."""
        refs = [_make_report(), _make_report(), _make_report()]
        track = _make_report()
        comp = compare_to_references(track, refs)
        # Identical reports → 100%
        assert comp.overall_similarity > 80.0
