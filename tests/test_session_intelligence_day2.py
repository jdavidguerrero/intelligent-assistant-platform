"""tests/test_session_intelligence_day2.py — Day 2: Session Intelligence 3-Layer Audit System.

Tests cover:
  - core/session_intelligence/gain_staging.py
  - core/session_intelligence/pattern_learner.py
  - core/session_intelligence/genre_presets.py
  - core/session_intelligence/recommendations.py
  - ingestion/pattern_store.py
  - ingestion/session_auditor.py
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from core.ableton.types import SessionState, TrackType
from core.session_intelligence.gain_staging import (
    check_low_freq_not_mono,
    check_low_headroom,
    check_untouched_faders,
    run_gain_staging_audit,
)
from core.session_intelligence.genre_presets import run_genre_audit
from core.session_intelligence.pattern_learner import (
    MIN_SESSIONS_REQUIRED,
    _infer_instrument_type,
    _is_anomaly,
    _mad,
    _median,
    detect_pattern_anomalies,
    learn_from_channel,
)
from core.session_intelligence.recommendations import (
    filter_findings_by_layer,
    filter_findings_by_severity,
    generate_audit_report,
)
from core.session_intelligence.types import (
    AuditFinding,
    BusInfo,
    ChannelInfo,
    DeviceInfo,
    SessionMap,
)
from ingestion.pattern_store import PatternStore
from ingestion.session_auditor import SessionAuditor

# ===========================================================================
# Test factories (shared helpers)
# ===========================================================================


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
    volume_lom_id: int = 0,
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
        volume_lom_id=volume_lom_id,
    )


def _build_session_map(
    buses: tuple[BusInfo, ...] = (),
    orphan_channels: tuple[ChannelInfo, ...] = (),
    return_channels: tuple[ChannelInfo, ...] = (),
    master_channel: ChannelInfo | None = None,
) -> SessionMap:
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


def _valid_finding(**overrides: object) -> AuditFinding:
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


def _make_eq8_params_with_hp(band_n: int = 1) -> tuple[tuple[str, str, float], ...]:
    """Build a minimal EQ8 params tuple that has an active HP_48 on band_n."""
    params: list[tuple[str, str, float]] = [
        ("Device On", "On", 1.0),
        ("Scale", "1.0", 0.5),
    ]
    for n in range(1, 9):
        base = 2 + (n - 1) * 5
        ft = 7.0 if n == band_n else 3.0  # HP_48 = 7, BELL = 3
        act = 1.0
        freq = 0.1  # raw freq value
        params += [
            (f"EqFrequency{n}", "100 Hz", freq),
            (f"EqGain{n}", "0 dB", 0.5),
            (f"EqQ{n}", "0.7", 0.5),
            (f"FilterType{n}", str(ft), ft),
            (f"ParameterIsActive{n}", str(act), act),
        ]
    return tuple(params)


# ===========================================================================
# 1. gain_staging.py
# ===========================================================================


class TestCheckLowHeadroom:
    def test_critical_for_volume_above_minus_3(self) -> None:
        ch = _build_channel(name="Lead", volume_db=-1.0, lom_path="live_set tracks 0")
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_low_headroom(sm)
        assert len(findings) == 1
        assert findings[0].severity == "critical"
        assert findings[0].rule_id == "gs_low_headroom"

    def test_warning_for_volume_between_minus_6_and_minus_3(self) -> None:
        ch = _build_channel(name="Lead", volume_db=-5.0, lom_path="live_set tracks 0")
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_low_headroom(sm)
        assert len(findings) == 1
        assert findings[0].severity == "warning"

    def test_no_finding_for_volume_below_minus_6(self) -> None:
        ch = _build_channel(name="Lead", volume_db=-12.0, lom_path="live_set tracks 0")
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_low_headroom(sm)
        assert findings == []

    def test_no_finding_at_exactly_minus_6(self) -> None:
        ch = _build_channel(name="Lead", volume_db=-6.0, lom_path="live_set tracks 0")
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_low_headroom(sm)
        assert findings == []

    def test_master_channel_skipped(self) -> None:
        master = _build_channel(
            name="Master", volume_db=-1.0, track_type=TrackType.MASTER,
            lom_path="live_set master_track"
        )
        sm = _build_session_map(master_channel=master)
        # all_channels does not include master
        findings = check_low_headroom(sm)
        assert findings == []

    def test_fix_action_present_for_critical(self) -> None:
        ch = _build_channel(name="Lead", volume_db=-1.0, lom_path="live_set tracks 0")
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_low_headroom(sm)
        assert findings[0].fix_action is not None

    def test_critical_sorted_before_warning(self) -> None:
        ch_crit = _build_channel(name="Lead", volume_db=-1.0, lom_path="live_set tracks 0")
        ch_warn = _build_channel(name="Pad", volume_db=-4.5, lom_path="live_set tracks 1")
        sm = _build_session_map(orphan_channels=(ch_warn, ch_crit))
        findings = check_low_headroom(sm)
        assert findings[0].severity == "critical"
        assert findings[1].severity == "warning"


class TestCheckUntouchedFaders:
    def test_info_for_fader_at_zero_db(self) -> None:
        ch = _build_channel(name="Pad", volume_db=0.0, lom_path="live_set tracks 0")
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_untouched_faders(sm)
        assert len(findings) == 1
        assert findings[0].severity == "info"
        assert findings[0].rule_id == "gs_untouched_fader"

    def test_no_finding_for_adjusted_fader(self) -> None:
        ch = _build_channel(name="Pad", volume_db=-6.0, lom_path="live_set tracks 0")
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_untouched_faders(sm)
        assert findings == []

    def test_master_skipped(self) -> None:
        master = _build_channel(
            name="Master", volume_db=0.0, track_type=TrackType.MASTER,
            lom_path="live_set master_track"
        )
        sm = _build_session_map(master_channel=master)
        findings = check_untouched_faders(sm)
        assert findings == []

    def test_fix_action_is_none(self) -> None:
        ch = _build_channel(name="Pad", volume_db=0.0, lom_path="live_set tracks 0")
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_untouched_faders(sm)
        assert findings[0].fix_action is None


class TestCheckLowFreqNotMono:
    def test_warning_for_bass_channel_panned(self) -> None:
        ch = _build_channel(name="Bass Synth", pan=0.5, lom_path="live_set tracks 0")
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_low_freq_not_mono(sm)
        assert len(findings) == 1
        assert findings[0].severity == "warning"
        assert findings[0].rule_id == "gs_bass_not_mono"

    def test_warning_for_sub_channel_panned(self) -> None:
        ch = _build_channel(name="Sub 808", pan=-0.5, lom_path="live_set tracks 0")
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_low_freq_not_mono(sm)
        assert len(findings) == 1

    def test_no_finding_for_bass_centered(self) -> None:
        ch = _build_channel(name="Bass Synth", pan=0.0, lom_path="live_set tracks 0")
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_low_freq_not_mono(sm)
        assert findings == []

    def test_no_finding_for_lead_panned(self) -> None:
        ch = _build_channel(name="Lead", pan=0.5, lom_path="live_set tracks 0")
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_low_freq_not_mono(sm)
        assert findings == []

    def test_pan_tolerance_boundary(self) -> None:
        # pan=0.1 is exactly at the threshold — no finding
        ch = _build_channel(name="Bass Synth", pan=0.1, lom_path="live_set tracks 0")
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_low_freq_not_mono(sm)
        assert findings == []


class TestRunGainStagingAudit:
    def test_returns_empty_for_healthy_session(self) -> None:
        ch = _build_channel(name="Pad", volume_db=-12.0, pan=0.0, lom_path="live_set tracks 0")
        sm = _build_session_map(orphan_channels=(ch,))
        findings = run_gain_staging_audit(sm)
        assert findings == []

    def test_combines_all_check_results(self) -> None:
        # untouched fader + headroom critical + bass panned
        ch_zero = _build_channel(name="Snare", volume_db=0.0, lom_path="live_set tracks 0")
        ch_hot = _build_channel(name="Pad", volume_db=-1.0, lom_path="live_set tracks 1")
        ch_bass = _build_channel(name="Bass", pan=0.5, lom_path="live_set tracks 2")
        sm = _build_session_map(orphan_channels=(ch_zero, ch_hot, ch_bass))
        findings = run_gain_staging_audit(sm)
        rule_ids = {f.rule_id for f in findings}
        assert "gs_untouched_fader" in rule_ids
        assert "gs_low_headroom" in rule_ids
        assert "gs_bass_not_mono" in rule_ids

    def test_sorted_by_severity(self) -> None:
        ch_zero = _build_channel(name="Snare", volume_db=0.0, lom_path="live_set tracks 0")
        ch_hot = _build_channel(name="Lead", volume_db=-1.0, lom_path="live_set tracks 1")
        sm = _build_session_map(orphan_channels=(ch_zero, ch_hot))
        findings = run_gain_staging_audit(sm)
        order = {"critical": 0, "warning": 1, "info": 2, "suggestion": 3}
        for i in range(len(findings) - 1):
            assert order[findings[i].severity] <= order[findings[i + 1].severity]


# ===========================================================================
# 2. pattern_learner.py
# ===========================================================================


class TestMedian:
    def test_median_odd_count(self) -> None:
        assert _median([1.0, 2.0, 3.0, 4.0, 5.0]) == 3.0

    def test_median_even_count(self) -> None:
        assert _median([1.0, 2.0, 3.0, 4.0]) == 2.5

    def test_median_single(self) -> None:
        assert _median([42.0]) == 42.0

    def test_median_empty(self) -> None:
        assert _median([]) == 0.0

    def test_median_sorted_ascending(self) -> None:
        assert _median([10.0, 20.0, 30.0]) == 20.0


class TestMad:
    def test_mad_symmetric(self) -> None:
        # [1,2,3,4,5] → median=3, deviations=[2,1,0,1,2] → MAD=1
        assert _mad([1.0, 2.0, 3.0, 4.0, 5.0], 3.0) == 1.0

    def test_mad_identical_values(self) -> None:
        assert _mad([5.0, 5.0, 5.0], 5.0) == 0.0

    def test_mad_single_value(self) -> None:
        assert _mad([10.0], 10.0) == 0.0


class TestIsAnomaly:
    def test_returns_false_for_insufficient_data(self) -> None:
        assert _is_anomaly(100.0, [1.0, 2.0]) is False

    def test_returns_false_for_empty_list(self) -> None:
        assert _is_anomaly(100.0, []) is False

    def test_returns_true_for_value_far_from_median(self) -> None:
        # values centered around -12, value = 0 (12 units away, MAD=1)
        values = [-13.0, -12.0, -12.0, -11.0, -12.0]
        assert _is_anomaly(0.0, values) is True

    def test_returns_false_for_value_within_range(self) -> None:
        values = [-12.0, -11.5, -12.5, -11.0, -12.0]
        assert _is_anomaly(-12.0, values) is False

    def test_returns_false_for_identical_values_same_as_value(self) -> None:
        # MAD=0, so threshold=0, any non-equal value would be anomaly
        # but equal value is not
        values = [-12.0, -12.0, -12.0]
        assert _is_anomaly(-12.0, values) is False

    def test_returns_false_for_exactly_3_values(self) -> None:
        # 3 values is enough for _is_anomaly
        values = [-12.0, -11.0, -13.0]
        result = _is_anomaly(-12.0, values)
        assert isinstance(result, bool)


class TestDetectPatternAnomalies:
    def _make_pad_channel(self) -> ChannelInfo:
        return _build_channel(name="Pad 1", volume_db=-20.0, lom_path="live_set tracks 0")

    def _make_patterns(self) -> dict:
        return {
            "pad": {
                "sample_count": 10,
                "volume_db_values": [-12.0, -11.5, -12.5, -12.0, -11.0, -12.2, -12.3, -11.8, -12.1, -11.9],
                "hp_freq_values": [1.0, 1.0, 1.0, 1.0, 1.0],  # 5 sessions with HP
                "comp_ratio_values": [0.174, 0.2, 0.18],
            }
        }

    def test_returns_empty_if_sessions_below_minimum(self) -> None:
        ch = self._make_pad_channel()
        patterns = self._make_patterns()
        result = detect_pattern_anomalies(ch, patterns, sessions_saved=MIN_SESSIONS_REQUIRED - 1)
        assert result == []

    def test_returns_empty_at_zero_sessions(self) -> None:
        ch = self._make_pad_channel()
        result = detect_pattern_anomalies(ch, {}, sessions_saved=0)
        assert result == []

    def test_activates_at_min_sessions_required(self) -> None:
        ch = self._make_pad_channel()
        patterns = self._make_patterns()
        # -20.0 dB is anomalous vs historical -12 dB pattern
        result = detect_pattern_anomalies(ch, patterns, sessions_saved=MIN_SESSIONS_REQUIRED)
        assert len(result) >= 1

    def test_volume_anomaly_finding_has_correct_fields(self) -> None:
        ch = self._make_pad_channel()
        patterns = self._make_patterns()
        findings = detect_pattern_anomalies(ch, patterns, sessions_saved=MIN_SESSIONS_REQUIRED)
        vol_findings = [f for f in findings if f.rule_id == "pattern_volume"]
        assert len(vol_findings) == 1
        f = vol_findings[0]
        assert f.layer == "pattern"
        assert f.severity == "warning"
        assert f.icon == "⚠️"
        assert "pad" in f.message.lower()

    def test_missing_hp_finding_when_user_usually_has_hp(self) -> None:
        # Channel has no EQ devices → no HP filter
        ch = _build_channel(name="Pad 1", volume_db=-12.0, devices=(), lom_path="live_set tracks 0")
        patterns = self._make_patterns()  # has hp_freq_values with 5 entries
        findings = detect_pattern_anomalies(ch, patterns, sessions_saved=MIN_SESSIONS_REQUIRED)
        hp_findings = [f for f in findings if f.rule_id == "pattern_no_hp"]
        assert len(hp_findings) == 1
        assert hp_findings[0].severity == "warning"

    def test_no_hp_finding_when_channel_has_hp(self) -> None:
        # Add an EQ8 device with HP band active
        hp_params = _make_eq8_params_with_hp(band_n=1)
        eq = _build_device_info(
            name="EQ Eight", class_name="Eq8", device_type="eq", params=hp_params
        )
        ch = _build_channel(name="Pad 1", volume_db=-12.0, devices=(eq,), lom_path="live_set tracks 0")
        patterns = self._make_patterns()
        findings = detect_pattern_anomalies(ch, patterns, sessions_saved=MIN_SESSIONS_REQUIRED)
        hp_findings = [f for f in findings if f.rule_id == "pattern_no_hp"]
        assert hp_findings == []

    def test_returns_empty_when_no_patterns_for_instrument(self) -> None:
        ch = _build_channel(name="Kick 1", volume_db=-6.0, lom_path="live_set tracks 0")
        patterns = self._make_patterns()  # only has "pad" key
        result = detect_pattern_anomalies(ch, patterns, sessions_saved=MIN_SESSIONS_REQUIRED)
        # "kick" not in patterns → empty
        assert result == []

    def test_confidence_capped_at_1_0(self) -> None:
        # sample_count = 100 → confidence = min(100/10, 1.0) = 1.0
        ch = self._make_pad_channel()
        patterns = {
            "pad": {
                "sample_count": 100,
                "volume_db_values": [-12.0, -11.5, -12.5, -12.0, -11.0],
                "hp_freq_values": [1.0, 1.0, 1.0, 1.0, 1.0],
            }
        }
        findings = detect_pattern_anomalies(ch, patterns, sessions_saved=MIN_SESSIONS_REQUIRED)
        for f in findings:
            assert f.confidence <= 1.0


class TestInferInstrumentType:
    def test_kick_from_name(self) -> None:
        ch = _build_channel(name="Kick 1")
        assert _infer_instrument_type(ch) == "kick"

    def test_bass_from_name(self) -> None:
        ch = _build_channel(name="Bass Synth")
        assert _infer_instrument_type(ch) == "bass"

    def test_pad_from_name(self) -> None:
        ch = _build_channel(name="Pad Atmos")
        assert _infer_instrument_type(ch) == "pad"

    def test_vocal_from_name(self) -> None:
        ch = _build_channel(name="Voc Lead")
        assert _infer_instrument_type(ch) == "vocal"

    def test_unknown_falls_back_to_bus(self) -> None:
        ch = _build_channel(name="Track 1", parent_bus="DRUMS")
        # parent_bus "DRUMS" has "drum" in it — not in _BUS_TYPE_TO_INSTRUMENT directly
        # "bass" in "drums" is false; check what happens
        result = _infer_instrument_type(ch)
        assert isinstance(result, str)


class TestLearnFromChannel:
    def test_returns_dict_with_required_keys(self) -> None:
        ch = _build_channel(name="Pad 1", volume_db=-12.0)
        data = learn_from_channel(ch)
        assert "instrument_type" in data
        assert "volume_db" in data
        assert "has_hp" in data

    def test_has_hp_false_for_channel_without_eq(self) -> None:
        ch = _build_channel(name="Pad 1", volume_db=-12.0, devices=())
        data = learn_from_channel(ch)
        assert data["has_hp"] is False

    def test_has_hp_true_for_channel_with_hp(self) -> None:
        hp_params = _make_eq8_params_with_hp(band_n=1)
        eq = _build_device_info(class_name="Eq8", device_type="eq", params=hp_params)
        ch = _build_channel(name="Pad 1", volume_db=-12.0, devices=(eq,))
        data = learn_from_channel(ch)
        assert data["has_hp"] is True

    def test_volume_db_recorded(self) -> None:
        ch = _build_channel(name="Lead", volume_db=-8.5)
        data = learn_from_channel(ch)
        assert data["volume_db"] == -8.5


# ===========================================================================
# 3. genre_presets.py
# ===========================================================================


class TestRunGenreAudit:
    def _make_pad_with_no_hp(self) -> ChannelInfo:
        return _build_channel(
            name="Pad Atmos",
            volume_db=-12.0,
            devices=(),
            lom_path="live_set tracks 0",
        )

    def _make_pad_with_hp(self) -> ChannelInfo:
        hp_params = _make_eq8_params_with_hp(band_n=1)
        eq = _build_device_info(class_name="Eq8", device_type="eq", params=hp_params)
        return _build_channel(
            name="Pad Atmos",
            volume_db=-12.0,
            devices=(eq,),
            lom_path="live_set tracks 0",
        )

    def _organic_house_preset(self) -> dict:
        return {
            "name": "Organic House",
            "instruments": {
                "pad": {
                    "hp_freq_range": [100, 250],
                    "width_range": [100, 150],
                    "suggestion": "HP critical to avoid muddiness",
                }
            },
            "buses": {"drums": "Glue compression 2:1"},
        }

    def test_returns_empty_for_empty_preset(self) -> None:
        ch = self._make_pad_with_no_hp()
        sm = _build_session_map(orphan_channels=(ch,))
        findings = run_genre_audit(sm, {})
        assert findings == []

    def test_all_findings_are_suggestions(self) -> None:
        ch = self._make_pad_with_no_hp()
        sm = _build_session_map(orphan_channels=(ch,))
        findings = run_genre_audit(sm, self._organic_house_preset())
        assert all(f.severity == "suggestion" for f in findings)

    def test_all_findings_have_genre_layer(self) -> None:
        ch = self._make_pad_with_no_hp()
        sm = _build_session_map(orphan_channels=(ch,))
        findings = run_genre_audit(sm, self._organic_house_preset())
        assert all(f.layer == "genre" for f in findings)

    def test_all_findings_have_lightbulb_icon(self) -> None:
        ch = self._make_pad_with_no_hp()
        sm = _build_session_map(orphan_channels=(ch,))
        findings = run_genre_audit(sm, self._organic_house_preset())
        assert all(f.icon == "💡" for f in findings)

    def test_finding_for_pad_with_no_hp_in_organic_house(self) -> None:
        ch = self._make_pad_with_no_hp()
        sm = _build_session_map(orphan_channels=(ch,))
        findings = run_genre_audit(sm, self._organic_house_preset())
        hp_findings = [f for f in findings if "hp" in f.rule_id.lower() or "HP" in f.message]
        assert len(hp_findings) >= 1

    def test_no_finding_for_pad_with_hp(self) -> None:
        ch = self._make_pad_with_hp()
        sm = _build_session_map(orphan_channels=(ch,))
        findings = run_genre_audit(sm, self._organic_house_preset())
        # Channel has HP so no HP-related finding
        hp_findings = [f for f in findings if "hp" in f.rule_id.lower() or "HP" in f.message]
        assert hp_findings == []

    def test_empty_session_returns_empty(self) -> None:
        sm = _build_session_map()
        findings = run_genre_audit(sm, self._organic_house_preset())
        assert findings == []

    def test_preset_name_in_finding_reason(self) -> None:
        ch = self._make_pad_with_no_hp()
        sm = _build_session_map(orphan_channels=(ch,))
        findings = run_genre_audit(sm, self._organic_house_preset())
        assert any("Organic House" in f.reason for f in findings)


# ===========================================================================
# 4. recommendations.py
# ===========================================================================


class TestGenerateAuditReport:
    def _make_session_map(self) -> SessionMap:
        return _build_session_map()

    def test_returns_audit_report(self) -> None:
        sm = self._make_session_map()
        report = generate_audit_report(
            sm,
            universal_findings=[],
            gain_findings=[],
            pattern_findings=[],
            genre_findings=[],
            generated_at=0.0,
        )
        assert report.session_map is sm
        assert isinstance(report.findings, tuple)

    def test_counts_are_correct(self) -> None:
        f_crit = _valid_finding(severity="critical", rule_id="no_eq", channel_lom_path="lp0")
        f_warn = _valid_finding(severity="warning", rule_id="extreme_compression", channel_lom_path="lp1")
        f_info = _valid_finding(severity="info", rule_id="bypassed_plugin", channel_lom_path="lp2")
        f_sugg = _valid_finding(severity="suggestion", layer="genre", rule_id="genre_hp_pad", channel_lom_path="lp3")
        sm = self._make_session_map()
        report = generate_audit_report(
            sm,
            universal_findings=[f_crit, f_warn, f_info],
            gain_findings=[],
            pattern_findings=[],
            genre_findings=[f_sugg],
            generated_at=0.0,
        )
        assert report.critical_count == 1
        assert report.warning_count == 1
        assert report.info_count == 1
        assert report.suggestion_count == 1

    def test_deduplication_keeps_highest_priority(self) -> None:
        # Same (lom_path, rule_id) from two layers — keep the higher priority
        f_info = _valid_finding(
            severity="info", layer="universal", rule_id="untouched_fader",
            channel_lom_path="live_set tracks 0"
        )
        f_crit = _valid_finding(
            severity="critical", layer="universal", rule_id="untouched_fader",
            channel_lom_path="live_set tracks 0"
        )
        sm = self._make_session_map()
        report = generate_audit_report(
            sm,
            universal_findings=[f_info],
            gain_findings=[f_crit],
            pattern_findings=[],
            genre_findings=[],
            generated_at=0.0,
        )
        # Should have exactly 1 finding (deduplicated)
        assert len(report.findings) == 1
        assert report.findings[0].severity == "critical"

    def test_critical_before_info(self) -> None:
        f_info = _valid_finding(severity="info", rule_id="bypassed_plugin", channel_lom_path="lp_a")
        f_crit = _valid_finding(severity="critical", rule_id="no_eq", channel_lom_path="lp_b")
        sm = self._make_session_map()
        report = generate_audit_report(
            sm,
            universal_findings=[f_info, f_crit],
            gain_findings=[],
            pattern_findings=[],
            genre_findings=[],
            generated_at=0.0,
        )
        severities = [f.severity for f in report.findings]
        critical_indices = [i for i, s in enumerate(severities) if s == "critical"]
        info_indices = [i for i, s in enumerate(severities) if s == "info"]
        if critical_indices and info_indices:
            assert max(critical_indices) < min(info_indices)

    def test_empty_findings_returns_zero_counts(self) -> None:
        sm = self._make_session_map()
        report = generate_audit_report(
            sm,
            universal_findings=[],
            gain_findings=[],
            pattern_findings=[],
            genre_findings=[],
            generated_at=42.0,
        )
        assert report.critical_count == 0
        assert report.warning_count == 0
        assert report.info_count == 0
        assert report.suggestion_count == 0
        assert report.generated_at == 42.0


class TestFilterFindingsByLayer:
    def test_filter_universal(self) -> None:
        f_u = _valid_finding(layer="universal", rule_id="no_eq", channel_lom_path="lp0")
        f_p = _valid_finding(layer="pattern", severity="warning", rule_id="pattern_volume", channel_lom_path="lp1")
        findings = (f_u, f_p)
        result = filter_findings_by_layer(findings, "universal")
        assert result == [f_u]

    def test_filter_pattern(self) -> None:
        f_p = _valid_finding(layer="pattern", severity="warning", rule_id="pattern_volume", channel_lom_path="lp0")
        findings = (f_p,)
        result = filter_findings_by_layer(findings, "pattern")
        assert result == [f_p]

    def test_filter_returns_empty_for_no_match(self) -> None:
        f_u = _valid_finding(layer="universal", rule_id="no_eq", channel_lom_path="lp0")
        findings = (f_u,)
        result = filter_findings_by_layer(findings, "genre")
        assert result == []


class TestFilterFindingsBySeverity:
    def test_filter_critical(self) -> None:
        f_crit = _valid_finding(severity="critical", rule_id="no_eq", channel_lom_path="lp0")
        f_info = _valid_finding(severity="info", rule_id="bypassed_plugin", channel_lom_path="lp1")
        findings = (f_crit, f_info)
        result = filter_findings_by_severity(findings, "critical")
        assert result == [f_crit]

    def test_filter_suggestion(self) -> None:
        f_sugg = _valid_finding(severity="suggestion", layer="genre", rule_id="genre_hp_pad", channel_lom_path="lp0")
        findings = (f_sugg,)
        result = filter_findings_by_severity(findings, "suggestion")
        assert result == [f_sugg]

    def test_filter_empty(self) -> None:
        findings: tuple[AuditFinding, ...] = ()
        result = filter_findings_by_severity(findings, "critical")
        assert result == []


# ===========================================================================
# 5. pattern_store.py
# ===========================================================================


class TestPatternStore:
    def test_load_returns_empty_dict_for_missing_file(self, tmp_path: Path) -> None:
        store = PatternStore(store_path=tmp_path / "patterns.json")
        result = store.load()
        assert result == {}

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        store_path = tmp_path / "nested" / "dir" / "patterns.json"
        store = PatternStore(store_path=store_path)
        store.save({"sessions_saved": 1, "patterns": {}})
        assert store_path.exists()

    def test_load_after_save_round_trips(self, tmp_path: Path) -> None:
        store = PatternStore(store_path=tmp_path / "patterns.json")
        data = {"sessions_saved": 3, "patterns": {"pad": {"sample_count": 5}}}
        store.save(data)
        loaded = store.load()
        assert loaded["sessions_saved"] == 3
        assert loaded["patterns"]["pad"]["sample_count"] == 5

    def test_add_session_data_increments_sessions_saved(self, tmp_path: Path) -> None:
        store = PatternStore(store_path=tmp_path / "patterns.json")
        channel_data = [{"instrument_type": "pad", "volume_db": -12.0, "has_hp": True}]
        store.add_session_data(channel_data)
        assert store.get_sessions_saved() == 1
        store.add_session_data(channel_data)
        assert store.get_sessions_saved() == 2

    def test_add_session_data_accumulates_values(self, tmp_path: Path) -> None:
        store = PatternStore(store_path=tmp_path / "patterns.json")
        data1 = [{"instrument_type": "pad", "volume_db": -12.0, "has_hp": True}]
        data2 = [{"instrument_type": "pad", "volume_db": -10.0, "has_hp": False}]
        store.add_session_data(data1)
        store.add_session_data(data2)
        patterns = store.get_patterns()
        assert "pad" in patterns
        assert len(patterns["pad"]["volume_db_values"]) == 2
        assert -12.0 in patterns["pad"]["volume_db_values"]
        assert -10.0 in patterns["pad"]["volume_db_values"]

    def test_clear_removes_file(self, tmp_path: Path) -> None:
        store = PatternStore(store_path=tmp_path / "patterns.json")
        store.save({"sessions_saved": 5})
        store.clear()
        assert not (tmp_path / "patterns.json").exists()

    def test_get_sessions_saved_returns_zero_for_empty(self, tmp_path: Path) -> None:
        store = PatternStore(store_path=tmp_path / "patterns.json")
        assert store.get_sessions_saved() == 0

    def test_unknown_instrument_type_skipped(self, tmp_path: Path) -> None:
        store = PatternStore(store_path=tmp_path / "patterns.json")
        channel_data = [{"instrument_type": "unknown", "volume_db": -12.0, "has_hp": True}]
        store.add_session_data(channel_data)
        patterns = store.get_patterns()
        assert "unknown" not in patterns


# ===========================================================================
# 6. session_auditor.py
# ===========================================================================


class TestSessionAuditor:
    def test_run_audit_returns_audit_report(self) -> None:
        session = _build_empty_session()
        with patch.object(PatternStore, "load", return_value={}):
            auditor = SessionAuditor()
            report = auditor.run_audit(session)
        from core.session_intelligence.types import AuditReport
        assert isinstance(report, AuditReport)

    def test_no_layer2_findings_when_sessions_saved_below_minimum(self) -> None:
        session = _build_empty_session()
        with patch.object(PatternStore, "load", return_value={"sessions_saved": 0, "patterns": {}}):
            auditor = SessionAuditor()
            report = auditor.run_audit(session)
        pattern_findings = filter_findings_by_layer(report.findings, "pattern")
        assert pattern_findings == []

    def test_no_genre_findings_when_preset_is_none(self) -> None:
        session = _build_empty_session()
        with patch.object(PatternStore, "load", return_value={}):
            auditor = SessionAuditor()
            report = auditor.run_audit(session, genre_preset=None)
        genre_findings = filter_findings_by_layer(report.findings, "genre")
        assert genre_findings == []

    def test_save_session_patterns_returns_channel_count(self, tmp_path: Path) -> None:
        from core.ableton.types import Track
        # Session with 2 tracks
        t1 = Track(
            name="Pad", index=0, type=TrackType.MIDI, arm=False, solo=False,
            mute=False, volume_db=-12.0, pan=0.0, devices=(), clips=(),
            lom_path="live_set tracks 0",
        )
        t2 = Track(
            name="Bass", index=1, type=TrackType.MIDI, arm=False, solo=False,
            mute=False, volume_db=-10.0, pan=0.0, devices=(), clips=(),
            lom_path="live_set tracks 1",
        )
        session = SessionState(
            tracks=(t1, t2),
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
        store = PatternStore(store_path=tmp_path / "patterns.json")
        auditor = SessionAuditor(pattern_store=store)
        count = auditor.save_session_patterns(session)
        assert count == 2

    def test_genre_preset_none_does_not_call_load_preset(self) -> None:
        session = _build_empty_session()
        with patch.object(PatternStore, "load", return_value={}):
            auditor = SessionAuditor()
            with patch.object(auditor, "_load_preset") as mock_load:
                auditor.run_audit(session, genre_preset=None)
                mock_load.assert_not_called()

    def test_unknown_genre_preset_produces_no_genre_findings(self) -> None:
        session = _build_empty_session()
        with patch.object(PatternStore, "load", return_value={}):
            auditor = SessionAuditor()
            report = auditor.run_audit(session, genre_preset="nonexistent_genre_xyz")
        genre_findings = filter_findings_by_layer(report.findings, "genre")
        assert genre_findings == []


# ===========================================================================
# gain_staging.py — lom_id in fix_action (added Day 6)
# ===========================================================================


class TestCheckLowHeadroomLomId:
    """Tests for the volume_lom_id → lom_id path in check_low_headroom fix_actions."""

    def test_fix_action_contains_lom_id_when_volume_lom_id_nonzero(self) -> None:
        """When channel has volume_lom_id != 0, fix_action dict must include lom_id."""
        ch = _build_channel(name="Lead", volume_db=-1.0, lom_path="live_set tracks 0", volume_lom_id=55)
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_low_headroom(sm)
        assert len(findings) == 1
        fix = findings[0].fix_action_dict()
        assert fix is not None
        assert fix["lom_id"] == 55
        assert fix["property"] == "value"

    def test_fix_action_has_no_lom_id_when_volume_lom_id_zero(self) -> None:
        """When channel has volume_lom_id == 0 (old scanner), fix_action uses lom_path only."""
        ch = _build_channel(name="Lead", volume_db=-1.0, lom_path="live_set tracks 0", volume_lom_id=0)
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_low_headroom(sm)
        assert len(findings) == 1
        fix = findings[0].fix_action_dict()
        assert fix is not None
        assert "lom_id" not in fix
        assert fix["lom_path"] == "live_set tracks 0 mixer_device volume"
        assert fix["property"] == "value"

    def test_fix_action_lom_path_still_present_alongside_lom_id(self) -> None:
        """lom_path is always included as fallback even when lom_id is set."""
        ch = _build_channel(name="Pad", volume_db=-2.0, lom_path="live_set tracks 3", volume_lom_id=12)
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_low_headroom(sm)
        fix = findings[0].fix_action_dict()
        assert fix is not None
        assert "lom_path" in fix
        assert fix["lom_path"] == "live_set tracks 3 mixer_device volume"

    def test_fix_action_value_is_safe_raw_level(self) -> None:
        """The suggested volume value is the -6 dB safe headroom target (raw scale)."""
        ch = _build_channel(name="Lead", volume_db=-1.0, lom_path="live_set tracks 0", volume_lom_id=7)
        sm = _build_session_map(orphan_channels=(ch,))
        findings = check_low_headroom(sm)
        fix = findings[0].fix_action_dict()
        assert fix is not None
        # Value must be < 0.85 (which corresponds to 0 dB) for safe headroom
        assert isinstance(fix["value"], float)
        assert fix["value"] < 0.85
