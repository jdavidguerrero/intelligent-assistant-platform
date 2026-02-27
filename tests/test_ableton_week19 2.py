"""tests/test_ableton_week19.py — Week 19: Ableton bidirectional bridge.

Tests cover:
  - core/ableton/types.py       — frozen dataclasses, LOMCommand serialisation
  - core/ableton/device_maps.py — value conversion helpers (Hz, dB, Q)
  - core/ableton/session.py     — find_track, find_device, find_parameter,
                                   get_eq_bands, get_compressor_params,
                                   session_summary
  - core/ableton/commands.py    — set_eq_band, set_compressor, set_utility,
                                   mute_track, solo_track, arm_track
  - ingestion/ableton_bridge.py — JSON deserialisation (_parse_*), cache,
                                   connection-error handling
  - tools/music/ableton_*.py    — all 4 MCP tools with mocked bridge
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.ableton.types import (
    Device,
    EQBand,
    FilterType,
    LOMCommand,
    Parameter,
    SessionState,
    Track,
    TrackType,
)

# ===========================================================================
# Factories
# ===========================================================================


def _make_parameter(
    name: str = "Freq",
    value: float = 0.5,
    min_value: float = 0.0,
    max_value: float = 1.0,
    lom_path: str = "live_set tracks 0 devices 0 parameters 0",
    index: int = 0,
    is_quantized: bool = False,
) -> Parameter:
    return Parameter(
        name=name,
        value=value,
        min_value=min_value,
        max_value=max_value,
        default_value=0.5,
        display_value="",
        lom_path=lom_path,
        index=index,
        is_quantized=is_quantized,
    )


def _make_eq8_device(band_freq_raw: float = 0.5, num_bands: int = 8) -> Device:
    """Create a synthetic EQ Eight device with ``num_bands`` bands."""
    params: list[Parameter] = [
        _make_parameter("Device On", 1.0, 0.0, 1.0, "live_set tracks 0 devices 0 parameters 0", 0),
        _make_parameter("Scale", 0.5, 0.0, 1.0, "live_set tracks 0 devices 0 parameters 1", 1),
    ]
    for band_n in range(1, num_bands + 1):
        base = 2 + (band_n - 1) * 5
        band_lom = "live_set tracks 0 devices 0 parameters {}"
        params += [
            _make_parameter(
                f"EqFrequency{band_n}", band_freq_raw, 0.0, 1.0, band_lom.format(base), base
            ),
            _make_parameter(f"EqGain{band_n}", 0.5, 0.0, 1.0, band_lom.format(base + 1), base + 1),
            _make_parameter(f"EqQ{band_n}", 0.5, 0.0, 1.0, band_lom.format(base + 2), base + 2),
            _make_parameter(
                f"FilterType{band_n}",
                3.0,
                0.0,
                7.0,
                band_lom.format(base + 3),
                base + 3,
                is_quantized=True,
            ),
            _make_parameter(
                f"ParameterIsActive{band_n}", 1.0, 0.0, 1.0, band_lom.format(base + 4), base + 4
            ),
        ]

    return Device(
        name="EQ Eight",
        class_name="Eq8",
        is_active=True,
        parameters=tuple(params),
        lom_path="live_set tracks 0 devices 0",
        index=0,
    )


def _make_compressor_device() -> Device:
    params = [
        _make_parameter("Device On", 1.0, 0.0, 1.0, "live_set tracks 0 devices 1 parameters 0", 0),
        _make_parameter("Threshold", 0.5, 0.0, 1.0, "live_set tracks 0 devices 1 parameters 1", 1),
        _make_parameter("Ratio", 0.3, 0.0, 1.0, "live_set tracks 0 devices 1 parameters 2", 2),
        _make_parameter("Attack", 0.2, 0.0, 1.0, "live_set tracks 0 devices 1 parameters 3", 3),
        _make_parameter("Release", 0.4, 0.0, 1.0, "live_set tracks 0 devices 1 parameters 4", 4),
        _make_parameter("Gain", 0.1, 0.0, 1.0, "live_set tracks 0 devices 1 parameters 5", 5),
        _make_parameter("Knee", 0.0, 0.0, 1.0, "live_set tracks 0 devices 1 parameters 6", 6),
        _make_parameter("Dry/Wet", 1.0, 0.0, 1.0, "live_set tracks 0 devices 1 parameters 7", 7),
    ]
    return Device(
        name="Compressor",
        class_name="Compressor2",
        is_active=True,
        parameters=tuple(params),
        lom_path="live_set tracks 0 devices 1",
        index=1,
    )


def _make_utility_device() -> Device:
    params = [
        _make_parameter("Device On", 1.0, 0.0, 1.0, "live_set tracks 0 devices 2 parameters 0", 0),
        _make_parameter("Gain", 0.5, 0.0, 1.0, "live_set tracks 0 devices 2 parameters 1", 1),
        _make_parameter(
            "Stereo Width", 0.25, 0.0, 1.0, "live_set tracks 0 devices 2 parameters 2", 2
        ),
        _make_parameter("Mono", 0.0, 0.0, 1.0, "live_set tracks 0 devices 2 parameters 3", 3),
    ]
    return Device(
        name="Utility",
        class_name="StereoGain",
        is_active=True,
        parameters=tuple(params),
        lom_path="live_set tracks 0 devices 2",
        index=2,
    )


def _make_track(
    name: str = "Pads",
    index: int = 0,
    track_type: TrackType = TrackType.AUDIO,
    devices: tuple = (),
) -> Track:
    return Track(
        name=name,
        index=index,
        type=track_type,
        arm=False,
        solo=False,
        mute=False,
        volume_db=0.0,
        pan=0.0,
        devices=devices if devices else (_make_eq8_device(),),
        clips=(),
        lom_path=f"live_set tracks {index}",
    )


def _make_session(tracks: tuple[Track, ...] | None = None) -> SessionState:
    if tracks is None:
        tracks = (
            _make_track("Pads", 0),
            _make_track("Bass", 1, TrackType.MIDI, (_make_eq8_device(), _make_compressor_device())),
            _make_track(
                "Kick", 2, TrackType.MIDI, (_make_compressor_device(), _make_utility_device())
            ),
        )
    return SessionState(
        tracks=tracks,
        return_tracks=(),
        master_track=None,
        tempo=128.0,
        time_sig_numerator=4,
        time_sig_denominator=4,
        is_playing=False,
        current_song_time=0.0,
        scene_count=8,
    )


# ===========================================================================
# core/ableton/types.py
# ===========================================================================


class TestLOMCommand:
    def test_to_dict_contains_required_keys(self):
        cmd = LOMCommand(
            type="set_parameter",
            lom_path="live_set tracks 0 devices 0 parameters 5",
            property="value",
            value=0.72,
        )
        d = cmd.to_dict()
        assert d["type"] == "set_parameter"
        assert d["lom_path"] == "live_set tracks 0 devices 0 parameters 5"
        assert d["property"] == "value"
        assert d["value"] == 0.72

    def test_to_dict_is_json_serializable(self):
        cmd = LOMCommand(type="set_parameter", lom_path="live_set", property="value", value=0.5)
        json.dumps(cmd.to_dict())  # should not raise

    def test_frozen_raises_on_mutation(self):
        cmd = LOMCommand(type="set_parameter", lom_path="live_set", property="value", value=0.5)
        with pytest.raises((AttributeError, TypeError)):
            cmd.value = 0.9  # type: ignore[misc]

    def test_description_optional(self):
        cmd = LOMCommand(type="set_parameter", lom_path="x", property="value", value=0.0)
        assert cmd.description == ""


class TestSessionState:
    def test_frozen(self):
        s = _make_session()
        with pytest.raises((AttributeError, TypeError)):
            s.tempo = 140.0  # type: ignore[misc]

    def test_track_count(self):
        s = _make_session()
        assert len(s.tracks) == 3


# ===========================================================================
# core/ableton/device_maps.py
# ===========================================================================


class TestEQ8Conversion:
    def test_eq8_band_indices_band1(self):
        from core.ableton.device_maps import eq8_band_indices

        idx = eq8_band_indices(1)
        assert idx["freq"] == 2
        assert idx["gain"] == 3
        assert idx["q"] == 4
        assert idx["filter_type"] == 5
        assert idx["active"] == 6

    def test_eq8_band_indices_band3(self):
        from core.ableton.device_maps import eq8_band_indices

        idx = eq8_band_indices(3)
        assert idx["freq"] == 12
        assert idx["gain"] == 13
        assert idx["q"] == 14
        assert idx["filter_type"] == 15
        assert idx["active"] == 16

    def test_eq8_band_indices_band8(self):
        from core.ableton.device_maps import eq8_band_indices

        idx = eq8_band_indices(8)
        assert idx["freq"] == 37
        assert idx["active"] == 41  # total 42 params = indices 0-41

    def test_eq8_freq_round_trip(self):
        from core.ableton.device_maps import eq8_freq_to_raw, eq8_raw_to_freq

        for freq in (20.0, 1000.0, 5000.0, 20000.0):
            raw = eq8_freq_to_raw(freq)
            assert 0.0 <= raw <= 1.0
            recovered = eq8_raw_to_freq(raw)
            assert abs(recovered - freq) < 0.1, f"freq={freq} → raw={raw} → {recovered}"

    def test_eq8_geometric_midpoint_is_half_raw(self):
        from core.ableton.device_maps import eq8_freq_to_raw

        # Geometric mean of 20–20000 Hz is sqrt(20 × 20000) ≈ 632 Hz → raw = 0.5
        # (NOT 1 kHz — that would be the arithmetic midpoint in log10 space only
        #  if min=1 Hz, but with min=20 Hz the midpoint shifts lower)
        raw_632 = eq8_freq_to_raw(632.5)
        assert abs(raw_632 - 0.5) < 0.02

    def test_eq8_gain_zero_db_is_half(self):
        from core.ableton.device_maps import eq8_gain_to_raw

        assert eq8_gain_to_raw(0.0) == pytest.approx(0.5)

    def test_eq8_gain_round_trip(self):
        from core.ableton.device_maps import eq8_gain_to_raw, eq8_raw_to_gain

        for gain in (-15.0, -6.0, 0.0, 6.0, 15.0):
            raw = eq8_gain_to_raw(gain)
            assert 0.0 <= raw <= 1.0
            assert abs(eq8_raw_to_gain(raw) - gain) < 0.01

    def test_eq8_q_round_trip(self):
        from core.ableton.device_maps import eq8_q_to_raw, eq8_raw_to_q

        for q in (0.1, 1.0, 2.0, 10.0):
            raw = eq8_q_to_raw(q)
            assert 0.0 <= raw <= 1.0
            assert abs(eq8_raw_to_q(raw) - q) < 0.01

    def test_eq8_freq_out_of_range_raises(self):
        from core.ableton.device_maps import eq8_freq_to_raw

        with pytest.raises(ValueError):
            eq8_freq_to_raw(10.0)  # below 20 Hz

        with pytest.raises(ValueError):
            eq8_freq_to_raw(25_000.0)  # above 20 kHz

    def test_eq8_gain_out_of_range_raises(self):
        from core.ableton.device_maps import eq8_gain_to_raw

        with pytest.raises(ValueError):
            eq8_gain_to_raw(20.0)  # above +15 dB

    def test_eq8_band_indices_invalid_raises(self):
        from core.ableton.device_maps import eq8_band_indices

        with pytest.raises(ValueError):
            eq8_band_indices(0)
        with pytest.raises(ValueError):
            eq8_band_indices(9)


class TestUtilityConversion:
    def test_utility_width_100pct_is_quarter_raw(self):
        from core.ableton.device_maps import utility_width_to_raw

        raw = utility_width_to_raw(100.0)
        assert raw == pytest.approx(0.25)  # 100 / 400 = 0.25

    def test_utility_width_round_trip(self):
        from core.ableton.device_maps import utility_raw_to_width, utility_width_to_raw

        for w in (0.0, 100.0, 200.0, 400.0):
            raw = utility_width_to_raw(w)
            assert abs(utility_raw_to_width(raw) - w) < 0.01


class TestCompressorConversion:
    def test_threshold_minus60_is_zero_raw(self):
        from core.ableton.device_maps import comp2_threshold_to_raw

        assert comp2_threshold_to_raw(-60.0) == pytest.approx(0.0)

    def test_threshold_zero_is_one_raw(self):
        from core.ableton.device_maps import comp2_threshold_to_raw

        assert comp2_threshold_to_raw(0.0) == pytest.approx(1.0)

    def test_threshold_out_of_range_raises(self):
        from core.ableton.device_maps import comp2_threshold_to_raw

        with pytest.raises(ValueError):
            comp2_threshold_to_raw(5.0)  # above 0 dB


# ===========================================================================
# core/ableton/session.py
# ===========================================================================


class TestFindTrack:
    def test_find_by_exact_name(self):
        from core.ableton.session import find_track

        s = _make_session()
        t = find_track(s, "Pads")
        assert t.name == "Pads"

    def test_find_by_partial_name_case_insensitive(self):
        from core.ableton.session import find_track

        s = _make_session()
        t = find_track(s, "bass")
        assert t.name == "Bass"

    def test_find_by_index(self):
        from core.ableton.session import find_track

        s = _make_session()
        t = find_track(s, 2)
        assert t.name == "Kick"

    def test_find_nonexistent_raises(self):
        from core.ableton.session import find_track

        s = _make_session()
        with pytest.raises(ValueError, match="No track matching"):
            find_track(s, "Nonexistent")

    def test_find_index_out_of_range_raises(self):
        from core.ableton.session import find_track

        s = _make_session()
        with pytest.raises(ValueError, match="out of range"):
            find_track(s, 99)


class TestFindDevice:
    def test_find_by_class_name(self):
        from core.ableton.session import find_device

        track = _make_track(
            "Bass", 1, TrackType.MIDI, (_make_eq8_device(), _make_compressor_device())
        )
        d = find_device(track, class_name="Compressor2")
        assert d.class_name == "Compressor2"

    def test_find_by_name_substring(self):
        from core.ableton.session import find_device

        track = _make_track(devices=(_make_eq8_device(),))
        d = find_device(track, name="eq eight")
        assert d.class_name == "Eq8"

    def test_no_criterion_raises(self):
        from core.ableton.session import find_device

        track = _make_track()
        with pytest.raises(ValueError, match="at least one of"):
            find_device(track)  # type: ignore[call-arg]

    def test_not_found_raises(self):
        from core.ableton.session import find_device

        track = _make_track()
        with pytest.raises(ValueError, match="No device matching"):
            find_device(track, class_name="NonexistentDevice")


class TestFindEQ:
    def test_find_eq8(self):
        from core.ableton.session import find_eq

        track = _make_track(devices=(_make_eq8_device(), _make_compressor_device()))
        eq = find_eq(track)
        assert eq.class_name == "Eq8"

    def test_no_eq_raises(self):
        from core.ableton.session import find_eq

        track = _make_track(devices=(_make_compressor_device(),))
        with pytest.raises(ValueError, match="No EQ device"):
            find_eq(track)


class TestFindCompressor:
    def test_find_compressor2(self):
        from core.ableton.session import find_compressor

        track = _make_track(devices=(_make_eq8_device(), _make_compressor_device()))
        comp = find_compressor(track)
        assert comp.class_name == "Compressor2"

    def test_no_compressor_raises(self):
        from core.ableton.session import find_compressor

        track = _make_track(devices=(_make_eq8_device(),))
        with pytest.raises(ValueError, match="No compressor"):
            find_compressor(track)


class TestFindParameter:
    def test_find_by_exact_name(self):
        from core.ableton.session import find_parameter

        device = _make_compressor_device()
        p = find_parameter(device, "Threshold")
        assert p.name == "Threshold"

    def test_find_by_substring(self):
        from core.ableton.session import find_parameter

        device = _make_compressor_device()
        p = find_parameter(device, "thresh")
        assert p.name == "Threshold"

    def test_not_found_raises(self):
        from core.ableton.session import find_parameter

        device = _make_compressor_device()
        with pytest.raises(ValueError, match="not found"):
            find_parameter(device, "NonexistentParam")


class TestGetEQBands:
    def test_returns_8_bands(self):
        from core.ableton.session import get_eq_bands

        eq = _make_eq8_device()
        bands = get_eq_bands(eq)
        assert len(bands) == 8

    def test_all_are_eq_band(self):
        from core.ableton.session import get_eq_bands

        bands = get_eq_bands(_make_eq8_device())
        for b in bands:
            assert isinstance(b, EQBand)

    def test_band_numbers_1_to_8(self):
        from core.ableton.session import get_eq_bands

        bands = get_eq_bands(_make_eq8_device())
        assert [b.band for b in bands] == list(range(1, 9))

    def test_raw_0_5_freq_is_geometric_midpoint(self):
        from core.ableton.session import get_eq_bands

        eq = _make_eq8_device(band_freq_raw=0.5)
        bands = get_eq_bands(eq)
        # raw=0.5 → geometric mean of 20–20000 Hz = sqrt(20 × 20000) ≈ 632 Hz
        for b in bands:
            assert 600 < b.freq_hz < 680, f"Expected ~632 Hz, got {b.freq_hz:.0f} Hz"

    def test_gain_0_5_raw_is_zero_db(self):
        from core.ableton.session import get_eq_bands

        bands = get_eq_bands(_make_eq8_device())
        for b in bands:
            assert abs(b.gain_db) < 0.01

    def test_filter_type_default_is_bell(self):
        from core.ableton.session import get_eq_bands

        bands = get_eq_bands(_make_eq8_device())
        for b in bands:
            assert b.filter_type == FilterType.BELL

    def test_non_eq8_raises(self):
        from core.ableton.session import get_eq_bands

        comp = _make_compressor_device()
        with pytest.raises(ValueError, match="EQ Eight"):
            get_eq_bands(comp)

    def test_too_few_parameters_raises(self):
        from core.ableton.session import get_eq_bands

        short_eq = Device(
            name="EQ Eight",
            class_name="Eq8",
            is_active=True,
            parameters=tuple(_make_parameter() for _ in range(10)),  # not 42
            lom_path="live_set tracks 0 devices 0",
        )
        with pytest.raises(ValueError, match="42 parameters"):
            get_eq_bands(short_eq)


class TestGetCompressorParams:
    def test_returns_compressor_settings(self):
        from core.ableton.session import CompressorSettings, get_compressor_params

        comp = _make_compressor_device()
        settings = get_compressor_params(comp)
        assert isinstance(settings, CompressorSettings)

    def test_non_compressor_raises(self):
        from core.ableton.session import get_compressor_params

        eq = _make_eq8_device()
        with pytest.raises(ValueError, match="compressor"):
            get_compressor_params(eq)


class TestSessionSummary:
    def test_has_required_keys(self):
        from core.ableton.session import session_summary

        summary = session_summary(_make_session())
        assert "tracks" in summary
        assert "tempo" in summary
        assert "is_playing" in summary
        assert "track_count" in summary

    def test_tempo_correct(self):
        from core.ableton.session import session_summary

        summary = session_summary(_make_session())
        assert summary["tempo"] == 128.0

    def test_track_count_correct(self):
        from core.ableton.session import session_summary

        summary = session_summary(_make_session())
        assert summary["track_count"] == 3

    def test_each_track_has_device_names(self):
        from core.ableton.session import session_summary

        summary = session_summary(_make_session())
        for t in summary["tracks"]:
            assert "device_names" in t
            assert isinstance(t["device_names"], list)


# ===========================================================================
# core/ableton/commands.py
# ===========================================================================


class TestSetParameter:
    def test_returns_set_parameter_command(self):
        from core.ableton.commands import set_parameter

        param = _make_parameter("Threshold", 0.5)
        cmd = set_parameter(param, 0.3)
        assert cmd.type == "set_parameter"
        assert cmd.value == 0.3

    def test_out_of_range_raises(self):
        from core.ableton.commands import set_parameter

        param = _make_parameter(value=0.5, min_value=0.0, max_value=1.0)
        with pytest.raises(ValueError):
            set_parameter(param, 1.5)


class TestSetEQBand:
    def test_returns_commands_list(self):
        from core.ableton.commands import set_eq_band

        track = _make_track()
        eq = _make_eq8_device()
        cmds = set_eq_band(track, eq, band=3, freq_hz=280.0, gain_db=-3.0, q=2.0)
        assert isinstance(cmds, list)
        assert len(cmds) == 3  # freq + gain + Q

    def test_lom_path_contains_correct_indices(self):
        from core.ableton.commands import set_eq_band

        track = _make_track()
        eq = _make_eq8_device()
        cmds = set_eq_band(track, eq, band=3, gain_db=-3.0)
        assert len(cmds) == 1
        # Band 3 gain is at index 13 (2 + (3-1)*5 + 1)
        assert "parameters 13" in cmds[0].lom_path

    def test_freq_cmd_lom_path_correct(self):
        from core.ableton.commands import set_eq_band

        track = _make_track()
        eq = _make_eq8_device()
        cmds = set_eq_band(track, eq, band=1, freq_hz=500.0)
        assert "parameters 2" in cmds[0].lom_path  # band 1 freq = index 2

    def test_filter_type_included_when_provided(self):
        from core.ableton.commands import set_eq_band

        track = _make_track()
        eq = _make_eq8_device()
        cmds = set_eq_band(track, eq, band=1, filter_type=4)  # notch
        assert len(cmds) == 1
        assert cmds[0].value == 4.0

    def test_enable_band_command(self):
        from core.ableton.commands import set_eq_band

        track = _make_track()
        eq = _make_eq8_device()
        cmds = set_eq_band(track, eq, band=2, enabled=False)
        assert len(cmds) == 1
        assert cmds[0].value == 0.0

    def test_invalid_band_raises(self):
        from core.ableton.commands import set_eq_band

        track = _make_track()
        eq = _make_eq8_device()
        with pytest.raises(ValueError):
            set_eq_band(track, eq, band=9, freq_hz=1000.0)

    def test_no_params_raises(self):
        from core.ableton.commands import set_eq_band

        track = _make_track()
        eq = _make_eq8_device()
        with pytest.raises(ValueError):
            set_eq_band(track, eq, band=1)  # no params provided

    def test_freq_value_within_0_1(self):
        from core.ableton.commands import set_eq_band

        track = _make_track()
        eq = _make_eq8_device()
        cmds = set_eq_band(track, eq, band=3, freq_hz=280.0)
        assert 0.0 <= cmds[0].value <= 1.0

    def test_gain_value_within_0_1(self):
        from core.ableton.commands import set_eq_band

        track = _make_track()
        eq = _make_eq8_device()
        cmds = set_eq_band(track, eq, band=3, gain_db=-3.0)
        assert 0.0 <= cmds[0].value <= 1.0

    def test_gain_minus3_db_less_than_half(self):
        from core.ableton.commands import set_eq_band

        track = _make_track()
        eq = _make_eq8_device()
        cmds = set_eq_band(track, eq, band=3, gain_db=-3.0)
        # -3 dB < 0 dB → raw < 0.5
        assert cmds[0].value < 0.5


class TestSetCompressor:
    def test_threshold_command(self):
        from core.ableton.commands import set_compressor

        track = _make_track(devices=(_make_compressor_device(),))
        comp = _make_compressor_device()
        cmds = set_compressor(track, comp, threshold_db=-20.0)
        assert len(cmds) == 1
        assert 0.0 <= cmds[0].value <= 1.0

    def test_no_params_raises(self):
        from core.ableton.commands import set_compressor

        track = _make_track()
        comp = _make_compressor_device()
        with pytest.raises(ValueError):
            set_compressor(track, comp)  # no params


class TestSetUtility:
    def test_width_command_value_in_range(self):
        from core.ableton.commands import set_utility

        track = _make_track()
        util = _make_utility_device()
        cmds = set_utility(track, util, width_pct=80.0)
        assert len(cmds) == 1
        assert 0.0 <= cmds[0].value <= 1.0

    def test_no_params_raises(self):
        from core.ableton.commands import set_utility

        track = _make_track()
        util = _make_utility_device()
        with pytest.raises(ValueError):
            set_utility(track, util)  # no params


class TestTrackCommands:
    def test_mute_track_command(self):
        from core.ableton.commands import mute_track

        track = _make_track()
        cmd = mute_track(track)
        assert cmd.type == "set_property"
        assert cmd.property == "mute"
        assert cmd.value == 1

    def test_unmute_track_command(self):
        from core.ableton.commands import unmute_track

        track = _make_track()
        cmd = unmute_track(track)
        assert cmd.value == 0

    def test_solo_track_command(self):
        from core.ableton.commands import solo_track

        track = _make_track()
        cmd = solo_track(track)
        assert cmd.property == "solo"
        assert cmd.value == 1

    def test_arm_track_command(self):
        from core.ableton.commands import arm_track

        track = _make_track()
        cmd = arm_track(track)
        assert cmd.property == "arm"
        assert cmd.value == 1


# ===========================================================================
# ingestion/ableton_bridge.py
# ===========================================================================


def _make_session_json() -> dict:
    """Minimal ALS Listener session payload."""
    return {
        "tracks": [
            {
                "name": "Pads",
                "index": 0,
                "type": "audio",
                "arm": False,
                "solo": False,
                "mute": False,
                "volume": 0.85,
                "pan": 0.5,
                "color": 0,
                "lom_path": "live_set tracks 0",
                "devices": [
                    {
                        "name": "EQ Eight",
                        "class_name": "Eq8",
                        "is_active": True,
                        "lom_path": "live_set tracks 0 devices 0",
                        "index": 0,
                        "parameters": [
                            {
                                "name": "Device On",
                                "value": 1.0,
                                "min": 0.0,
                                "max": 1.0,
                                "default": 1.0,
                                "display": "on",
                                "is_quantized": True,
                            }
                        ],
                    }
                ],
                "clips": [],
            }
        ],
        "return_tracks": [],
        "master_track": None,
        "tempo": 128.0,
        "time_sig_numerator": 4,
        "time_sig_denominator": 4,
        "is_playing": False,
        "current_song_time": 0.0,
        "scene_count": 8,
    }


class TestAbletonBridgeDeserialization:
    def test_parse_session_creates_session_state(self):
        from ingestion.ableton_bridge import _parse_session

        data = _make_session_json()
        session = _parse_session(data)
        assert isinstance(session, SessionState)
        assert session.tempo == 128.0
        assert len(session.tracks) == 1

    def test_parse_session_track_name(self):
        from ingestion.ableton_bridge import _parse_session

        session = _parse_session(_make_session_json())
        assert session.tracks[0].name == "Pads"

    def test_parse_session_volume_0_85_is_zero_db(self):
        from ingestion.ableton_bridge import _parse_session

        session = _parse_session(_make_session_json())
        # raw 0.85 ≈ 0 dB by our formula
        assert abs(session.tracks[0].volume_db) < 1.0

    def test_parse_session_pan_0_5_is_center(self):
        from ingestion.ableton_bridge import _parse_session

        session = _parse_session(_make_session_json())
        assert session.tracks[0].pan == pytest.approx(0.0, abs=0.01)

    def test_parse_parameter_creates_parameter(self):
        from ingestion.ableton_bridge import _parse_parameter

        data = {
            "name": "Freq",
            "value": 0.5,
            "min": 0.0,
            "max": 1.0,
            "default": 0.5,
            "display": "1kHz",
        }
        p = _parse_parameter(data, 0, 0, 3)
        assert p.name == "Freq"
        assert p.value == 0.5
        assert "parameters 3" in p.lom_path

    def test_parse_device_creates_device(self):
        from ingestion.ableton_bridge import _parse_device

        data = {"name": "EQ Eight", "class_name": "Eq8", "is_active": True, "parameters": []}
        d = _parse_device(data, 0, 1)
        assert d.name == "EQ Eight"
        assert d.class_name == "Eq8"
        assert d.index == 1

    def test_parse_clip_creates_clip(self):
        from ingestion.ableton_bridge import _parse_clip

        data = {
            "name": "Clip 1",
            "length": 4.0,
            "is_playing": False,
            "is_triggered": False,
            "is_midi": True,
        }
        c = _parse_clip(data, 0, 2)
        assert c.name == "Clip 1"
        assert c.is_midi is True
        assert "clip_slots 2" in c.lom_path


class TestAbletonBridgeConnectionError:
    def test_get_session_no_ableton_raises_connection_error(self):
        from ingestion.ableton_bridge import AbletonBridge

        bridge = AbletonBridge(host="localhost", port=19999)  # no server
        try:
            import websocket  # noqa: F401

            with pytest.raises(ConnectionError):
                bridge.get_session()
        except ImportError:
            pytest.skip("websocket-client not installed")

    def test_ping_no_ableton_raises_connection_error(self):
        from ingestion.ableton_bridge import AbletonBridge

        bridge = AbletonBridge(host="localhost", port=19999)
        try:
            import websocket  # noqa: F401

            with pytest.raises(ConnectionError):
                bridge.ping()
        except ImportError:
            pytest.skip("websocket-client not installed")


class TestAbletonBridgeCache:
    def test_cache_used_on_second_call(self):
        from ingestion.ableton_bridge import AbletonBridge

        bridge = AbletonBridge()
        session = _make_session()
        bridge._session_cache = session
        bridge._cache_time = 999_999_999.0  # far future → cache is valid

        # Second call should not try to connect (cache is valid)
        result = bridge.get_session()
        assert result is session

    def test_invalidate_clears_cache(self):
        from ingestion.ableton_bridge import AbletonBridge

        bridge = AbletonBridge()
        bridge._session_cache = _make_session()
        bridge._cache_time = 999_999_999.0
        bridge.invalidate()
        assert bridge._session_cache is None


# ===========================================================================
# tools/music/ableton_read_session.py
# ===========================================================================


def _mock_bridge_with_session(session: SessionState) -> MagicMock:
    mock_bridge = MagicMock()
    mock_bridge.get_session.return_value = session
    return mock_bridge


class TestAbletonReadSessionTool:
    def test_success_returns_summary(self):
        from tools.music.ableton_read_session import AbletonReadSession

        tool = AbletonReadSession()
        session = _make_session()
        with patch("ingestion.ableton_bridge.AbletonBridge") as MockBridge:
            MockBridge.return_value = _mock_bridge_with_session(session)
            result = tool()
        assert result.success
        assert "tracks" in result.data
        assert "tempo" in result.data

    def test_connection_error_returns_failure(self):
        from tools.music.ableton_read_session import AbletonReadSession

        tool = AbletonReadSession()
        with patch("ingestion.ableton_bridge.AbletonBridge") as MockBridge:
            MockBridge.return_value.get_session.side_effect = ConnectionError("Ableton not running")
            result = tool()
        assert not result.success
        assert "Ableton" in result.error or "not running" in result.error

    def test_track_filter_applied(self):
        from tools.music.ableton_read_session import AbletonReadSession

        tool = AbletonReadSession()
        session = _make_session()
        with patch("ingestion.ableton_bridge.AbletonBridge") as MockBridge:
            MockBridge.return_value = _mock_bridge_with_session(session)
            result = tool(track_filter="Pads")
        assert result.success
        assert all("pads" in t["name"].lower() for t in result.data["tracks"])

    def test_metadata_contains_ws_port(self):
        from tools.music.ableton_read_session import AbletonReadSession

        tool = AbletonReadSession()
        session = _make_session()
        with patch("ingestion.ableton_bridge.AbletonBridge") as MockBridge:
            MockBridge.return_value = _mock_bridge_with_session(session)
            result = tool()
        assert result.metadata["ws_port"] == 11005


# ===========================================================================
# tools/music/ableton_set_parameter.py
# ===========================================================================


class TestAbletonSetParameterTool:
    def test_missing_track_name_returns_error(self):
        from tools.music.ableton_set_parameter import AbletonSetParameter

        result = AbletonSetParameter()(
            track_name="", device_name="EQ8", parameter_name="Freq", value=0.5
        )
        assert not result.success

    def test_success_path(self):
        from tools.music.ableton_set_parameter import AbletonSetParameter

        session = _make_session()
        with patch("ingestion.ableton_bridge.AbletonBridge") as MockBridge:
            bridge = _mock_bridge_with_session(session)
            bridge.send_command.return_value = {"type": "ack"}
            MockBridge.return_value = bridge
            result = AbletonSetParameter()(
                track_name="Pads",
                device_name="EQ Eight",
                parameter_name="Device On",
                value=1.0,
            )
        assert result.success

    def test_track_not_found_returns_error(self):
        from tools.music.ableton_set_parameter import AbletonSetParameter

        session = _make_session()
        with patch("ingestion.ableton_bridge.AbletonBridge") as MockBridge:
            MockBridge.return_value = _mock_bridge_with_session(session)
            result = AbletonSetParameter()(
                track_name="NonExistentTrack",
                device_name="EQ Eight",
                parameter_name="Device On",
                value=1.0,
            )
        assert not result.success


# ===========================================================================
# tools/music/ableton_apply_eq.py
# ===========================================================================


class TestAbletonApplyEQTool:
    def test_missing_track_returns_error(self):
        from tools.music.ableton_apply_eq import AbletonApplyEQ

        result = AbletonApplyEQ()(track_name="", band=3, freq_hz=280.0, gain_db=-3.0)
        assert not result.success

    def test_invalid_band_returns_error(self):
        from tools.music.ableton_apply_eq import AbletonApplyEQ

        result = AbletonApplyEQ()(track_name="Pads", band=9, freq_hz=280.0, gain_db=-3.0)
        assert not result.success
        assert "band" in result.error.lower()

    def test_invalid_freq_returns_error(self):
        from tools.music.ableton_apply_eq import AbletonApplyEQ

        result = AbletonApplyEQ()(track_name="Pads", band=3, freq_hz=5.0, gain_db=-3.0)
        assert not result.success

    def test_invalid_gain_returns_error(self):
        from tools.music.ableton_apply_eq import AbletonApplyEQ

        result = AbletonApplyEQ()(track_name="Pads", band=3, freq_hz=1000.0, gain_db=20.0)
        assert not result.success

    def test_success_path(self):
        from tools.music.ableton_apply_eq import AbletonApplyEQ

        session = _make_session()
        with patch("ingestion.ableton_bridge.AbletonBridge") as MockBridge:
            bridge = _mock_bridge_with_session(session)
            bridge.send_commands.return_value = [{"type": "ack"}, {"type": "ack"}, {"type": "ack"}]
            MockBridge.return_value = bridge
            result = AbletonApplyEQ()(
                track_name="Pads",
                band=3,
                freq_hz=280.0,
                gain_db=-3.0,
                q=2.0,
            )
        assert result.success
        assert result.data["freq_hz"] == 280.0
        assert result.data["gain_db"] == -3.0

    def test_filter_type_bell_accepted(self):
        from tools.music.ableton_apply_eq import AbletonApplyEQ

        session = _make_session()
        with patch("ingestion.ableton_bridge.AbletonBridge") as MockBridge:
            bridge = _mock_bridge_with_session(session)
            bridge.send_commands.return_value = [{"type": "ack"}] * 4
            MockBridge.return_value = bridge
            result = AbletonApplyEQ()(
                track_name="Pads",
                band=3,
                freq_hz=280.0,
                gain_db=-3.0,
                filter_type="bell",
            )
        assert result.success

    def test_unknown_filter_type_returns_error(self):
        from tools.music.ableton_apply_eq import AbletonApplyEQ

        result = AbletonApplyEQ()(
            track_name="Pads", band=3, freq_hz=280.0, gain_db=-3.0, filter_type="superfilter"
        )
        assert not result.success

    def test_connection_error_returns_failure(self):
        from tools.music.ableton_apply_eq import AbletonApplyEQ

        with patch("ingestion.ableton_bridge.AbletonBridge") as MockBridge:
            MockBridge.return_value.get_session.side_effect = ConnectionError("not running")
            result = AbletonApplyEQ()(track_name="Pads", band=3, freq_hz=280.0, gain_db=-3.0)
        assert not result.success


# ===========================================================================
# tools/music/ableton_apply_mix_fix.py
# ===========================================================================


class TestAbletonApplyMixFixTool:
    def test_missing_track_returns_error(self):
        from tools.music.ableton_apply_mix_fix import AbletonApplyMixFix

        result = AbletonApplyMixFix()(
            track_name="", category="eq", recommendation="Cut 3 dB at 280 Hz"
        )
        assert not result.success

    def test_missing_category_returns_error(self):
        from tools.music.ableton_apply_mix_fix import AbletonApplyMixFix

        result = AbletonApplyMixFix()(
            track_name="Pads", category="", recommendation="Cut 3 dB at 280 Hz"
        )
        assert not result.success

    def test_unknown_category_returns_error(self):
        from tools.music.ableton_apply_mix_fix import AbletonApplyMixFix

        result = AbletonApplyMixFix()(
            track_name="Pads", category="unknowncategory", recommendation="fix it"
        )
        assert not result.success

    def test_dry_run_eq_fix_returns_planned_action(self):
        from tools.music.ableton_apply_mix_fix import AbletonApplyMixFix

        result = AbletonApplyMixFix()(
            track_name="Pads",
            category="muddiness",
            recommendation="Cut 3 dB at 280 Hz",
            dry_run=True,
        )
        assert result.success
        assert result.data["dry_run"] is True
        assert result.data["planned_action"] == "apply_eq"
        assert result.data["freq_hz"] == pytest.approx(280.0)

    def test_dry_run_stereo_fix_extracts_width(self):
        from tools.music.ableton_apply_mix_fix import AbletonApplyMixFix

        result = AbletonApplyMixFix()(
            track_name="Pads",
            category="stereo",
            recommendation="Reduce width to 70%",
            dry_run=True,
        )
        assert result.success
        assert result.data["width_pct"] == pytest.approx(70.0)

    def test_dry_run_level_fix_extracts_gain(self):
        from tools.music.ableton_apply_mix_fix import AbletonApplyMixFix

        result = AbletonApplyMixFix()(
            track_name="Pads",
            category="level",
            recommendation="Reduce gain by -4 dB",
            dry_run=True,
        )
        assert result.success
        assert result.data["gain_db"] == pytest.approx(-4.0)

    def test_freq_extracted_from_recommendation(self):
        from tools.music.ableton_apply_mix_fix import AbletonApplyMixFix

        result = AbletonApplyMixFix()(
            track_name="Pads",
            category="eq",
            recommendation="Boost 2 kHz by +3 dB",
            dry_run=True,
        )
        assert result.success
        assert result.data["freq_hz"] == pytest.approx(2000.0)

    def test_gain_extracted_from_recommendation(self):
        from tools.music.ableton_apply_mix_fix import AbletonApplyMixFix

        result = AbletonApplyMixFix()(
            track_name="Pads",
            category="harshness",
            recommendation="Reduce harshness: cut -2.5 dB at 4 kHz",
            dry_run=True,
        )
        assert result.success
        assert result.data["gain_db"] == pytest.approx(-2.5)


# ===========================================================================
# Integration: full pipeline  (Week 16 analysis → Week 19 apply)
# ===========================================================================


class TestWeek19Integration:
    def test_eq_fix_commands_target_correct_band(self):
        """set_eq_band on band 3 at 280 Hz writes correct parameter indices."""
        from core.ableton.commands import set_eq_band
        from core.ableton.device_maps import eq8_band_indices, eq8_freq_to_raw, eq8_gain_to_raw

        track = _make_track()
        eq = _make_eq8_device()
        cmds = set_eq_band(track, eq, band=3, freq_hz=280.0, gain_db=-3.0, q=2.0)

        idx = eq8_band_indices(3)
        freq_cmd = next(c for c in cmds if "parameters " + str(idx["freq"]) in c.lom_path)
        gain_cmd = next(c for c in cmds if "parameters " + str(idx["gain"]) in c.lom_path)

        assert abs(freq_cmd.value - eq8_freq_to_raw(280.0)) < 0.001
        assert abs(gain_cmd.value - eq8_gain_to_raw(-3.0)) < 0.001

    def test_session_roundtrip_preserves_track_count(self):
        """ALS Listener JSON → _parse_session → find_track → find_eq."""
        from core.ableton.session import find_eq, find_track
        from ingestion.ableton_bridge import _parse_session

        data = _make_session_json()
        session = _parse_session(data)
        track = find_track(session, "Pads")
        assert track.name == "Pads"
        # EQ Eight has only 1 parameter in our test JSON — find_eq still works by class_name
        eq = find_eq(track)
        assert eq.class_name == "Eq8"

    def test_lom_command_json_matches_protocol(self):
        """Commands serialise exactly as the ALS Listener expects."""
        from core.ableton.commands import set_eq_band

        track = _make_track()
        eq = _make_eq8_device()
        cmds = set_eq_band(track, eq, band=3, freq_hz=280.0, gain_db=-3.0)

        for cmd in cmds:
            d = cmd.to_dict()
            assert d["type"] in ("set_parameter", "set_property")
            assert isinstance(d["lom_path"], str)
            assert isinstance(d["value"], int | float)
            assert isinstance(d["property"], str)
            # Must be JSON serializable
            json.dumps(d)
