"""tests/test_session_intelligence_day3.py — Day 3: API routes + MCP tools.

Tests cover:
  - api/routes/session_intelligence.py (4 endpoints)
  - tools/music/audit_session.py
  - tools/music/get_my_patterns.py
  - tools/music/save_session_patterns.py
  - tools/music/apply_audit_fix.py
  - tools/music/set_genre_preset.py
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.ableton.types import SessionState
from core.session_intelligence.types import (
    AuditFinding,
    AuditReport,
    SessionMap,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_minimal_session() -> SessionState:
    """Build a minimal SessionState for testing (no real Ableton needed)."""
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
    )


def _make_minimal_finding(
    *,
    layer: str = "universal",
    severity: str = "warning",
    rule_id: str = "no_eq",
    channel_name: str = "Pad Main",
    fix_action: tuple | None = None,
) -> AuditFinding:
    """Build a minimal AuditFinding for testing."""
    return AuditFinding(
        layer=layer,
        severity=severity,
        icon="[!]",
        channel_name=channel_name,
        channel_lom_path="live_set tracks 0",
        device_name=None,
        rule_id=rule_id,
        message="Test finding",
        reason="Test reason",
        confidence=1.0,
        fix_action=fix_action,
    )


def _make_minimal_session_map() -> SessionMap:
    """Build a minimal SessionMap for testing."""
    return SessionMap(
        buses=(),
        orphan_channels=(),
        return_channels=(),
        master_channel=None,
        all_channels=(),
        mapped_at=time.time(),
    )


def _make_minimal_report(findings: tuple = ()) -> AuditReport:
    """Build a minimal AuditReport for testing."""
    critical = sum(1 for f in findings if f.severity == "critical")
    warning = sum(1 for f in findings if f.severity == "warning")
    info = sum(1 for f in findings if f.severity == "info")
    suggestion = sum(1 for f in findings if f.severity == "suggestion")
    return AuditReport(
        session_map=_make_minimal_session_map(),
        findings=findings,
        critical_count=critical,
        warning_count=warning,
        suggestion_count=suggestion,
        info_count=info,
        generated_at=time.time(),
    )


# ---------------------------------------------------------------------------
# API route tests
# ---------------------------------------------------------------------------


class TestAPIAuditEndpoint:
    """Tests for POST /session/audit."""

    def _get_client(self) -> TestClient:
        from fastapi import FastAPI

        from api.routes.session_intelligence import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_audit_returns_200_with_mocked_session(self) -> None:
        """Happy path: mock bridge + auditor, expect 200 with findings."""
        client = self._get_client()
        mock_session = _make_minimal_session()
        mock_finding = _make_minimal_finding()
        mock_report = _make_minimal_report((mock_finding,))

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.return_value = mock_session
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        mock_auditor_instance = MagicMock()
        mock_auditor_instance.run_audit.return_value = mock_report

        with (
            patch("api.routes.session_intelligence.AbletonBridge", mock_bridge_cls),
            patch("api.routes.session_intelligence._get_auditor", return_value=mock_auditor_instance),
        ):
            resp = client.post("/session/audit", json={})

        assert resp.status_code == 200
        data = resp.json()
        assert "findings" in data
        assert "critical_count" in data
        assert data["warning_count"] == 1

    def test_audit_with_genre_preset(self) -> None:
        """Verify genre_preset is forwarded to run_audit."""
        client = self._get_client()
        mock_session = _make_minimal_session()
        mock_report = _make_minimal_report()

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.return_value = mock_session
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        mock_auditor_instance = MagicMock()
        mock_auditor_instance.run_audit.return_value = mock_report

        with (
            patch("api.routes.session_intelligence.AbletonBridge", mock_bridge_cls),
            patch("api.routes.session_intelligence._get_auditor", return_value=mock_auditor_instance),
        ):
            resp = client.post("/session/audit", json={"genre_preset": "organic_house"})

        assert resp.status_code == 200
        mock_auditor_instance.run_audit.assert_called_once_with(
            mock_session, genre_preset="organic_house"
        )

    def test_audit_connection_error_returns_422(self) -> None:
        """Ableton not running -> 422."""
        client = self._get_client()

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.side_effect = ConnectionError("ALS not running")
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        with patch("api.routes.session_intelligence.AbletonBridge", mock_bridge_cls):
            resp = client.post("/session/audit", json={})

        assert resp.status_code == 422

    def test_audit_serializes_fix_action(self) -> None:
        """Findings with fix_action should serialize the dict correctly."""
        client = self._get_client()
        mock_session = _make_minimal_session()
        fix = (
            ("lom_path", "live_set tracks 0 devices 1"),
            ("property", "is_active"),
            ("value", 1),
        )
        finding_with_fix = _make_minimal_finding(fix_action=fix)
        mock_report = _make_minimal_report((finding_with_fix,))

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.return_value = mock_session
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        mock_auditor_instance = MagicMock()
        mock_auditor_instance.run_audit.return_value = mock_report

        with (
            patch("api.routes.session_intelligence.AbletonBridge", mock_bridge_cls),
            patch("api.routes.session_intelligence._get_auditor", return_value=mock_auditor_instance),
        ):
            resp = client.post("/session/audit", json={})

        assert resp.status_code == 200
        finding_data = resp.json()["findings"][0]
        assert finding_data["fix_action"] is not None
        assert finding_data["fix_action"]["lom_path"] == "live_set tracks 0 devices 1"

    def test_audit_no_fix_action_is_null(self) -> None:
        """Findings without fix_action should serialize as null."""
        client = self._get_client()
        mock_session = _make_minimal_session()
        finding_no_fix = _make_minimal_finding(fix_action=None)
        mock_report = _make_minimal_report((finding_no_fix,))

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.return_value = mock_session
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        mock_auditor_instance = MagicMock()
        mock_auditor_instance.run_audit.return_value = mock_report

        with (
            patch("api.routes.session_intelligence.AbletonBridge", mock_bridge_cls),
            patch("api.routes.session_intelligence._get_auditor", return_value=mock_auditor_instance),
        ):
            resp = client.post("/session/audit", json={})

        assert resp.status_code == 200
        finding_data = resp.json()["findings"][0]
        assert finding_data["fix_action"] is None

    def test_audit_report_structure(self) -> None:
        """Verify full report structure keys are present."""
        client = self._get_client()
        mock_session = _make_minimal_session()
        mock_report = _make_minimal_report()

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.return_value = mock_session
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        mock_auditor_instance = MagicMock()
        mock_auditor_instance.run_audit.return_value = mock_report

        with (
            patch("api.routes.session_intelligence.AbletonBridge", mock_bridge_cls),
            patch("api.routes.session_intelligence._get_auditor", return_value=mock_auditor_instance),
        ):
            resp = client.post("/session/audit", json={})

        assert resp.status_code == 200
        data = resp.json()
        for key in ("generated_at", "critical_count", "warning_count", "suggestion_count", "info_count", "findings", "session_map"):
            assert key in data, f"Missing key: {key}"


class TestAPIPatternsEndpoints:
    """Tests for GET /session/patterns and POST /session/patterns/save."""

    def _get_client(self) -> TestClient:
        from fastapi import FastAPI

        from api.routes.session_intelligence import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_get_patterns_empty(self) -> None:
        """Empty pattern store returns empty dict + sessions_saved=0."""
        client = self._get_client()

        mock_store = MagicMock()
        mock_store.load.return_value = {}

        with patch("api.routes.session_intelligence._get_pattern_store", return_value=mock_store):
            resp = client.get("/session/patterns")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sessions_saved"] == 0
        assert data["patterns"] == {}

    def test_get_patterns_with_data(self) -> None:
        """Pattern store with data returns the patterns dict."""
        client = self._get_client()
        patterns_data = {
            "sessions_saved": 5,
            "patterns": {"pad": {"sample_count": 10, "volume_db_values": [-12.0, -11.5]}},
        }

        mock_store = MagicMock()
        mock_store.load.return_value = patterns_data

        with patch("api.routes.session_intelligence._get_pattern_store", return_value=mock_store):
            resp = client.get("/session/patterns")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sessions_saved"] == 5
        assert "pad" in data["patterns"]

    def test_save_patterns_success(self) -> None:
        """Happy path: save patterns returns channels_learned and sessions_saved."""
        client = self._get_client()
        mock_session = _make_minimal_session()

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.return_value = mock_session
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        mock_auditor_instance = MagicMock()
        mock_auditor_instance.save_session_patterns.return_value = 7

        mock_store_instance = MagicMock()
        mock_store_instance.get_sessions_saved.return_value = 1

        with (
            patch("api.routes.session_intelligence.AbletonBridge", mock_bridge_cls),
            patch("api.routes.session_intelligence._get_auditor", return_value=mock_auditor_instance),
            patch("api.routes.session_intelligence._get_pattern_store", return_value=mock_store_instance),
        ):
            resp = client.post("/session/patterns/save")

        assert resp.status_code == 200
        data = resp.json()
        assert data["channels_learned"] == 7
        assert data["sessions_saved"] == 1

    def test_save_patterns_connection_error(self) -> None:
        """Ableton not running -> 422."""
        client = self._get_client()

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.side_effect = ConnectionError("no ALS")
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        with patch("api.routes.session_intelligence.AbletonBridge", mock_bridge_cls):
            resp = client.post("/session/patterns/save")

        assert resp.status_code == 422


class TestAPIApplyFixEndpoint:
    """Tests for POST /session/apply-fix."""

    def _get_client(self) -> TestClient:
        from fastapi import FastAPI

        from api.routes.session_intelligence import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_apply_fix_success(self) -> None:
        """Happy path: send a fix command, get ack back."""
        client = self._get_client()
        fix_payload = {
            "lom_path": "live_set tracks 2 devices 1",
            "property": "is_active",
            "value": 1,
        }

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.send_command.return_value = {"status": "ok"}
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        with patch("api.routes.session_intelligence.AbletonBridge", mock_bridge_cls):
            resp = client.post("/session/apply-fix", json=fix_payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["applied"] is True
        assert data["lom_path"] == "live_set tracks 2 devices 1"

    def test_apply_fix_missing_lom_path(self) -> None:
        """Missing lom_path -> 422 (pydantic validation)."""
        client = self._get_client()
        resp = client.post(
            "/session/apply-fix",
            json={"property": "is_active", "value": 1},
        )
        assert resp.status_code == 422

    def test_apply_fix_missing_property(self) -> None:
        """Missing property -> 422 (pydantic validation)."""
        client = self._get_client()
        resp = client.post(
            "/session/apply-fix",
            json={"lom_path": "live_set tracks 0", "value": 1},
        )
        assert resp.status_code == 422

    def test_apply_fix_connection_error(self) -> None:
        """Ableton not running -> 422."""
        client = self._get_client()
        fix_payload = {
            "lom_path": "live_set tracks 0 devices 0",
            "property": "is_active",
            "value": 1,
        }

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.send_command.side_effect = ConnectionError("no ALS")
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        with patch("api.routes.session_intelligence.AbletonBridge", mock_bridge_cls):
            resp = client.post("/session/apply-fix", json=fix_payload)

        assert resp.status_code == 422

    def test_apply_fix_returns_ack(self) -> None:
        """The ack from bridge is included in the response."""
        client = self._get_client()
        fix_payload = {
            "lom_path": "live_set tracks 1",
            "property": "volume",
            "value": 0.8,
            "description": "Test fix",
        }

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.send_command.return_value = {"status": "ok", "ts": 1234}
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        with patch("api.routes.session_intelligence.AbletonBridge", mock_bridge_cls):
            resp = client.post("/session/apply-fix", json=fix_payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["ack"]["status"] == "ok"

    def test_apply_fix_with_lom_id_only(self) -> None:
        """lom_id alone (no lom_path) is sufficient — integer ID navigation."""
        client = self._get_client()
        fix_payload = {
            "lom_path": "",
            "lom_id": 55,
            "property": "value",
            "value": 0.757,
        }

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.send_command.return_value = {"status": "ok"}
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        with patch("api.routes.session_intelligence.AbletonBridge", mock_bridge_cls):
            resp = client.post("/session/apply-fix", json=fix_payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["applied"] is True
        assert data["lom_id"] == 55

    def test_apply_fix_missing_both_lom_path_and_lom_id_returns_422(self) -> None:
        """When neither lom_path nor lom_id is provided, the endpoint returns 422."""
        client = self._get_client()
        fix_payload = {
            "property": "value",
            "value": 0.5,
        }

        mock_bridge_instance = MagicMock()
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        with patch("api.routes.session_intelligence.AbletonBridge", mock_bridge_cls):
            resp = client.post("/session/apply-fix", json=fix_payload)

        assert resp.status_code == 422

    def test_apply_fix_lom_id_forwarded_to_lom_command(self) -> None:
        """lom_id from the request is forwarded to LOMCommand and bridge."""
        from core.ableton.types import LOMCommand

        client = self._get_client()
        fix_payload = {
            "lom_path": "live_set tracks 0 mixer_device volume",
            "lom_id": 42,
            "property": "value",
            "value": 0.757,
        }

        captured_cmd: list[LOMCommand] = []

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.send_command.side_effect = lambda cmd: (
            captured_cmd.append(cmd) or {"status": "ok"}
        )
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        with patch("api.routes.session_intelligence.AbletonBridge", mock_bridge_cls):
            resp = client.post("/session/apply-fix", json=fix_payload)

        assert resp.status_code == 200
        assert len(captured_cmd) == 1
        cmd = captured_cmd[0]
        assert cmd.lom_id == 42
        assert cmd.property == "value"
        assert cmd.value == 0.757
        # to_dict() must include lom_id when non-zero
        d = cmd.to_dict()
        assert d["lom_id"] == 42


# ---------------------------------------------------------------------------
# MCP tool tests
# ---------------------------------------------------------------------------


class TestAuditSessionTool:
    """Tests for tools/music/audit_session.py."""

    def test_audit_session_success(self) -> None:
        """Happy path: mock bridge + auditor, verify structured output."""
        from tools.music.audit_session import AuditSession

        tool = AuditSession()
        mock_session = _make_minimal_session()
        finding = _make_minimal_finding(severity="critical", rule_id="no_eq")
        mock_report = _make_minimal_report((finding,))

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.return_value = mock_session
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        mock_auditor_instance = MagicMock()
        mock_auditor_instance.run_audit.return_value = mock_report
        mock_auditor_cls = MagicMock(return_value=mock_auditor_instance)

        with (
            patch("tools.music.audit_session.AbletonBridge", mock_bridge_cls),
            patch("tools.music.audit_session.SessionAuditor", mock_auditor_cls),
        ):
            result = tool(genre_preset="", force_refresh=False)

        assert result.success is True
        assert result.data is not None
        assert result.data["critical_count"] == 1
        assert "findings_by_layer" in result.data
        assert len(result.data["findings_by_layer"]["universal"]) == 1

    def test_audit_session_severity_filter(self) -> None:
        """severity_filter='critical' should exclude warning findings."""
        from tools.music.audit_session import AuditSession

        tool = AuditSession()
        mock_session = _make_minimal_session()
        crit = _make_minimal_finding(severity="critical", rule_id="no_eq")
        warn = _make_minimal_finding(severity="warning", rule_id="no_highpass")
        mock_report = _make_minimal_report((crit, warn))

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.return_value = mock_session
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        mock_auditor_instance = MagicMock()
        mock_auditor_instance.run_audit.return_value = mock_report
        mock_auditor_cls = MagicMock(return_value=mock_auditor_instance)

        with (
            patch("tools.music.audit_session.AbletonBridge", mock_bridge_cls),
            patch("tools.music.audit_session.SessionAuditor", mock_auditor_cls),
        ):
            result = tool(severity_filter="critical")

        assert result.success is True
        assert result.data["total_findings"] == 1
        # Only critical finding remains
        assert result.data["findings_by_layer"]["universal"][0]["rule"] == "no_eq"

    def test_audit_session_connection_error(self) -> None:
        """ConnectionError from bridge -> ToolResult with success=False."""
        from tools.music.audit_session import AuditSession

        tool = AuditSession()

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.side_effect = ConnectionError("no ALS")
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        with patch("tools.music.audit_session.AbletonBridge", mock_bridge_cls):
            result = tool()

        assert result.success is False
        assert "no ALS" in result.error

    def test_audit_session_genre_preset_passed(self) -> None:
        """genre_preset is forwarded to SessionAuditor.run_audit."""
        from tools.music.audit_session import AuditSession

        tool = AuditSession()
        mock_session = _make_minimal_session()
        mock_report = _make_minimal_report()

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.return_value = mock_session
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        mock_auditor_instance = MagicMock()
        mock_auditor_instance.run_audit.return_value = mock_report
        mock_auditor_cls = MagicMock(return_value=mock_auditor_instance)

        with (
            patch("tools.music.audit_session.AbletonBridge", mock_bridge_cls),
            patch("tools.music.audit_session.SessionAuditor", mock_auditor_cls),
        ):
            tool(genre_preset="organic_house")

        mock_auditor_instance.run_audit.assert_called_once_with(
            mock_session, genre_preset="organic_house"
        )

    def test_audit_session_empty_findings(self) -> None:
        """Empty session with no findings returns success with empty grouped dict."""
        from tools.music.audit_session import AuditSession

        tool = AuditSession()
        mock_session = _make_minimal_session()
        mock_report = _make_minimal_report(())

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.return_value = mock_session
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        mock_auditor_instance = MagicMock()
        mock_auditor_instance.run_audit.return_value = mock_report
        mock_auditor_cls = MagicMock(return_value=mock_auditor_instance)

        with (
            patch("tools.music.audit_session.AbletonBridge", mock_bridge_cls),
            patch("tools.music.audit_session.SessionAuditor", mock_auditor_cls),
        ):
            result = tool()

        assert result.success is True
        assert result.data["total_findings"] == 0


class TestGetMyPatternsTool:
    """Tests for tools/music/get_my_patterns.py."""

    def test_empty_store_returns_layer2_inactive(self) -> None:
        """Empty store -> layer_2_active is False."""
        from tools.music.get_my_patterns import GetMyPatterns

        tool = GetMyPatterns()

        mock_store_instance = MagicMock()
        mock_store_instance.load.return_value = {}
        mock_store_cls = MagicMock(return_value=mock_store_instance)

        with patch("tools.music.get_my_patterns.PatternStore", mock_store_cls):
            result = tool()

        assert result.success is True
        assert result.data["sessions_saved"] == 0
        assert result.data["layer_2_active"] is False

    def test_store_with_3_sessions_activates_layer2(self) -> None:
        """3 sessions saved -> layer_2_active is True."""
        from tools.music.get_my_patterns import GetMyPatterns

        tool = GetMyPatterns()
        data = {
            "sessions_saved": 3,
            "patterns": {"pad": {"sample_count": 9}},
        }

        mock_store_instance = MagicMock()
        mock_store_instance.load.return_value = data
        mock_store_cls = MagicMock(return_value=mock_store_instance)

        with patch("tools.music.get_my_patterns.PatternStore", mock_store_cls):
            result = tool()

        assert result.success is True
        assert result.data["layer_2_active"] is True
        assert "pad" in result.data["patterns"]

    def test_instrument_filter(self) -> None:
        """instrument_type filter keeps only matching instrument types."""
        from tools.music.get_my_patterns import GetMyPatterns

        tool = GetMyPatterns()
        data = {
            "sessions_saved": 5,
            "patterns": {
                "pad": {"sample_count": 10},
                "kick": {"sample_count": 8},
                "bass": {"sample_count": 6},
            },
        }

        mock_store_instance = MagicMock()
        mock_store_instance.load.return_value = data
        mock_store_cls = MagicMock(return_value=mock_store_instance)

        with patch("tools.music.get_my_patterns.PatternStore", mock_store_cls):
            result = tool(instrument_type="pad")

        assert result.success is True
        assert "pad" in result.data["patterns"]
        assert "kick" not in result.data["patterns"]

    def test_more_than_3_sessions_layer2_active(self) -> None:
        """5 sessions saved -> layer_2_active is True."""
        from tools.music.get_my_patterns import GetMyPatterns

        tool = GetMyPatterns()
        data = {"sessions_saved": 5, "patterns": {}}

        mock_store_instance = MagicMock()
        mock_store_instance.load.return_value = data
        mock_store_cls = MagicMock(return_value=mock_store_instance)

        with patch("tools.music.get_my_patterns.PatternStore", mock_store_cls):
            result = tool()

        assert result.data["layer_2_active"] is True


class TestSaveSessionPatternsTool:
    """Tests for tools/music/save_session_patterns.py."""

    def test_save_success(self) -> None:
        """Happy path: save patterns returns channels_learned and sessions_saved."""
        from tools.music.save_session_patterns import SaveSessionPatterns

        tool = SaveSessionPatterns()
        mock_session = _make_minimal_session()

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.return_value = mock_session
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        mock_store_instance = MagicMock()
        mock_store_instance.get_sessions_saved.return_value = 1
        mock_store_cls = MagicMock(return_value=mock_store_instance)

        mock_auditor_instance = MagicMock()
        mock_auditor_instance.save_session_patterns.return_value = 5
        mock_auditor_cls = MagicMock(return_value=mock_auditor_instance)

        with (
            patch("tools.music.save_session_patterns.AbletonBridge", mock_bridge_cls),
            patch("tools.music.save_session_patterns.PatternStore", mock_store_cls),
            patch("tools.music.save_session_patterns.SessionAuditor", mock_auditor_cls),
        ):
            result = tool()

        assert result.success is True
        assert result.data["channels_learned"] == 5
        assert result.data["sessions_saved"] == 1
        assert result.data["layer_2_active"] is False

    def test_save_connection_error(self) -> None:
        """Ableton not running -> ToolResult with success=False."""
        from tools.music.save_session_patterns import SaveSessionPatterns

        tool = SaveSessionPatterns()

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.side_effect = ConnectionError("no ALS")
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        with patch("tools.music.save_session_patterns.AbletonBridge", mock_bridge_cls):
            result = tool()

        assert result.success is False

    def test_save_3rd_session_activates_layer2(self) -> None:
        """After 3rd save, layer_2_active becomes True."""
        from tools.music.save_session_patterns import SaveSessionPatterns

        tool = SaveSessionPatterns()
        mock_session = _make_minimal_session()

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.return_value = mock_session
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        mock_store_instance = MagicMock()
        mock_store_instance.get_sessions_saved.return_value = 3
        mock_store_cls = MagicMock(return_value=mock_store_instance)

        mock_auditor_instance = MagicMock()
        mock_auditor_instance.save_session_patterns.return_value = 4
        mock_auditor_cls = MagicMock(return_value=mock_auditor_instance)

        with (
            patch("tools.music.save_session_patterns.AbletonBridge", mock_bridge_cls),
            patch("tools.music.save_session_patterns.PatternStore", mock_store_cls),
            patch("tools.music.save_session_patterns.SessionAuditor", mock_auditor_cls),
        ):
            result = tool()

        assert result.data["layer_2_active"] is True
        assert "Layer 2 now active" in result.data["status"]

    def test_save_channels_learned_count(self) -> None:
        """channels_learned matches what SessionAuditor reports."""
        from tools.music.save_session_patterns import SaveSessionPatterns

        tool = SaveSessionPatterns()
        mock_session = _make_minimal_session()

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.get_session.return_value = mock_session
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        mock_store_instance = MagicMock()
        mock_store_instance.get_sessions_saved.return_value = 2
        mock_store_cls = MagicMock(return_value=mock_store_instance)

        mock_auditor_instance = MagicMock()
        mock_auditor_instance.save_session_patterns.return_value = 12
        mock_auditor_cls = MagicMock(return_value=mock_auditor_instance)

        with (
            patch("tools.music.save_session_patterns.AbletonBridge", mock_bridge_cls),
            patch("tools.music.save_session_patterns.PatternStore", mock_store_cls),
            patch("tools.music.save_session_patterns.SessionAuditor", mock_auditor_cls),
        ):
            result = tool()

        assert result.data["channels_learned"] == 12


class TestApplyAuditFixTool:
    """Tests for tools/music/apply_audit_fix.py."""

    def test_apply_fix_success(self) -> None:
        """Happy path: send a fix command, get ack back."""
        from tools.music.apply_audit_fix import ApplyAuditFix

        tool = ApplyAuditFix()

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.send_command.return_value = {"status": "ok"}
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        with patch("tools.music.apply_audit_fix.AbletonBridge", mock_bridge_cls):
            result = tool(
                lom_path="live_set tracks 2 devices 1",
                property="is_active",
                value=1,
            )

        assert result.success is True
        assert result.data["applied"] is True

    def test_apply_fix_dry_run(self) -> None:
        """dry_run=True returns planned command without calling bridge."""
        from tools.music.apply_audit_fix import ApplyAuditFix

        tool = ApplyAuditFix()
        result = tool(
            lom_path="live_set tracks 0 devices 0",
            property="value",
            value="0.5",
            dry_run=True,
        )
        assert result.success is True
        assert result.data["dry_run"] is True
        assert result.data["planned_command"]["lom_path"] == "live_set tracks 0 devices 0"

    def test_apply_fix_auto_converts_string_number(self) -> None:
        """String '0.75' should be auto-converted to float."""
        from tools.music.apply_audit_fix import ApplyAuditFix

        tool = ApplyAuditFix()

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.send_command.return_value = {}
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        with patch("tools.music.apply_audit_fix.AbletonBridge", mock_bridge_cls):
            result = tool(
                lom_path="live_set tracks 0",
                property="value",
                value="0.75",
            )

        assert result.success is True
        assert result.data["value"] == pytest.approx(0.75)

    def test_apply_fix_missing_lom_path(self) -> None:
        """Empty lom_path -> ToolResult with success=False."""
        from tools.music.apply_audit_fix import ApplyAuditFix

        tool = ApplyAuditFix()
        result = tool(lom_path="", property="value", value=1)
        assert result.success is False
        assert "lom_path" in result.error

    def test_apply_fix_connection_error(self) -> None:
        """ConnectionError from bridge -> ToolResult with success=False."""
        from tools.music.apply_audit_fix import ApplyAuditFix

        tool = ApplyAuditFix()

        mock_bridge_instance = MagicMock()
        mock_bridge_instance.send_command.side_effect = ConnectionError("no ALS")
        mock_bridge_cls = MagicMock(return_value=mock_bridge_instance)

        with patch("tools.music.apply_audit_fix.AbletonBridge", mock_bridge_cls):
            result = tool(
                lom_path="live_set tracks 0",
                property="value",
                value=1,
            )

        assert result.success is False

    def test_apply_fix_integer_string(self) -> None:
        """String '42' should be auto-converted to int."""
        from tools.music.apply_audit_fix import ApplyAuditFix

        tool = ApplyAuditFix()
        result = tool(
            lom_path="live_set tracks 0",
            property="value",
            value="42",
            dry_run=True,
        )
        assert result.success is True
        assert result.data["planned_command"]["value"] == 42
        assert isinstance(result.data["planned_command"]["value"], int)


class TestSetGenrePresetTool:
    """Tests for tools/music/set_genre_preset.py."""

    def test_list_all_presets(self) -> None:
        """No genre argument -> list all available presets."""
        from tools.music.set_genre_preset import SetGenrePreset

        tool = SetGenrePreset()
        result = tool()

        assert result.success is True
        assert "available_presets" in result.data
        assert isinstance(result.data["available_presets"], list)

    def test_list_presets_includes_known_presets(self) -> None:
        """The genre_presets dir has organic_house, techno, deep_house, melodic_techno."""
        from tools.music.set_genre_preset import SetGenrePreset

        tool = SetGenrePreset()
        result = tool()

        assert result.success is True
        presets = result.data["available_presets"]
        # At least one of the known presets should be present
        assert any(p in presets for p in ["organic_house", "techno", "deep_house", "melodic_techno"])

    def test_preview_organic_house(self) -> None:
        """Preview organic_house returns preset data."""
        from tools.music.set_genre_preset import SetGenrePreset

        tool = SetGenrePreset()
        result = tool(genre="organic_house")

        assert result.success is True
        assert result.data["preset_name"] == "organic_house"
        assert "preset" in result.data

    def test_invalid_genre_returns_error(self) -> None:
        """Unknown genre -> success=False with 'not found' in error."""
        from tools.music.set_genre_preset import SetGenrePreset

        tool = SetGenrePreset()
        result = tool(genre="death_metal_2099")

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_genre_name_normalization(self) -> None:
        """'organic house' with space normalizes to 'organic_house'."""
        from tools.music.set_genre_preset import SetGenrePreset

        tool = SetGenrePreset()
        result_space = tool(genre="organic house")
        result_underscore = tool(genre="organic_house")

        assert result_space.success is True
        assert result_underscore.success is True
        assert result_space.data["preset_name"] == result_underscore.data["preset_name"]

    def test_usage_hint_in_list_response(self) -> None:
        """List response includes usage hint."""
        from tools.music.set_genre_preset import SetGenrePreset

        tool = SetGenrePreset()
        result = tool()

        assert "usage" in result.data
