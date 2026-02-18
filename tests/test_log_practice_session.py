"""
Tests for log_practice_session tool.

Uses tmp_path for JSON storage to avoid polluting data/ directory.
All tests are deterministic and isolated.
"""

import json
from datetime import UTC

from tools.music.log_practice_session import (
    LogPracticeSession,
    _extract_tags,
    _find_practice_gaps,
)

# ---------------------------------------------------------------------------
# Tool properties
# ---------------------------------------------------------------------------


class TestLogPracticeSessionProperties:
    """Test tool interface contract."""

    def test_tool_name(self):
        """Tool name must be exactly 'log_practice_session'."""
        tool = LogPracticeSession()
        assert tool.name == "log_practice_session"

    def test_description_mentions_key_concepts(self):
        """Description should mention session, topic, gaps."""
        tool = LogPracticeSession()
        desc = tool.description.lower()
        assert "session" in desc
        assert "topic" in desc
        assert "gap" in desc

    def test_has_three_parameters(self):
        """Tool should expose topic, duration_minutes, notes."""
        tool = LogPracticeSession()
        names = [p.name for p in tool.parameters]
        assert "topic" in names
        assert "duration_minutes" in names
        assert "notes" in names

    def test_notes_is_optional(self):
        """notes parameter should be optional with empty string default."""
        tool = LogPracticeSession()
        notes_param = next(p for p in tool.parameters if p.name == "notes")
        assert notes_param.required is False
        assert notes_param.default == ""

    def test_topic_and_duration_are_required(self):
        """topic and duration_minutes should be required."""
        tool = LogPracticeSession()
        required = {p.name for p in tool.parameters if p.required}
        assert "topic" in required
        assert "duration_minutes" in required


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestLogPracticeSessionHappyPath:
    """Test successful session logging."""

    def test_basic_session_logged(self, tmp_path):
        """Should log a session and return session_id."""
        storage = tmp_path / "sessions.json"
        tool = LogPracticeSession(sessions_file=storage)

        result = tool(topic="bass design", duration_minutes=60)

        assert result.success is True
        assert result.data["session_id"] is not None
        assert result.data["topic"] == "bass design"
        assert result.data["duration_minutes"] == 60
        assert result.data["total_sessions"] == 1

    def test_session_persisted_to_file(self, tmp_path):
        """Session should be written to JSON file."""
        storage = tmp_path / "sessions.json"
        tool = LogPracticeSession(sessions_file=storage)

        tool(topic="mixing", duration_minutes=45, notes="Worked on EQ")

        assert storage.exists()
        data = json.loads(storage.read_text())
        assert len(data) == 1
        assert data[0]["topic"] == "mixing"
        assert data[0]["duration_minutes"] == 45
        assert data[0]["notes"] == "Worked on EQ"

    def test_multiple_sessions_accumulated(self, tmp_path):
        """Each call should append to existing sessions."""
        storage = tmp_path / "sessions.json"
        tool = LogPracticeSession(sessions_file=storage)

        tool(topic="bass design", duration_minutes=60)
        tool(topic="mixing", duration_minutes=30)
        result = tool(topic="arrangement", duration_minutes=90)

        assert result.data["total_sessions"] == 3

    def test_session_id_is_timestamp_format(self, tmp_path):
        """session_id should follow YYYYMMDDTHHmmss format."""
        storage = tmp_path / "sessions.json"
        tool = LogPracticeSession(sessions_file=storage)

        result = tool(topic="synthesis", duration_minutes=30)

        session_id = result.data["session_id"]
        # Format: 20250217T143022
        assert len(session_id) == 15
        assert session_id[8] == "T"
        assert session_id.replace("T", "").isdigit()

    def test_metadata_includes_storage_path(self, tmp_path):
        """metadata should include the storage file path."""
        storage = tmp_path / "sessions.json"
        tool = LogPracticeSession(sessions_file=storage)

        result = tool(topic="EQ", duration_minutes=30)

        assert "storage" in result.metadata
        assert str(storage) in result.metadata["storage"]

    def test_creates_parent_directory(self, tmp_path):
        """Should create parent directories if they don't exist."""
        storage = tmp_path / "nested" / "deep" / "sessions.json"
        tool = LogPracticeSession(sessions_file=storage)

        result = tool(topic="mixing", duration_minutes=30)

        assert result.success is True
        assert storage.exists()

    def test_notes_optional_omitted(self, tmp_path):
        """Should work without notes parameter."""
        storage = tmp_path / "sessions.json"
        tool = LogPracticeSession(sessions_file=storage)

        result = tool(topic="synthesis", duration_minutes=45)

        assert result.success is True
        data = json.loads(storage.read_text())
        assert data[0]["notes"] == ""


# ---------------------------------------------------------------------------
# Input validation — domain errors
# ---------------------------------------------------------------------------


