"""tests/test_session_intelligence_day1.py — Day 1: Session Intelligence 3-Layer Audit System.

Tests cover:
  - core/ableton/device_maps.py   — 4 new reverse converter functions
  - core/session_intelligence/types.py   — frozen dataclasses, validators
  - core/session_intelligence/mapper.py  — SessionState → SessionMap conversion
  - core/session_intelligence/universal_audit.py — 8 universal checks
"""

from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import pytest

from core.ableton.device_maps import (
    comp2_attack_to_raw,
    comp2_raw_to_attack_ms,
    comp2_raw_to_ratio,
    comp2_raw_to_release_ms,
    comp2_raw_to_threshold_db,
    comp2_release_to_raw,
    comp2_threshold_to_raw,
)
from core.ableton.types import (
    Device,
    Parameter,
    SessionState,
    Track,
    TrackType,
)
from core.session_intelligence.mapper import (
    _classify_device_type,
    _infer_bus_type,
    map_session_to_map,
)
from core.session_intelligence.types import (
    AuditFinding,
    BusInfo,
    ChannelInfo,
    DeviceInfo,
    SessionMap,
)
from core.session_intelligence.universal_audit import (
    check_bypassed_plugin,
    check_duplicate_device_type,
    check_extreme_compression,
    check_mono_on_stereo,
    check_muted_with_cpu,
    check_no_eq,
    check_no_highpass,
    check_untouched_fader,
    run_universal_audit,
)

# ===========================================================================
# Test factories
# ===========================================================================


def _build_parameter(
    name: str = "Freq",
    value: float = 0.5,
    display_value: str = "",
    lom_path: str = "live_set tracks 0 devices 0 parameters 0",
    index: int = 0,
    is_quantized: bool = False,
) -> Parameter:
    return Parameter(
        name=name,
        value=value,
        min_value=0.0,
        max_value=1.0,
        default_value=0.5,
        display_value=display_value,
        lom_path=lom_path,
        index=index,
        is_quantized=is_quantized,
    )


def _build_device(
    name: str = "EQ Eight",
    class_name: str = "Eq8",
    is_active: bool = True,
    params: tuple[Parameter, ...] = (),
    lom_path: str = "live_set tracks 0 devices 0",
    index: int = 0,
) -> Device:
    return Device(
        name=name,
        class_name=class_name,
        is_active=is_active,
        parameters=params,
        lom_path=lom_path,
        index=index,
    )


def _build_track(
    name: str = "Synth",
    index: int = 0,
    track_type: TrackType = TrackType.MIDI,
    devices: tuple[Device, ...] = (),
    volume_db: float = -6.0,
    pan: float = 0.0,
    mute: bool = False,
    solo: bool = False,
    lom_path: str = "live_set tracks 0",
) -> Track:
    return Track(
        name=name,
        index=index,
        type=track_type,
        arm=False,
        solo=solo,
        mute=mute,
        volume_db=volume_db,
        pan=pan,
        devices=devices,
        clips=(),
        lom_path=lom_path,
    )


def _build_device_info(
    name: str = "EQ Eight",
    class_name: str = "Eq8",
    is_active: bool = True,
    device_type: str = "eq",
    params: tuple[tuple[str, str, float], ...] = (),
    lom_path: str = "live_set tracks 0 devices 0",
) -> DeviceInfo:
    return DeviceInfo(
        name=name,
        class_name=class_name,
        is_active=is_active,
        device_type=device_type,
        params=params,
        lom_path=lom_path,
    )


def _build_channel(
    name: str = "Synth",
    index: int = 0,
    track_type: TrackType = TrackType.MIDI,
    devices: tuple[DeviceInfo, ...] = (),
    volume_db: float = -6.0,
    pan: float = 0.0,
    is_muted: bool = False,
    is_solo: bool = False,
    parent_bus: str | None = None,
    lom_path: str = "live_set tracks 0",
) -> ChannelInfo:
    return ChannelInfo(
        name=name,
        index=index,
        track_type=track_type,
        parent_bus=parent_bus,
        is_orphan=parent_bus is None and track_type not in (TrackType.RETURN, TrackType.MASTER),
        volume_db=volume_db,
        pan=pan,
        is_muted=is_muted,
        is_solo=is_solo,
        devices=devices,
        lom_path=lom_path,
    )


def _build_session_map(
    buses: tuple[BusInfo, ...] = (),
    orphan_channels: tuple[ChannelInfo, ...] = (),
    return_channels: tuple[ChannelInfo, ...] = (),
    master_channel: ChannelInfo | None = None,
) -> SessionMap:
    """Build a minimal SessionMap for testing."""
    all_ch: list[ChannelInfo] = list(orphan_channels)
    for bus in buses:
        all_ch.extend(bus.channels)
    all_ch.extend(return_channels)
    return SessionMap(
        buses=buses,
        orphan_channels=orphan_channels,
        return_channels=return_channels,
        master_channel=master_channel,
        all_channels=tuple(all_ch),
        mapped_at=0.0,
    )


def _build_empty_session() -> SessionState:
    return SessionState(
        tracks=(),
        return_tracks=(),
        master_track=None,
        tempo=120.0,
        time_sig_numerator=4,
        time_sig_denominator=4,
        is_playing=False,
        current_song_time=0.0,
        scene_count=8,
        timestamp=0.0,
    )


