"""
tests/test_mix_analysis.py — Test suite for core/mix_analysis/.

Tests all 5 analysis modules using synthetic signals with known properties:
    - spectral.py: band energy, centroid, tilt, flatness
    - stereo.py:   width, correlation, mid-side ratio, per-band width
    - dynamics.py: RMS, peak, crest factor, LUFS, LRA
    - transients.py: onset density, sharpness
    - problems.py:  all 8 problem detectors + genre loader

Signal conventions:
    - Mono: shape (N,), dtype float64
    - Stereo: shape (2, N), dtype float64
    - Full-scale sine: amplitude = 1.0, RMS ≈ 0.707 (−3.01 dBFS)
    - DC signal: rms_db = 20*log10(amplitude) exactly
"""

from __future__ import annotations

import numpy as np
import pytest

from core.mix_analysis import (
    analyze_dynamics,
    analyze_frequency_balance,
    analyze_stereo_image,
    analyze_transients,
    available_genres,
    detect_mix_problems,
)
from core.mix_analysis._genre_loader import load_genre_target
from core.mix_analysis.types import (
    BandProfile,
    DynamicProfile,
    FrequencyProfile,
    MixAnalysis,
    MixProblem,
    StereoImage,
    TransientProfile,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SR = 44100  # standard sample rate for tests
DURATION = 2.0  # seconds
N = int(SR * DURATION)


def _sine(freq_hz: float, amplitude: float = 0.5, sr: int = SR, n: int = N) -> np.ndarray:
    """Generate a mono sine wave."""
    t = np.linspace(0, n / sr, n, endpoint=False)
    return (amplitude * np.sin(2.0 * np.pi * freq_hz * t)).astype(np.float64)


def _white_noise(amplitude: float = 0.3, n: int = N, seed: int = 42) -> np.ndarray:
    """Generate white noise with controlled amplitude."""
    rng = np.random.default_rng(seed)
    return (amplitude * rng.standard_normal(n)).astype(np.float64)


def _stereo(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Stack two mono arrays into a stereo (2, N) array."""
    return np.stack([left, right], axis=0)


def _impulse_train(density_hz: float, sr: int = SR, n: int = N) -> np.ndarray:
    """Generate a train of unit impulses at a given rate."""
    y = np.zeros(n, dtype=np.float64)
    step = max(1, int(sr / density_hz))
    y[::step] = 1.0
    return y


# ---------------------------------------------------------------------------
# 1. BandProfile / types
# ---------------------------------------------------------------------------


class TestBandProfile:
    def test_construction(self):
        bp = BandProfile(sub=1.0, low=2.0, low_mid=3.0, mid=4.0, high_mid=5.0, high=6.0, air=7.0)
        assert bp.sub == 1.0
        assert bp.air == 7.0

    def test_as_dict_keys(self):
        bp = BandProfile(sub=0, low=0, low_mid=0, mid=0, high_mid=0, high=0, air=0)
        keys = list(bp.as_dict().keys())
        assert keys == ["sub", "low", "low_mid", "mid", "high_mid", "high", "air"]

    def test_get_valid(self):
        bp = BandProfile(sub=1.5, low=0, low_mid=0, mid=0, high_mid=0, high=0, air=0)
        assert bp.get("sub") == pytest.approx(1.5)

    def test_get_invalid_raises(self):
        bp = BandProfile(sub=0, low=0, low_mid=0, mid=0, high_mid=0, high=0, air=0)
        with pytest.raises(ValueError, match="Unknown band"):
            bp.get("bass")

    def test_frozen(self):
        bp = BandProfile(sub=0, low=0, low_mid=0, mid=0, high_mid=0, high=0, air=0)
        with pytest.raises((AttributeError, TypeError)):
            bp.sub = 999  # type: ignore[misc]

    def test_hashable(self):
        bp = BandProfile(sub=0, low=0, low_mid=0, mid=0, high_mid=0, high=0, air=0)
        _ = {bp: "ok"}


class TestMixProblem:
    def test_frozen(self):
        p = MixProblem(
            category="muddiness",
            frequency_range=(200.0, 500.0),
            severity=7.5,
            description="test",
            recommendation="cut",
        )
        with pytest.raises((AttributeError, TypeError)):
            p.severity = 0.0  # type: ignore[misc]

    def test_frequency_range_tuple(self):
        p = MixProblem("x", (100.0, 300.0), 5.0, "d", "r")
        assert p.frequency_range == (100.0, 300.0)


# ---------------------------------------------------------------------------
# 2. spectral.py
# ---------------------------------------------------------------------------


class TestAnalyzeFrequencyBalance:
    def test_returns_frequency_profile(self):
        y = _white_noise()
        fp = analyze_frequency_balance(y, SR)
        assert isinstance(fp, FrequencyProfile)

    def test_white_noise_has_energy_in_all_bands(self):
        """White noise should have measurable energy in every band."""
        y = _white_noise(amplitude=0.4, n=SR * 5, seed=7)
        fp = analyze_frequency_balance(y, SR)
        # Each band should be > -40 dB relative
        for band in ["sub", "low", "low_mid", "mid", "high_mid", "high", "air"]:
            val = fp.bands.get(band)
            assert val > -40.0, f"Band {band} has unexpectedly low energy: {val:.1f} dB"

    def test_mid_sine_dominates_mid_band(self):
        """A 1 kHz sine should show highest relative energy in the mid band."""
        y = _sine(1000.0, amplitude=0.8)
        fp = analyze_frequency_balance(y, SR)
        assert fp.bands.mid > fp.bands.sub
        assert fp.bands.mid > fp.bands.air

    def test_low_sine_dominates_low_band(self):
        """A 100 Hz sine should have more energy in low band than high bands."""
        y = _sine(100.0, amplitude=0.8)
        fp = analyze_frequency_balance(y, SR)
        assert fp.bands.low > fp.bands.high_mid
        assert fp.bands.low > fp.bands.high

    def test_spectral_centroid_range(self):
        y = _white_noise()
        fp = analyze_frequency_balance(y, SR)
        assert 100.0 < fp.spectral_centroid < 20000.0

    def test_bright_mix_higher_centroid(self):
        """High-frequency sine → higher centroid than low-frequency sine."""
        y_high = _sine(8000.0, amplitude=0.5)
        y_low = _sine(100.0, amplitude=0.5)
        fp_high = analyze_frequency_balance(y_high, SR)
        fp_low = analyze_frequency_balance(y_low, SR)
        assert fp_high.spectral_centroid > fp_low.spectral_centroid

    def test_spectral_flatness_noise_higher_than_tone(self):
        """White noise is flatter than a pure sine tone."""
        y_noise = _white_noise(amplitude=0.3)
        y_tone = _sine(1000.0, amplitude=0.5)
        fp_noise = analyze_frequency_balance(y_noise, SR)
        fp_tone = analyze_frequency_balance(y_tone, SR)
        assert fp_noise.spectral_flatness > fp_tone.spectral_flatness

    def test_stereo_input_handled(self):
        """Stereo input should be mixed to mono without error."""
        y = _stereo(_white_noise(), _white_noise(seed=99))
        fp = analyze_frequency_balance(y, SR)
        assert isinstance(fp, FrequencyProfile)

    def test_overall_rms_db_range(self):
        """Overall RMS should be in a sane dBFS range for 0.3 amplitude noise."""
        y = _white_noise(amplitude=0.3)
        fp = analyze_frequency_balance(y, SR)
        # RMS should be roughly −10 dBFS ± 5 dB
        assert -20.0 < fp.overall_rms_db < -5.0

    def test_empty_array_raises(self):
        with pytest.raises(ValueError, match="empty"):
            analyze_frequency_balance(np.array([]), SR)

    def test_invalid_sr_raises(self):
        y = _white_noise()
        with pytest.raises(ValueError, match="Sample rate"):
            analyze_frequency_balance(y, 0)


# ---------------------------------------------------------------------------
# 3. stereo.py
# ---------------------------------------------------------------------------


class TestAnalyzeStereoImage:
    def test_mono_input_returns_is_mono_true(self):
        y = _white_noise()
        si = analyze_stereo_image(y, SR)
        assert si.is_mono is True
        assert si.width == pytest.approx(0.0)
        assert si.lr_correlation == pytest.approx(1.0)

    def test_mono_2d_input(self):
        """(1, N) shaped array should be treated as mono."""
        y = _white_noise().reshape(1, -1)
        si = analyze_stereo_image(y, SR)
        assert si.is_mono is True

    def test_identical_channels_mono_compatible(self):
        """L == R → correlation ≈ 1, width ≈ 0."""
        mono = _white_noise()
        y = _stereo(mono, mono)
        si = analyze_stereo_image(y, SR)
        assert si.is_mono is False
        assert si.lr_correlation == pytest.approx(1.0, abs=0.01)
        assert si.width == pytest.approx(0.0, abs=0.01)

    def test_inverted_channels_correlation_minus_one(self):
        """L == -R → correlation = -1 (phase inverted mono).
        Per the spec formula (width = 1 - |corr|), width = 0 because
        the two channels are perfectly (inversely) correlated.
        Phase cancellation is flagged separately by phase_issues detector."""
        mono = _white_noise()
        y = _stereo(mono, -mono)
        si = analyze_stereo_image(y, SR)
        assert si.lr_correlation == pytest.approx(-1.0, abs=0.05)
        # width = 1 - |-1| = 0 — correctly identifies as "correlated" (not decorrelated)
        assert si.width == pytest.approx(0.0, abs=0.05)

    def test_uncorrelated_stereo_moderate_width(self):
        """Independent L and R → moderate width."""
        y = _stereo(_white_noise(seed=1), _white_noise(seed=2))
        si = analyze_stereo_image(y, SR)
        assert 0.0 < si.width < 1.0
        assert -1.0 <= si.lr_correlation <= 1.0

    def test_mid_side_ratio_mono(self):
        """Mono-compatible mix (L==R) → very high mid-side ratio (all mid, no side)."""
        mono = _white_noise()
        y = _stereo(mono, mono)
        si = analyze_stereo_image(y, SR)
        assert si.mid_side_ratio > 20.0  # mid >> side in dB

    def test_band_widths_is_band_profile(self):
        y = _stereo(_white_noise(), _white_noise(seed=5))
        si = analyze_stereo_image(y, SR)
        assert isinstance(si.band_widths, BandProfile)

    def test_lows_narrow_highs_wider_in_typical_mix(self):
        """In a typical mix, highs should be wider than lows.
        Simulated: add correlated sub to independent stereo noise."""
        sub = _sine(60.0, amplitude=0.5)  # mono sub bass
        highs_l = _white_noise(amplitude=0.2, seed=10)
        highs_r = _white_noise(amplitude=0.2, seed=11)
        left = sub + highs_l
        right = sub + highs_r
        y = _stereo(left, right)
        si = analyze_stereo_image(y, SR)
        # Lows should be narrower than highs due to common sub component
        assert si.band_widths.sub < si.band_widths.high

    def test_empty_raises(self):
        y = np.zeros((2, 0))
        with pytest.raises(ValueError):
            analyze_stereo_image(y, SR)

    def test_too_many_channels_raises(self):
        y = np.zeros((4, N))
        with pytest.raises(ValueError, match="channels"):
            analyze_stereo_image(y, SR)

    def test_invalid_sr_raises(self):
        y = _white_noise()
        with pytest.raises(ValueError, match="Sample rate"):
            analyze_stereo_image(y, -1)


# ---------------------------------------------------------------------------
# 4. dynamics.py
# ---------------------------------------------------------------------------


class TestAnalyzeDynamics:
    def test_returns_dynamic_profile(self):
        y = _white_noise()
        dp = analyze_dynamics(y, SR)
        assert isinstance(dp, DynamicProfile)

    def test_dc_signal_rms_equals_amplitude_db(self):
        """DC signal: RMS = amplitude, so rms_db = 20*log10(amplitude)."""
        amplitude = 0.5
        y = np.full(SR, amplitude, dtype=np.float64)
        dp = analyze_dynamics(y, SR)
        expected_rms_db = 20.0 * np.log10(amplitude)
        assert dp.rms_db == pytest.approx(expected_rms_db, abs=0.1)

    def test_dc_signal_peak_equals_amplitude_db(self):
        amplitude = 0.5
        y = np.full(SR, amplitude, dtype=np.float64)
        dp = analyze_dynamics(y, SR)
        expected_peak_db = 20.0 * np.log10(amplitude)
        assert dp.peak_db == pytest.approx(expected_peak_db, abs=0.1)

    def test_dc_signal_crest_factor_near_zero(self):
        """DC signal has identical RMS and peak → crest factor ≈ 0 dB."""
        y = np.full(SR, 0.5, dtype=np.float64)
        dp = analyze_dynamics(y, SR)
        assert dp.crest_factor == pytest.approx(0.0, abs=0.5)

    def test_sine_crest_factor_near_3_db(self):
        """Sine wave: peak = A, rms = A/√2 → crest ≈ 3.01 dB."""
        y = _sine(440.0, amplitude=0.8, n=SR * 4)
        dp = analyze_dynamics(y, SR)
        assert dp.crest_factor == pytest.approx(3.01, abs=0.5)

    def test_impulse_train_high_crest(self):
        """Sparse impulse train has high crest factor (high peak, low RMS)."""
        y = _impulse_train(density_hz=2.0)  # 2 impulses per second
        dp = analyze_dynamics(y, SR)
        assert dp.crest_factor > 10.0

    def test_lufs_range(self):
        """LUFS should be a sensible negative value for noise at −10 dBFS amplitude."""
        y = _white_noise(amplitude=0.316)  # −10 dBFS approx
        dp = analyze_dynamics(y, SR)
        assert -40.0 < dp.lufs < 0.0

    def test_loud_signal_higher_lufs_than_quiet(self):
        y_loud = _white_noise(amplitude=0.5)
        y_quiet = _white_noise(amplitude=0.05)
        dp_loud = analyze_dynamics(y_loud, SR)
        dp_quiet = analyze_dynamics(y_quiet, SR)
        assert dp_loud.lufs > dp_quiet.lufs

    def test_stereo_input(self):
        y = _stereo(_white_noise(), _white_noise(seed=7))
        dp = analyze_dynamics(y, SR)
        assert dp.crest_factor >= 0.0

    def test_crest_factor_non_negative(self):
        y = _white_noise(amplitude=0.3)
        dp = analyze_dynamics(y, SR)
        assert dp.crest_factor >= 0.0

    def test_peak_gte_rms(self):
        """Peak dBFS should always be >= RMS dBFS."""
        y = _white_noise(amplitude=0.4)
        dp = analyze_dynamics(y, SR)
        assert dp.peak_db >= dp.rms_db

    def test_dynamic_range_non_negative(self):
        y = _white_noise()
        dp = analyze_dynamics(y, SR)
        assert dp.dynamic_range >= 0.0

    def test_loudness_range_non_negative(self):
        y = _white_noise(amplitude=0.3, n=SR * 10)
        dp = analyze_dynamics(y, SR)
        assert dp.loudness_range >= 0.0

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            analyze_dynamics(np.array([]), SR)

    def test_invalid_sr_raises(self):
        with pytest.raises(ValueError, match="Sample rate"):
            analyze_dynamics(_white_noise(), 0)


# ---------------------------------------------------------------------------
# 5. transients.py
# ---------------------------------------------------------------------------


class TestAnalyzeTransients:
    def test_returns_transient_profile(self):
        y = _white_noise()
        tp = analyze_transients(y, SR)
        assert isinstance(tp, TransientProfile)

    def test_impulse_train_high_density(self):
        """10 impulses/sec → density should be > 1.0 onset/sec."""
        y = _impulse_train(density_hz=10.0)
        tp = analyze_transients(y, SR)
        assert tp.density > 1.0

    def test_slow_impulse_train_lower_density(self):
        """1 impulse every 2 sec → density < impulse train at 10 Hz."""
        y_fast = _impulse_train(density_hz=10.0)
        y_slow = _impulse_train(density_hz=0.5)
        tp_fast = analyze_transients(y_fast, SR)
        tp_slow = analyze_transients(y_slow, SR)
        assert tp_fast.density > tp_slow.density

    def test_sharpness_range(self):
        y = _white_noise()
        tp = analyze_transients(y, SR)
        assert 0.0 <= tp.sharpness <= 1.0

    def test_attack_ratio_range(self):
        y = _white_noise()
        tp = analyze_transients(y, SR)
        assert 0.0 <= tp.attack_ratio <= 1.0

    def test_density_non_negative(self):
        y = _sine(440.0)
        tp = analyze_transients(y, SR)
        assert tp.density >= 0.0

    def test_stereo_input(self):
        y = _stereo(_white_noise(), _white_noise(seed=99))
        tp = analyze_transients(y, SR)
        assert tp.density >= 0.0

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            analyze_transients(np.array([]), SR)

    def test_invalid_sr_raises(self):
        with pytest.raises(ValueError, match="Sample rate"):
            analyze_transients(_white_noise(), 0)


# ---------------------------------------------------------------------------
# 6. _genre_loader.py
# ---------------------------------------------------------------------------


class TestGenreLoader:
    def test_load_organic_house(self):
        data = load_genre_target("organic house")
        assert "bands" in data
        assert "dynamics" in data
        assert "stereo" in data
        assert "thresholds" in data

    def test_case_insensitive(self):
        d1 = load_genre_target("Organic House")
        d2 = load_genre_target("organic house")
        assert d1 == d2

    def test_all_genres_load(self):
        for genre in available_genres():
            data = load_genre_target(genre)
            assert "bands" in data

    def test_unknown_genre_raises(self):
        with pytest.raises(ValueError, match="Unknown genre"):
            load_genre_target("disco house")

    def test_available_genres_returns_list(self):
        genres = available_genres()
        assert isinstance(genres, list)
        assert len(genres) >= 5
        assert "organic house" in genres
        assert "melodic techno" in genres

    def test_bands_have_seven_entries(self):
        data = load_genre_target("organic house")
        bands = data["bands"]
        expected = {"sub", "low", "low_mid", "mid", "high_mid", "high", "air"}
        assert set(bands.keys()) == expected

    def test_dynamics_have_required_keys(self):
        data = load_genre_target("deep house")
        dyn = data["dynamics"]
        for key in ("lufs_min", "lufs_max", "crest_min", "crest_max"):
            assert key in dyn, f"Missing key: {key}"

    def test_caching_returns_same_object(self):
        """Second call should return cached result (same dict object)."""
        d1 = load_genre_target("melodic techno")
        d2 = load_genre_target("melodic techno")
        assert d1 is d2


# ---------------------------------------------------------------------------
# 7. problems.py — detector helpers
# ---------------------------------------------------------------------------


def _make_freq_profile(
    low_mid_rel: float = -8.0,
    high_mid_rel: float = -12.0,
    sub_rel: float = -6.0,
    low_rel: float = -4.0,
) -> FrequencyProfile:
    """Build a FrequencyProfile with specified relative band levels."""
    return FrequencyProfile(
        bands=BandProfile(
            sub=sub_rel,
            low=low_rel,
            low_mid=low_mid_rel,
            mid=-10.0,
            high_mid=high_mid_rel,
            high=-16.0,
            air=-22.0,
        ),
        spectral_centroid=1200.0,
        spectral_tilt=-4.0,
        spectral_flatness=0.3,
        overall_rms_db=-14.0,
    )


def _make_stereo(width: float = 0.5, corr: float = 0.0) -> StereoImage:
    """Build a StereoImage with specified width and correlation."""
    bw_val = width * 0.8
    return StereoImage(
        width=width,
        lr_correlation=corr,
        mid_side_ratio=6.0,
        band_widths=BandProfile(
            sub=0.02,
            low=0.05,
            low_mid=0.10,
            mid=bw_val * 0.5,
            high_mid=bw_val * 0.8,
            high=bw_val,
            air=bw_val,
        ),
        is_mono=False,
    )


def _make_dynamics(
    rms_db: float = -14.0,
    peak_db: float = -0.5,
    lufs: float = -9.0,
    crest_factor: float = 10.0,
) -> DynamicProfile:
    return DynamicProfile(
        rms_db=rms_db,
        peak_db=peak_db,
        lufs=lufs,
        crest_factor=crest_factor,
        dynamic_range=8.0,
        loudness_range=4.0,
    )


class TestDetectMixProblems:
    def test_no_problems_clean_mix(self):
        """A mix at genre targets should produce no problems."""
        freq = _make_freq_profile(low_mid_rel=-8.0, high_mid_rel=-12.0)
        stereo = _make_stereo(width=0.5)
        dyn = _make_dynamics(crest_factor=10.0)
        problems = detect_mix_problems(freq, stereo, dyn, "organic house")
        assert problems == []

    def test_muddiness_detected(self):
        """low_mid 5 dB above organic house target (−8) should trigger muddiness."""
        freq = _make_freq_profile(low_mid_rel=-3.0)  # target is −8, so +5 dB excess
        stereo = _make_stereo(width=0.5)
        dyn = _make_dynamics(crest_factor=10.0)
        problems = detect_mix_problems(freq, stereo, dyn, "organic house")
        categories = [p.category for p in problems]
        assert "muddiness" in categories

    def test_muddiness_severity_positive(self):
        freq = _make_freq_profile(low_mid_rel=-3.0)
        problems = detect_mix_problems(freq, _make_stereo(), _make_dynamics(), "organic house")
        muddy = next(p for p in problems if p.category == "muddiness")
        assert muddy.severity > 0.0

    def test_harshness_detected(self):
        """high_mid 4 dB above organic house target (−12) → harshness."""
        freq = _make_freq_profile(high_mid_rel=-8.0)  # target −12, so +4 dB excess
        problems = detect_mix_problems(freq, _make_stereo(), _make_dynamics(), "organic house")
        categories = [p.category for p in problems]
        assert "harshness" in categories

    def test_boominess_detected(self):
        """Sub and low bands 6 dB above target + low crest → boominess."""
        freq = _make_freq_profile(sub_rel=0.0, low_rel=0.0)  # organic house targets: -6, -4
        dyn = _make_dynamics(crest_factor=5.0)  # below organic house min (8.0)
        problems = detect_mix_problems(freq, _make_stereo(), dyn, "organic house")
        categories = [p.category for p in problems]
        assert "boominess" in categories

    def test_thinness_detected(self):
        """low_mid 6 dB below organic house target (−8) → thinness."""
        freq = _make_freq_profile(low_mid_rel=-14.0)  # target −8, deficit = 6
        problems = detect_mix_problems(freq, _make_stereo(), _make_dynamics(), "organic house")
        categories = [p.category for p in problems]
        assert "thinness" in categories

    def test_narrow_stereo_detected(self):
        """Width 0.1 is below organic house minimum (0.3) → narrow_stereo."""
        freq = _make_freq_profile()
        stereo = _make_stereo(width=0.1)
        dyn = _make_dynamics()
        problems = detect_mix_problems(freq, stereo, dyn, "organic house")
        categories = [p.category for p in problems]
        assert "narrow_stereo" in categories

    def test_narrow_stereo_no_false_positive_wide_mix(self):
        """Width 0.6 should NOT trigger narrow_stereo for organic house."""
        freq = _make_freq_profile()
        stereo = _make_stereo(width=0.6)
        dyn = _make_dynamics()
        problems = detect_mix_problems(freq, stereo, dyn, "organic house")
        categories = [p.category for p in problems]
        assert "narrow_stereo" not in categories

    def test_phase_issues_detected(self):
        """Overall correlation −0.5 should trigger phase_issues."""
        freq = _make_freq_profile()
        # Correlation −0.5 → width = 1 − 0.5 = 0.5, but correlation is negative
        stereo = StereoImage(
            width=0.7,
            lr_correlation=-0.5,
            mid_side_ratio=-3.0,
            band_widths=BandProfile(
                sub=0.9,
                low=0.7,
                low_mid=0.5,
                mid=0.3,
                high_mid=0.4,
                high=0.5,
                air=0.5,
            ),
            is_mono=False,
        )
        dyn = _make_dynamics()
        problems = detect_mix_problems(freq, stereo, dyn, "organic house")
        categories = [p.category for p in problems]
        assert "phase_issues" in categories

    def test_over_compression_detected(self):
        """Crest factor 4.0 dB below organic house minimum (8.0) → over_compression."""
        freq = _make_freq_profile()
        stereo = _make_stereo(width=0.5)
        dyn = _make_dynamics(crest_factor=4.0)
        problems = detect_mix_problems(freq, stereo, dyn, "organic house")
        categories = [p.category for p in problems]
        assert "over_compression" in categories

    def test_over_compression_severity_above_zero(self):
        freq = _make_freq_profile()
        dyn = _make_dynamics(crest_factor=3.0)
        problems = detect_mix_problems(freq, _make_stereo(), dyn, "organic house")
        oc = next(p for p in problems if p.category == "over_compression")
        assert oc.severity > 0.0

    def test_mono_input_no_stereo_problems(self):
        """Passing stereo=None (mono mix) should not produce stereo-related problems."""
        freq = _make_freq_profile()
        dyn = _make_dynamics()
        problems = detect_mix_problems(freq, None, dyn, "organic house")
        categories = [p.category for p in problems]
        assert "narrow_stereo" not in categories
        assert "phase_issues" not in categories

    def test_problems_sorted_by_severity(self):
        """Returned list should be sorted severity descending."""
        freq = _make_freq_profile(low_mid_rel=-3.0, high_mid_rel=-8.0)
        dyn = _make_dynamics(crest_factor=4.0)
        problems = detect_mix_problems(freq, _make_stereo(), dyn, "organic house")
        if len(problems) > 1:
            severities = [p.severity for p in problems]
            assert severities == sorted(severities, reverse=True)

    def test_problems_have_recommendations(self):
        """Every detected problem must include a non-empty recommendation."""
        freq = _make_freq_profile(low_mid_rel=-3.0)
        dyn = _make_dynamics(crest_factor=4.0)
        problems = detect_mix_problems(freq, _make_stereo(), dyn, "organic house")
        for p in problems:
            assert len(p.recommendation) > 10

    def test_problems_have_frequency_range(self):
        freq = _make_freq_profile(low_mid_rel=-3.0)
        problems = detect_mix_problems(freq, _make_stereo(), _make_dynamics(), "organic house")
        for p in problems:
            lo, hi = p.frequency_range
            assert lo <= hi

    def test_all_genres_accepted(self):
        """detect_mix_problems should work for all 5 genres."""
        freq = _make_freq_profile()
        stereo = _make_stereo()
        dyn = _make_dynamics()
        for genre in available_genres():
            result = detect_mix_problems(freq, stereo, dyn, genre)
            assert isinstance(result, list)

    def test_unknown_genre_raises(self):
        freq = _make_freq_profile()
        dyn = _make_dynamics()
        with pytest.raises(ValueError, match="Unknown genre"):
            detect_mix_problems(freq, None, dyn, "drum and bass")

    def test_severity_clipped_to_0_10(self):
        """Severity must always be in [0, 10]."""
        # Extreme muddiness: +15 dB above target
        freq = _make_freq_profile(low_mid_rel=7.0)
        problems = detect_mix_problems(freq, _make_stereo(), _make_dynamics(), "organic house")
        for p in problems:
            assert 0.0 <= p.severity <= 10.0

    def test_melodic_techno_lower_crest_target(self):
        """Melodic techno has lower crest_min (6) than organic house (8).
        Crest factor 7.0 should not trigger over_compression for melodic techno."""
        freq = _make_freq_profile()
        dyn = _make_dynamics(crest_factor=7.0)
        problems_mt = detect_mix_problems(freq, _make_stereo(), dyn, "melodic techno")
        problems_oh = detect_mix_problems(freq, _make_stereo(), dyn, "organic house")
        mt_cats = [p.category for p in problems_mt]
        oh_cats = [p.category for p in problems_oh]
        # Melodic techno should NOT flag over_compression at crest=7
        assert "over_compression" not in mt_cats
        # Organic house SHOULD flag it (min=8)
        assert "over_compression" in oh_cats


# ---------------------------------------------------------------------------
# 8. Integration: full pipeline with real signals
# ---------------------------------------------------------------------------


class TestIntegrationPipeline:
    """End-to-end: generate audio → run all 4 analysis functions → detect problems."""

    def test_full_pipeline_white_noise(self):
        """Smoke test: all 4 analyses + problem detection on white noise stereo."""
        y_mono = _white_noise(amplitude=0.3, n=SR * 3)
        y_stereo = _stereo(y_mono, _white_noise(amplitude=0.3, n=SR * 3, seed=77))

        fp = analyze_frequency_balance(y_stereo, SR)
        si = analyze_stereo_image(y_stereo, SR)
        dp = analyze_dynamics(y_stereo, SR)
        tp = analyze_transients(y_stereo, SR)
        problems = detect_mix_problems(fp, si, dp, "organic house")

        assert isinstance(fp, FrequencyProfile)
        assert isinstance(si, StereoImage)
        assert isinstance(dp, DynamicProfile)
        assert isinstance(tp, TransientProfile)
        assert isinstance(problems, list)

    def test_all_profile_fields_populated(self):
        y = _white_noise(amplitude=0.3)
        fp = analyze_frequency_balance(y, SR)
        assert fp.spectral_centroid >= 0.0
        assert isinstance(fp.spectral_tilt, float)
        assert 0.0 <= fp.spectral_flatness <= 1.0

    def test_mix_analysis_dataclass_construction(self):
        """MixAnalysis can be assembled from component results."""
        y_mono = _white_noise(amplitude=0.3, n=SR * 2)
        y = _stereo(y_mono, _white_noise(amplitude=0.3, n=SR * 2, seed=42))

        fp = analyze_frequency_balance(y, SR)
        si = analyze_stereo_image(y, SR)
        dp = analyze_dynamics(y, SR)
        tp = analyze_transients(y, SR)
        problems = detect_mix_problems(fp, si, dp, "organic house")

        ma = MixAnalysis(
            frequency=fp,
            stereo=si,
            dynamics=dp,
            transients=tp,
            problems=tuple(problems),
            genre="organic house",
            duration_sec=2.0,
            sample_rate=SR,
        )
        assert ma.genre == "organic house"
        assert ma.sample_rate == SR
        assert isinstance(ma.problems, tuple)