class TestLogPracticeSessionValidation:
    """Test domain-level input validation."""

    def test_empty_topic_rejected(self, tmp_path):
        """Empty topic string should return error."""
        tool = LogPracticeSession(sessions_file=tmp_path / "s.json")
        result = tool(topic="", duration_minutes=30)
        assert result.success is False
        assert "topic" in result.error.lower()

    def test_whitespace_only_topic_rejected(self, tmp_path):
        """Whitespace-only topic should return error."""
        tool = LogPracticeSession(sessions_file=tmp_path / "s.json")
        result = tool(topic="   ", duration_minutes=30)
        assert result.success is False

    def test_topic_too_long_rejected(self, tmp_path):
        """Topic exceeding max length should return error."""
        tool = LogPracticeSession(sessions_file=tmp_path / "s.json")
        result = tool(topic="x" * 201, duration_minutes=30)
        assert result.success is False
        assert "too long" in result.error.lower()

    def test_duration_zero_rejected(self, tmp_path):
        """Duration of 0 minutes should be rejected."""
        tool = LogPracticeSession(sessions_file=tmp_path / "s.json")
        result = tool(topic="mixing", duration_minutes=0)
        assert result.success is False
        assert "duration" in result.error.lower()

    def test_negative_duration_rejected(self, tmp_path):
        """Negative duration should be rejected."""
        tool = LogPracticeSession(sessions_file=tmp_path / "s.json")
        result = tool(topic="mixing", duration_minutes=-10)
        assert result.success is False

    def test_duration_too_long_rejected(self, tmp_path):
        """Duration over 720 minutes (12h) should be rejected."""
        tool = LogPracticeSession(sessions_file=tmp_path / "s.json")
        result = tool(topic="mixing", duration_minutes=721)
        assert result.success is False
        assert "720" in result.error

    def test_notes_too_long_rejected(self, tmp_path):
        """Notes exceeding max length should be rejected."""
        tool = LogPracticeSession(sessions_file=tmp_path / "s.json")
        result = tool(topic="mixing", duration_minutes=30, notes="n" * 2001)
        assert result.success is False
        assert "notes" in result.error.lower()

    def test_missing_topic_returns_validation_error(self, tmp_path):
        """Missing required topic should fail base class validation."""
        tool = LogPracticeSession(sessions_file=tmp_path / "s.json")
        result = tool(duration_minutes=30)
        assert result.success is False
        assert "topic" in result.error

    def test_wrong_type_duration_returns_validation_error(self, tmp_path):
        """String passed as duration_minutes should fail type validation."""
        tool = LogPracticeSession(sessions_file=tmp_path / "s.json")
        result = tool(topic="mixing", duration_minutes="thirty")
        assert result.success is False
        assert "int" in result.error


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------


class TestGapAnalysis:
    """Test practice gap detection logic."""

    def test_gaps_empty_sessions(self):
        """With no sessions, all core topics should be gaps."""
        gaps = _find_practice_gaps([])
        assert len(gaps) > 0
        assert "arrangement" in gaps
        assert "mixing" in gaps

    def test_recent_topic_removed_from_gaps(self):
        """A recently practiced topic should not appear in gaps."""
        from datetime import datetime

        recent_session = {
            "topic": "arrangement",
            "logged_at": datetime.now(UTC).isoformat(),
            "tags": ["arrangement", "structure"],
        }
        gaps = _find_practice_gaps([recent_session], days=7)
        assert "arrangement" not in gaps

    def test_old_session_still_a_gap(self):
        """A topic practiced 10 days ago should appear as a gap (7-day window)."""
        from datetime import datetime, timedelta

        old_session = {
            "topic": "arrangement",
            "logged_at": (datetime.now(UTC) - timedelta(days=10)).isoformat(),
            "tags": ["arrangement"],
        }
        gaps = _find_practice_gaps([old_session], days=7)
        assert "arrangement" in gaps

    def test_returns_list_of_strings(self):
        """gaps should always be a list of strings."""
        gaps = _find_practice_gaps([])
        assert isinstance(gaps, list)
        assert all(isinstance(g, str) for g in gaps)

    def test_logged_session_affects_gaps(self, tmp_path):
        """After logging a session, its topic should leave gaps list."""
        storage = tmp_path / "sessions.json"
        tool = LogPracticeSession(sessions_file=storage)

        result = tool(topic="arrangement", duration_minutes=120)

        assert "arrangement" not in result.data["gaps"]


# ---------------------------------------------------------------------------
# Tag extraction (pure function)
# ---------------------------------------------------------------------------


class TestExtractTags:
    """Test tag extraction from topic + notes."""

    def test_basic_extraction(self):
        """Should extract meaningful words from topic."""
        tags = _extract_tags("bass design", "")
        assert "bass" in tags
        assert "design" in tags

    def test_stop_words_excluded(self):
        """Common stop words should be excluded."""
        tags = _extract_tags("mixing the kick and bass", "")
        assert "the" not in tags
        assert "and" not in tags
        assert "kick" in tags
        assert "bass" in tags

    def test_short_words_excluded(self):
        """Very short words (≤2 chars) should be excluded."""
        tags = _extract_tags("EQ on the hi-hat", "")
        assert "on" not in tags

    def test_notes_contribute_to_tags(self):
        """Words from notes should appear in tags."""
        tags = _extract_tags("mixing", "practiced sidechain compression")
        assert "sidechain" in tags
        assert "compression" in tags

    def test_returns_sorted_tuple(self):
        """Tags should be returned as a sorted tuple."""
        tags = _extract_tags("synthesis design", "oscillator filter")
        assert isinstance(tags, tuple)
        assert list(tags) == sorted(tags)

    def test_tags_are_lowercase(self):
        """All tags should be lowercase."""
        tags = _extract_tags("Bass Design", "")
        assert all(t == t.lower() for t in tags)