def _make_eq8_params(hp_band: int | None = None, active: bool = True) -> tuple[Parameter, ...]:
    """Build a minimal EQ8 parameter list (42 params).

    If ``hp_band`` is given (1-8), that band is set to HP_48 (filter_type=7)
    and its active flag is set per ``active``.
    """
    # Device On + Scale (indices 0, 1)
    params: list[Parameter] = [
        _build_parameter("Device On", 1.0, index=0),
        _build_parameter("Scale", 0.5, index=1),
    ]
    for band_n in range(1, 9):
        base = 2 + (band_n - 1) * 5
        ft = 7.0 if (hp_band == band_n) else 3.0  # HP_48 = 7, BELL = 3
        act = 1.0 if (hp_band is None or hp_band != band_n or active) else 0.0
        if hp_band == band_n:
            act = 1.0 if active else 0.0
        params += [
            _build_parameter(f"EqFrequency{band_n}", 0.1, index=base),
            _build_parameter(f"EqGain{band_n}", 0.5, index=base + 1),
            _build_parameter(f"EqQ{band_n}", 0.5, index=base + 2),
            _build_parameter(f"FilterType{band_n}", ft, index=base + 3, is_quantized=True),
            _build_parameter(f"ParameterIsActive{band_n}", act, index=base + 4, is_quantized=True),
        ]
    return tuple(params)


def _make_comp2_params(ratio_raw: float = 0.174) -> tuple[Parameter, ...]:
    """Build minimal Compressor2 parameters with a controllable Ratio raw value."""
    return (
        _build_parameter("Threshold", 0.5, index=0),
        _build_parameter("Ratio", ratio_raw, index=1),
        _build_parameter("Attack", 0.2, index=2),
        _build_parameter("Release", 0.3, index=3),
        _build_parameter("Gain", 0.0, index=4),
        _build_parameter("Knee", 0.0, index=5),
    )


# ===========================================================================
# 1. device_maps reverse converters
# ===========================================================================


class TestComp2ReverseConverters:
    """Round-trip and edge case tests for the 4 new reverse converter functions."""

    # --- Threshold ---

    def test_threshold_round_trip_minus_20(self) -> None:
        raw = comp2_threshold_to_raw(-20.0)
        result = comp2_raw_to_threshold_db(raw)
        assert abs(result - (-20.0)) < 1e-9

    def test_threshold_round_trip_minus_6(self) -> None:
        raw = comp2_threshold_to_raw(-6.0)
        result = comp2_raw_to_threshold_db(raw)
        assert abs(result - (-6.0)) < 1e-9

    def test_threshold_raw_zero_returns_minus_60(self) -> None:
        assert comp2_raw_to_threshold_db(0.0) == pytest.approx(-60.0)

    def test_threshold_raw_one_returns_zero_db(self) -> None:
        assert comp2_raw_to_threshold_db(1.0) == pytest.approx(0.0)

    # --- Attack ---

    def test_attack_round_trip_10ms(self) -> None:
        raw = comp2_attack_to_raw(10.0)
        result = comp2_raw_to_attack_ms(raw)
        assert abs(result - 10.0) < 1e-6

    def test_attack_round_trip_100ms(self) -> None:
        raw = comp2_attack_to_raw(100.0)
        result = comp2_raw_to_attack_ms(raw)
        assert abs(result - 100.0) < 1e-6

    def test_attack_raw_zero_returns_zero_ms(self) -> None:
        assert comp2_raw_to_attack_ms(0.0) == 0.0

    def test_attack_raw_one_returns_200ms(self) -> None:
        assert comp2_raw_to_attack_ms(1.0) == pytest.approx(200.0)

    # --- Release ---

    def test_release_round_trip_100ms(self) -> None:
        raw = comp2_release_to_raw(100.0)
        result = comp2_raw_to_release_ms(raw)
        assert abs(result - 100.0) < 1e-6

    def test_release_round_trip_1000ms(self) -> None:
        raw = comp2_release_to_raw(1000.0)
        result = comp2_raw_to_release_ms(raw)
        assert abs(result - 1000.0) < 1e-6

    def test_release_raw_zero_returns_1ms(self) -> None:
        assert comp2_raw_to_release_ms(0.0) == pytest.approx(1.0)

    def test_release_raw_one_returns_10000ms(self) -> None:
        assert comp2_raw_to_release_ms(1.0) == pytest.approx(10_000.0)

    # --- Ratio ---

    def test_ratio_raw_zero_returns_one_to_one(self) -> None:
        # raw=0 → ratio=1.0 (no compression)
        assert comp2_raw_to_ratio(0.0) == pytest.approx(1.0)

    def test_ratio_raw_one_returns_inf(self) -> None:
        assert comp2_raw_to_ratio(1.0) == math.inf

    def test_ratio_above_one_returns_inf(self) -> None:
        # Values > 1.0 are also in limiter territory
        assert comp2_raw_to_ratio(1.5) == math.inf

    def test_ratio_midpoint_is_between_1_and_100(self) -> None:
        ratio = comp2_raw_to_ratio(0.5)
        assert 1.0 < ratio < 100.0

    def test_ratio_small_raw_gives_small_ratio(self) -> None:
        ratio = comp2_raw_to_ratio(0.174)
        # With quadratic model: 1 + 99 * 0.174^2 ≈ 1 + 2.99 ≈ 3.99
        assert ratio == pytest.approx(4.0, abs=0.2)


# ===========================================================================
# 2. types.py — validators and immutability
# ===========================================================================


def _valid_finding(**overrides: object) -> AuditFinding:
    """Build a valid AuditFinding with optional field overrides."""
    defaults: dict[str, object] = dict(
        layer="universal",
        severity="critical",
        icon="❌",
        channel_name="Synth",
        channel_lom_path="live_set tracks 0",
        device_name=None,
        rule_id="no_eq",
        message="Synth: No EQ device found",
        reason="Add an EQ",
        confidence=0.95,
        fix_action=None,
    )
    defaults.update(overrides)
    return AuditFinding(**defaults)  # type: ignore[arg-type]


class TestAuditFindingValidators:
    def test_invalid_layer_raises(self) -> None:
        with pytest.raises(ValueError, match="layer"):
            _valid_finding(layer="bad_layer")

    def test_invalid_severity_raises(self) -> None:
        with pytest.raises(ValueError, match="severity"):
            _valid_finding(severity="extreme")

    def test_confidence_above_1_raises(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            _valid_finding(confidence=1.5)

    def test_confidence_below_0_raises(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            _valid_finding(confidence=-0.1)

    def test_confidence_boundary_zero_ok(self) -> None:
        f = _valid_finding(confidence=0.0)
        assert f.confidence == 0.0

    def test_confidence_boundary_one_ok(self) -> None:
        f = _valid_finding(confidence=1.0)
        assert f.confidence == 1.0

    def test_all_valid_layers_accepted(self) -> None:
        for layer in ("universal", "pattern", "genre"):
            f = _valid_finding(layer=layer)
            assert f.layer == layer

    def test_all_valid_severities_accepted(self) -> None:
        for sev in ("critical", "warning", "info", "suggestion"):
            f = _valid_finding(severity=sev)
            assert f.severity == sev

    def test_fix_action_dict_none(self) -> None:
        f = _valid_finding(fix_action=None)
        assert f.fix_action_dict() is None

    def test_fix_action_dict_converts_to_dict(self) -> None:
        fix = (("lom_path", "live_set tracks 0 devices 1"), ("property", "is_active"), ("value", 1))
        f = _valid_finding(fix_action=fix)
        d = f.fix_action_dict()
        assert d == {"lom_path": "live_set tracks 0 devices 1", "property": "is_active", "value": 1}

    def test_audit_finding_is_frozen(self) -> None:
        f = _valid_finding()
        with pytest.raises(FrozenInstanceError):
            f.severity = "info"  # type: ignore[misc]

    def test_device_info_is_frozen(self) -> None:
        d = _build_device_info()
        with pytest.raises(FrozenInstanceError):
            d.name = "changed"  # type: ignore[misc]

    def test_channel_info_is_frozen(self) -> None:
        ch = _build_channel()
        with pytest.raises(FrozenInstanceError):
            ch.name = "changed"  # type: ignore[misc]

    def test_session_map_is_frozen(self) -> None:
        sm = _build_session_map()
        with pytest.raises(FrozenInstanceError):
            sm.mapped_at = 999.0  # type: ignore[misc]


# ===========================================================================
# 3. mapper.py
# ===========================================================================


class TestClassifyDeviceType:
    def test_eq8_returns_eq(self) -> None:
        assert _classify_device_type("Eq8") == "eq"

    def test_compressor2_returns_compressor(self) -> None:
        assert _classify_device_type("Compressor2") == "compressor"

    def test_glue_compressor_returns_compressor(self) -> None:
        assert _classify_device_type("GlueCompressor") == "compressor"

    def test_stereo_gain_returns_utility(self) -> None:
        assert _classify_device_type("StereoGain") == "utility"

    def test_vst_plugin_returns_instrument(self) -> None:
        assert _classify_device_type("VstPluginDevice") == "instrument"

    def test_vst3_plugin_returns_instrument(self) -> None:
        assert _classify_device_type("Vst3PluginDevice") == "instrument"

    def test_operator_returns_instrument(self) -> None:
        assert _classify_device_type("Operator") == "instrument"

    def test_simpler_returns_instrument(self) -> None:
        assert _classify_device_type("OriginalSimpler") == "instrument"

    def test_unknown_class_returns_unknown(self) -> None:
        assert _classify_device_type("SomeFutureThing") == "unknown"

    def test_multiband_dynamics_returns_compressor(self) -> None:
        assert _classify_device_type("MultibandDynamics") == "compressor"


class TestInferBusType:
    def test_drums_exact(self) -> None:
        assert _infer_bus_type("DRUMS") == "drums"

    def test_drums_fuzzy_perc(self) -> None:
        assert _infer_bus_type("PERC GROUP") == "drums"

    def test_drums_fuzzy_beat(self) -> None:
        assert _infer_bus_type("Beat Bus") == "drums"

    def test_bass_exact(self) -> None:
        assert _infer_bus_type("BASS") == "bass"

    def test_bass_mixed_case(self) -> None:
        assert _infer_bus_type("Bass Group") == "bass"

    def test_melodic_synth(self) -> None:
        assert _infer_bus_type("Synth Bus") == "melodic"

    def test_vocal_bus(self) -> None:
        assert _infer_bus_type("Vocals") == "vocal"

    def test_fx_bus(self) -> None:
        assert _infer_bus_type("FX Return") == "fx"

    def test_unknown_bus(self) -> None:
        assert _infer_bus_type("UNKNOWN THING") == "unknown"

    def test_riser_is_fx(self) -> None:
        assert _infer_bus_type("Risers") == "fx"


class TestMapSessionToMap:
    def test_empty_session_returns_empty_map(self) -> None:
        session = _build_empty_session()
        sm = map_session_to_map(session)
        assert sm.buses == ()
        assert sm.orphan_channels == ()
        assert sm.return_channels == ()
        assert sm.master_channel is None
        assert sm.all_channels == ()

    def test_no_group_tracks_all_are_orphans(self) -> None:
        tracks = (
            _build_track("Kick", 0, TrackType.AUDIO, lom_path="live_set tracks 0"),
            _build_track("Snare", 1, TrackType.AUDIO, lom_path="live_set tracks 1"),
        )
        session = SessionState(
            tracks=tracks,
            return_tracks=(),
            master_track=None,
            tempo=120.0,
            time_sig_numerator=4,
            time_sig_denominator=4,
            is_playing=False,
            current_song_time=0.0,
            scene_count=8,
        )
        sm = map_session_to_map(session)
        assert len(sm.orphan_channels) == 2
        assert sm.buses == ()
        assert all(ch.is_orphan for ch in sm.orphan_channels)

    def test_single_group_with_three_members(self) -> None:
        tracks = (
            _build_track("DRUMS", 0, TrackType.GROUP, lom_path="live_set tracks 0"),
            _build_track("Kick", 1, TrackType.AUDIO, lom_path="live_set tracks 1"),
            _build_track("Snare", 2, TrackType.AUDIO, lom_path="live_set tracks 2"),
            _build_track("HH", 3, TrackType.AUDIO, lom_path="live_set tracks 3"),
        )
        session = SessionState(
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
        sm = map_session_to_map(session)
        assert len(sm.buses) == 1
        bus = sm.buses[0]
        assert bus.name == "DRUMS"
        assert bus.bus_type == "drums"
        assert len(bus.channels) == 3
        assert sm.orphan_channels == ()

    def test_multiple_groups_channels_assigned_correctly(self) -> None:
        tracks = (
            _build_track("DRUMS", 0, TrackType.GROUP, lom_path="live_set tracks 0"),
            _build_track("Kick", 1, TrackType.AUDIO, lom_path="live_set tracks 1"),
            _build_track("BASS", 2, TrackType.GROUP, lom_path="live_set tracks 2"),
            _build_track("Sub", 3, TrackType.AUDIO, lom_path="live_set tracks 3"),
            _build_track("Bass Synth", 4, TrackType.MIDI, lom_path="live_set tracks 4"),
        )
        session = SessionState(
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
        sm = map_session_to_map(session)
        assert len(sm.buses) == 2
        drum_bus = sm.buses[0]
        bass_bus = sm.buses[1]
        assert drum_bus.name == "DRUMS"
        assert len(drum_bus.channels) == 1
        assert drum_bus.channels[0].name == "Kick"
        assert bass_bus.name == "BASS"
        assert len(bass_bus.channels) == 2
        assert bass_bus.channels[0].name == "Sub"
        assert bass_bus.channels[1].name == "Bass Synth"

    def test_orphans_before_first_group(self) -> None:
        tracks = (
            _build_track("Intro FX", 0, TrackType.AUDIO, lom_path="live_set tracks 0"),
            _build_track("DRUMS", 1, TrackType.GROUP, lom_path="live_set tracks 1"),
            _build_track("Kick", 2, TrackType.AUDIO, lom_path="live_set tracks 2"),
        )
        session = SessionState(
            tracks=tracks,
            return_tracks=(),
            master_track=None,
            tempo=120.0,
            time_sig_numerator=4,
            time_sig_denominator=4,
            is_playing=False,
            current_song_time=0.0,
            scene_count=8,
        )
        sm = map_session_to_map(session)
        assert len(sm.orphan_channels) == 1
        assert sm.orphan_channels[0].name == "Intro FX"
        assert len(sm.buses) == 1
        assert len(sm.buses[0].channels) == 1

    def test_return_tracks_go_to_return_channels(self) -> None:
        ret = _build_track("Reverb", 0, TrackType.RETURN, lom_path="live_set return_tracks 0")
        session = SessionState(
            tracks=(),
            return_tracks=(ret,),
            master_track=None,
            tempo=120.0,
            time_sig_numerator=4,
            time_sig_denominator=4,
            is_playing=False,
            current_song_time=0.0,
            scene_count=8,
        )
        sm = map_session_to_map(session)
        assert len(sm.return_channels) == 1
        assert sm.return_channels[0].name == "Reverb"
        assert sm.return_channels[0].track_type == TrackType.RETURN

    def test_master_track_goes_to_master_channel(self) -> None:
        master = _build_track("Master", 0, TrackType.MASTER, lom_path="live_set master_track")
        session = SessionState(
            tracks=(),
            return_tracks=(),
            master_track=master,
            tempo=120.0,
            time_sig_numerator=4,
            time_sig_denominator=4,
            is_playing=False,
            current_song_time=0.0,
            scene_count=8,
        )
        sm = map_session_to_map(session)
        assert sm.master_channel is not None
        assert sm.master_channel.name == "Master"

    def test_master_not_in_all_channels(self) -> None:
        master = _build_track("Master", 0, TrackType.MASTER, lom_path="live_set master_track")
        session = SessionState(
            tracks=(_build_track("Kick", 0, TrackType.AUDIO, lom_path="live_set tracks 0"),),
            return_tracks=(),
            master_track=master,
            tempo=120.0,
            time_sig_numerator=4,
            time_sig_denominator=4,
            is_playing=False,
            current_song_time=0.0,
            scene_count=8,
        )
        sm = map_session_to_map(session)
        assert all(ch.name != "Master" for ch in sm.all_channels)

    def test_channels_in_group_have_parent_bus_set(self) -> None:
        tracks = (
            _build_track("DRUMS", 0, TrackType.GROUP, lom_path="live_set tracks 0"),
            _build_track("Kick", 1, TrackType.AUDIO, lom_path="live_set tracks 1"),
        )
        session = SessionState(
            tracks=tracks,
            return_tracks=(),
            master_track=None,
            tempo=120.0,
            time_sig_numerator=4,
            time_sig_denominator=4,
            is_playing=False,
            current_song_time=0.0,
            scene_count=8,
        )
        sm = map_session_to_map(session)
        kick_ch = sm.buses[0].channels[0]
        assert kick_ch.parent_bus == "DRUMS"
        assert not kick_ch.is_orphan

    def test_mapped_at_is_passed_through(self) -> None:
        session = _build_empty_session()
        sm = map_session_to_map(session, mapped_at=12345.0)
        assert sm.mapped_at == 12345.0


# ===========================================================================
# 4. universal_audit.py
# ===========================================================================


class TestCheckNoEq:
    def test_returns_none_for_channel_with_eq(self) -> None:
        eq = _build_device_info(class_name="Eq8", device_type="eq")
        inst = _build_device_info(class_name="OriginalSimpler", device_type="instrument")
        ch = _build_channel(devices=(inst, eq))
        assert check_no_eq(ch) is None

    def test_returns_finding_for_instrument_without_eq(self) -> None:
        inst = _build_device_info(class_name="OriginalSimpler", device_type="instrument")
        ch = _build_channel(devices=(inst,))
        f = check_no_eq(ch)
        assert f is not None
        assert f.rule_id == "no_eq"
        assert f.severity == "critical"
        assert f.layer == "universal"

    def test_returns_none_for_channel_without_instrument(self) -> None:
        # A channel with only an EQ but no instrument — nothing to report
        eq = _build_device_info(class_name="Eq8", device_type="eq")
        ch = _build_channel(devices=(eq,))
        assert check_no_eq(ch) is None

    def test_returns_none_for_return_track(self) -> None:
        inst = _build_device_info(class_name="OriginalSimpler", device_type="instrument")
        ch = _build_channel(devices=(inst,), track_type=TrackType.RETURN)
        assert check_no_eq(ch) is None

    def test_returns_none_for_empty_channel(self) -> None:
        ch = _build_channel(devices=())
        assert check_no_eq(ch) is None


class TestCheckNoHighpass:
    def _make_eq8_device_info(self, hp_band: int | None = None, active: bool = True) -> DeviceInfo:
        raw_params = _make_eq8_params(hp_band=hp_band, active=active)
        params = tuple((p.name, p.display_value, p.value) for p in raw_params)
        return DeviceInfo(
            name="EQ Eight",
            class_name="Eq8",
            is_active=True,
            device_type="eq",
            params=params,
            lom_path="live_set tracks 0 devices 0",
        )

    def test_returns_none_for_kick_channel(self) -> None:
        eq = self._make_eq8_device_info(hp_band=None)
        inst = _build_device_info(class_name="InstrumentImpulse", device_type="instrument")
        ch = _build_channel(name="Kick", devices=(inst, eq))
        assert check_no_highpass(ch) is None

    def test_returns_none_for_sub_channel(self) -> None:
        eq = self._make_eq8_device_info(hp_band=None)
        inst = _build_device_info(class_name="OriginalSimpler", device_type="instrument")
        ch = _build_channel(name="808 Sub", devices=(inst, eq))
        assert check_no_highpass(ch) is None

    def test_returns_none_for_channel_with_hp_active(self) -> None:
        eq = self._make_eq8_device_info(hp_band=1, active=True)
        inst = _build_device_info(class_name="OriginalSimpler", device_type="instrument")
        ch = _build_channel(name="Pad", devices=(inst, eq))
        assert check_no_highpass(ch) is None

    def test_returns_finding_for_channel_without_hp(self) -> None:
        # EQ has no HP band set
        eq = self._make_eq8_device_info(hp_band=None)
        inst = _build_device_info(class_name="OriginalSimpler", device_type="instrument")
        ch = _build_channel(name="Pad", devices=(inst, eq))
        f = check_no_highpass(ch)
        assert f is not None
        assert f.rule_id == "no_highpass"
        assert f.severity == "critical"

    def test_returns_none_for_channel_with_no_instrument(self) -> None:
        eq = self._make_eq8_device_info(hp_band=None)
        ch = _build_channel(name="FX", devices=(eq,))
        assert check_no_highpass(ch) is None

    def test_returns_none_for_return_track(self) -> None:
        eq = self._make_eq8_device_info(hp_band=None)
        inst = _build_device_info(class_name="OriginalSimpler", device_type="instrument")
        ch = _build_channel(name="Pad", devices=(inst, eq), track_type=TrackType.RETURN)
        assert check_no_highpass(ch) is None


class TestCheckExtremeCompression:
    def test_returns_finding_for_ratio_above_10(self) -> None:
        # raw=0.99 → ratio ≈ 1 + 99 * 0.99^2 ≈ 97.9 → > 10
        params = _make_comp2_params(ratio_raw=0.99)
        comp = DeviceInfo(
            name="Compressor 2",
            class_name="Compressor2",
            is_active=True,
            device_type="compressor",
            params=tuple((p.name, p.display_value, p.value) for p in params),
            lom_path="live_set tracks 0 devices 0",
        )
        ch = _build_channel(devices=(comp,))
        f = check_extreme_compression(ch)
        assert f is not None
        assert f.rule_id == "extreme_compression"
        assert f.severity == "warning"
        assert f.fix_action is not None

    def test_returns_none_for_ratio_4_to_1(self) -> None:
        # ratio ≈ 4:1 → raw ≈ 0.174
        params = _make_comp2_params(ratio_raw=0.174)
        comp = DeviceInfo(
            name="Compressor 2",
            class_name="Compressor2",
            is_active=True,
            device_type="compressor",
            params=tuple((p.name, p.display_value, p.value) for p in params),
            lom_path="live_set tracks 0 devices 0",
        )
        ch = _build_channel(devices=(comp,))
        assert check_extreme_compression(ch) is None

    def test_returns_none_for_no_compressor(self) -> None:
        eq = _build_device_info(class_name="Eq8", device_type="eq")
        ch = _build_channel(devices=(eq,))
        assert check_extreme_compression(ch) is None

    def test_returns_none_for_glue_compressor(self) -> None:
        # Only Compressor2 is checked (class_name exact match)
        params = _make_comp2_params(ratio_raw=0.99)
        glue = DeviceInfo(
            name="Glue Compressor",
            class_name="GlueCompressor",
            is_active=True,
            device_type="compressor",
            params=tuple((p.name, p.display_value, p.value) for p in params),
            lom_path="live_set tracks 0 devices 0",
        )
        ch = _build_channel(devices=(glue,))
        assert check_extreme_compression(ch) is None


class TestCheckUntouchedFader:
    def test_returns_finding_for_zero_db(self) -> None:
        ch = _build_channel(volume_db=0.0)
        f = check_untouched_fader(ch)
        assert f is not None
        assert f.rule_id == "untouched_fader"
        assert f.severity == "info"

    def test_returns_none_for_minus_6_db(self) -> None:
        ch = _build_channel(volume_db=-6.0)
        assert check_untouched_fader(ch) is None

    def test_returns_none_for_master_at_zero(self) -> None:
        ch = _build_channel(volume_db=0.0, track_type=TrackType.MASTER)
        assert check_untouched_fader(ch) is None

    def test_returns_none_for_positive_volume(self) -> None:
        ch = _build_channel(volume_db=3.0)
        assert check_untouched_fader(ch) is None


class TestCheckBypassedPlugin:
    def test_returns_finding_for_bypassed_device(self) -> None:
        eq = _build_device_info(class_name="Eq8", device_type="eq", is_active=False)
        ch = _build_channel(devices=(eq,))
        f = check_bypassed_plugin(ch)
        assert f is not None
        assert f.rule_id == "bypassed_plugin"
        assert f.severity == "info"
        assert f.fix_action is not None
        assert f.device_name == "EQ Eight"

    def test_returns_none_for_all_active(self) -> None:
        eq = _build_device_info(class_name="Eq8", device_type="eq", is_active=True)
        ch = _build_channel(devices=(eq,))
        assert check_bypassed_plugin(ch) is None

    def test_returns_none_for_empty_devices(self) -> None:
        ch = _build_channel(devices=())
        assert check_bypassed_plugin(ch) is None

    def test_fix_action_is_correct_structure(self) -> None:
        eq = _build_device_info(
            class_name="Eq8",
            device_type="eq",
            is_active=False,
            lom_path="live_set tracks 0 devices 1",
        )
        ch = _build_channel(devices=(eq,))
        f = check_bypassed_plugin(ch)
        assert f is not None
        d = f.fix_action_dict()
        assert d is not None
        assert d["property"] == "is_active"
        assert d["value"] == 1


class TestCheckMutedWithCpu:
    def test_returns_finding_for_muted_with_devices(self) -> None:
        eq = _build_device_info(class_name="Eq8", device_type="eq")
        ch = _build_channel(is_muted=True, devices=(eq,))
        f = check_muted_with_cpu(ch)
        assert f is not None
        assert f.rule_id == "muted_with_cpu"
        assert f.severity == "info"

    def test_returns_none_for_muted_with_no_devices(self) -> None:
        ch = _build_channel(is_muted=True, devices=())
        assert check_muted_with_cpu(ch) is None

    def test_returns_none_for_unmuted_channel(self) -> None:
        eq = _build_device_info(class_name="Eq8", device_type="eq")
        ch = _build_channel(is_muted=False, devices=(eq,))
        assert check_muted_with_cpu(ch) is None


class TestCheckMonoOnStereo:
    def _make_utility_info(self, width_raw: float) -> DeviceInfo:
        params = (
            ("Gain", "0 dB", 0.5),
            ("Stereo Width", "0 %", width_raw),
            ("Mono", "Off", 0.0),
        )
        return DeviceInfo(
            name="Utility",
            class_name="StereoGain",
            is_active=True,
            device_type="utility",
            params=params,
            lom_path="live_set tracks 0 devices 0",
        )

    def test_returns_none_for_normal_width(self) -> None:
        util = self._make_utility_info(width_raw=0.25)  # 100% = normal
        ch = _build_channel(name="Pad", devices=(util,))
        assert check_mono_on_stereo(ch) is None

    def test_returns_warning_for_zero_width_on_pad(self) -> None:
        util = self._make_utility_info(width_raw=0.0)  # 0% = mono
        ch = _build_channel(name="Pad", devices=(util,))
        f = check_mono_on_stereo(ch)
        assert f is not None
        assert f.rule_id == "mono_on_stereo"
        assert f.severity == "warning"

    def test_returns_none_for_zero_width_on_kick(self) -> None:
        util = self._make_utility_info(width_raw=0.0)
        ch = _build_channel(name="Kick", devices=(util,))
        assert check_mono_on_stereo(ch) is None

    def test_returns_none_for_zero_width_on_sub(self) -> None:
        util = self._make_utility_info(width_raw=0.0)
        ch = _build_channel(name="808 Sub", devices=(util,))
        assert check_mono_on_stereo(ch) is None

    def test_returns_none_for_channel_without_utility(self) -> None:
        ch = _build_channel(name="Pad", devices=())
        assert check_mono_on_stereo(ch) is None


class TestCheckDuplicateDeviceType:
    def test_returns_finding_for_two_eqs(self) -> None:
        eq1 = _build_device_info(name="EQ Eight", class_name="Eq8", device_type="eq")
        eq2 = _build_device_info(name="EQ Eight 2", class_name="Eq8", device_type="eq")
        ch = _build_channel(devices=(eq1, eq2))
        f = check_duplicate_device_type(ch)
        assert f is not None
        assert f.rule_id == "duplicate_device_type"
        assert f.severity == "info"
        assert "2" in f.message

    def test_returns_none_for_one_of_each(self) -> None:
        eq = _build_device_info(class_name="Eq8", device_type="eq")
        comp = _build_device_info(class_name="Compressor2", device_type="compressor")
        ch = _build_channel(devices=(eq, comp))
        assert check_duplicate_device_type(ch) is None

    def test_returns_none_for_empty_channel(self) -> None:
        ch = _build_channel(devices=())
        assert check_duplicate_device_type(ch) is None

    def test_unknown_types_not_counted(self) -> None:
        # Two "unknown" type devices should not trigger duplicate check
        d1 = _build_device_info(class_name="SomeFx", device_type="unknown")
        d2 = _build_device_info(class_name="SomeFx", device_type="unknown")
        ch = _build_channel(devices=(d1, d2))
        assert check_duplicate_device_type(ch) is None


class TestRunUniversalAudit:
    def test_empty_session_returns_empty_list(self) -> None:
        sm = _build_session_map()
        findings = run_universal_audit(sm)
        assert findings == []

    def test_critical_findings_come_first(self) -> None:
        # Channel with no eq (critical) + bypassed plugin (info)
        inst = _build_device_info(class_name="OriginalSimpler", device_type="instrument")
        eq_bypassed = _build_device_info(class_name="Eq8", device_type="eq", is_active=False)
        # No active eq → check_no_eq fires (critical)
        # Also bypassed eq → check_bypassed_plugin fires (info)
        ch = _build_channel(name="Synth", devices=(inst, eq_bypassed))
        sm = _build_session_map(orphan_channels=(ch,))
        findings = run_universal_audit(sm)
        assert len(findings) > 0
        # Critical must come before info/warning
        severities = [f.severity for f in findings]
        # Find first non-critical index
        critical_indices = [i for i, s in enumerate(severities) if s == "critical"]
        other_indices = [i for i, s in enumerate(severities) if s != "critical"]
        if critical_indices and other_indices:
            assert max(critical_indices) < min(other_indices)

    def test_clean_channel_produces_no_findings(self) -> None:
        # Channel with instrument + EQ with HP + moderate compression
        inst = _build_device_info(class_name="OriginalSimpler", device_type="instrument")
        eq_params = tuple(
            (p.name, p.display_value, p.value) for p in _make_eq8_params(hp_band=1, active=True)
        )
        eq = DeviceInfo(
            name="EQ Eight",
            class_name="Eq8",
            is_active=True,
            device_type="eq",
            params=eq_params,
            lom_path="live_set tracks 0 devices 1",
        )
        ch = _build_channel(name="Pad", devices=(inst, eq), volume_db=-6.0)
        sm = _build_session_map(orphan_channels=(ch,))
        findings = run_universal_audit(sm)
        # Should have no critical or warning findings for this channel
        channel_findings = [f for f in findings if f.channel_name == "Pad"]
        assert all(f.severity in ("info", "suggestion") for f in channel_findings)

    def test_returns_list_sorted_by_severity(self) -> None:
        # Two channels: one with untouched fader (info), one with no eq (critical)
        inst = _build_device_info(class_name="OriginalSimpler", device_type="instrument")
        ch_no_eq = _build_channel(name="Synth", devices=(inst,))
        ch_fader = _build_channel(name="Drums", volume_db=0.0, devices=())
        sm = _build_session_map(orphan_channels=(ch_no_eq, ch_fader))
        findings = run_universal_audit(sm)
        severities = [f.severity for f in findings]
        order = {"critical": 0, "warning": 1, "info": 2, "suggestion": 3}
        for i in range(len(severities) - 1):
            assert order[severities[i]] <= order[severities[i + 1]]

    def test_master_channel_not_in_all_channels(self) -> None:
        # Master should be excluded from audit (not in all_channels)
        master_ch = _build_channel(name="Master", track_type=TrackType.MASTER, volume_db=0.0)
        sm = _build_session_map(master_channel=master_ch)
        findings = run_universal_audit(sm)
        # No findings should reference master in this test
        assert all(f.channel_name != "Master" for f in findings)


# ===========================================================================
# ChannelInfo.volume_lom_id field + mapper propagation (added Day 6)
# ===========================================================================


class TestChannelInfoVolumeLomId:
    """Tests for the volume_lom_id field added to ChannelInfo and Track."""

    def test_channel_info_volume_lom_id_defaults_to_zero(self) -> None:
        ch = _build_channel(name="Lead", lom_path="live_set tracks 0")
        assert ch.volume_lom_id == 0

    def test_channel_info_volume_lom_id_can_be_set(self) -> None:
        ch = ChannelInfo(
            name="Lead",
            index=0,
            track_type=TrackType.MIDI,
            parent_bus=None,
            is_orphan=True,
            volume_db=-6.0,
            pan=0.0,
            is_muted=False,
            is_solo=False,
            devices=(),
            lom_path="live_set tracks 0",
            volume_lom_id=42,
        )
        assert ch.volume_lom_id == 42

    def test_track_volume_lom_id_defaults_to_zero(self) -> None:
        t = _build_track(name="Kick", lom_path="live_set tracks 0")
        assert t.volume_lom_id == 0

    def test_track_volume_lom_id_propagates_via_mapper(self) -> None:
        """Mapper must copy volume_lom_id from Track to ChannelInfo."""
        from core.ableton.types import SessionState

        t = Track(
            name="Pad",
            index=0,
            type=TrackType.MIDI,
            arm=False,
            solo=False,
            mute=False,
            volume_db=-6.0,
            pan=0.0,
            devices=(),
            clips=(),
            lom_path="live_set tracks 0",
            volume_lom_id=99,
        )
        session = SessionState(
            tracks=(t,),
            return_tracks=(),
            master_track=None,
            tempo=120.0,
            time_sig_numerator=4,
            time_sig_denominator=4,
            is_playing=False,
            current_song_time=0.0,
            scene_count=0,
        )
        from core.session_intelligence.mapper import map_session_to_map

        session_map = map_session_to_map(session, mapped_at=0.0)
        assert len(session_map.orphan_channels) == 1
        assert session_map.orphan_channels[0].volume_lom_id == 99

    def test_track_volume_lom_id_zero_stays_zero_in_channel(self) -> None:
        """When scanner doesn't provide lom_id (old device), value stays 0."""
        from core.ableton.types import SessionState

        t = _build_track(name="Synth", lom_path="live_set tracks 0")
        # volume_lom_id is 0 (default)
        session = SessionState(
            tracks=(t,),
            return_tracks=(),
            master_track=None,
            tempo=120.0,
            time_sig_numerator=4,
            time_sig_denominator=4,
            is_playing=False,
            current_song_time=0.0,
            scene_count=0,
        )
        from core.session_intelligence.mapper import map_session_to_map

        session_map = map_session_to_map(session, mapped_at=0.0)
        assert session_map.orphan_channels[0].volume_lom_id == 0


# ===========================================================================
# LOMCommand.to_dict() — conditional lom_id serialization (added Day 6)
# ===========================================================================


class TestLOMCommandToDict:
    """Tests for LOMCommand.to_dict() with conditional lom_id inclusion."""

    def test_to_dict_omits_lom_id_when_zero(self) -> None:
        from core.ableton.types import LOMCommand

        cmd = LOMCommand(
            type="set_property",
            lom_path="live_set tracks 0",
            property="mute",
            value=1,
            lom_id=0,
        )
        d = cmd.to_dict()
        assert "lom_id" not in d

    def test_to_dict_includes_lom_id_when_nonzero(self) -> None:
        from core.ableton.types import LOMCommand

        cmd = LOMCommand(
            type="set_property",
            lom_path="live_set tracks 0 mixer_device volume",
            property="value",
            value=0.757,
            lom_id=42,
        )
        d = cmd.to_dict()
        assert d["lom_id"] == 42

    def test_to_dict_always_includes_type_lom_path_property_value(self) -> None:
        from core.ableton.types import LOMCommand

        cmd = LOMCommand(
            type="set_parameter",
            lom_path="live_set tracks 1 devices 0 parameters 2",
            property="value",
            value=0.5,
            lom_id=7,
        )
        d = cmd.to_dict()
        assert d["type"] == "set_parameter"
        assert d["lom_path"] == "live_set tracks 1 devices 0 parameters 2"
        assert d["property"] == "value"
        assert d["value"] == 0.5
        assert d["lom_id"] == 7
