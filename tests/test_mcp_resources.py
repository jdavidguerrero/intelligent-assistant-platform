"""
MCP Musical Intelligence — resources.py tests.

Test strategy (pure unit tests — no network, no real DB):

    1. Pure-function tests — _compute_session_stats, _compute_category_counts,
       _filter_sessions, _filter_notes, _classify_source_types.
       These are the data-transformation contracts.

    2. File I/O tests — use pytest tmp_path to write JSON fixtures and patch
       the module-level Path constants so resource functions read our files.

    3. Edge-case tests — missing file, corrupted JSON, empty list, boundary
       pagination values.

All assertions target the *public contract* (JSON keys, values, types), not
the internal implementation, so refactoring the internals stays safe.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(
    topic: str = "groove",
    duration_minutes: int = 30,
    logged_at: str = "2025-06-01T10:00:00",
) -> dict:
    return {"topic": topic, "duration_minutes": duration_minutes, "logged_at": logged_at}


def _make_note(
    category: str = "discovery",
    title: str = "Test note",
    content: str = "Some content",
    tags: list | None = None,
    created_at: str = "2025-06-01T10:00:00",
) -> dict:
    return {
        "category": category,
        "title": title,
        "content": content,
        "tags": tags or [],
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# Pure function: _compute_session_stats
# ---------------------------------------------------------------------------


class TestComputeSessionStats:
    def test_empty_returns_zero_stats(self) -> None:
        from musical_mcp.resources import _compute_session_stats

        stats = _compute_session_stats([])
        assert stats["total_sessions"] == 0
        assert stats["total_minutes"] == 0
        assert stats["topics"] == {}
        assert stats["most_practiced"] is None
        assert stats["least_practiced"] is None
        assert stats["avg_session_min"] == 0.0

    def test_single_session(self) -> None:
        from musical_mcp.resources import _compute_session_stats

        sessions = [_make_session("groove", 45)]
        stats = _compute_session_stats(sessions)
        assert stats["total_sessions"] == 1
        assert stats["total_minutes"] == 45
        assert stats["avg_session_min"] == 45.0
        assert stats["most_practiced"] == "groove"
        assert stats["least_practiced"] is None  # only 1 topic

    def test_multiple_sessions_same_topic(self) -> None:
        from musical_mcp.resources import _compute_session_stats

        sessions = [
            _make_session("groove", 30),
            _make_session("groove", 60),
        ]
        stats = _compute_session_stats(sessions)
        assert stats["total_sessions"] == 2
        assert stats["total_minutes"] == 90
        assert stats["topics"]["groove"] == 90
        assert stats["avg_session_min"] == 45.0

    def test_most_and_least_practiced(self) -> None:
        from musical_mcp.resources import _compute_session_stats

        sessions = [
            _make_session("groove", 90),
            _make_session("chords", 20),
            _make_session("melody", 40),
        ]
        stats = _compute_session_stats(sessions)
        assert stats["most_practiced"] == "groove"
        assert stats["least_practiced"] == "chords"

    def test_topics_dict_sorted_by_minutes_descending(self) -> None:
        from musical_mcp.resources import _compute_session_stats

        sessions = [
            _make_session("z_topic", 10),
            _make_session("a_topic", 100),
        ]
        stats = _compute_session_stats(sessions)
        topics_list = list(stats["topics"].items())
        assert topics_list[0][0] == "a_topic"  # highest minutes first

    def test_avg_session_min_is_rounded_to_one_decimal(self) -> None:
        from musical_mcp.resources import _compute_session_stats

        sessions = [
            _make_session("a", 10),
            _make_session("a", 10),
            _make_session("a", 11),
        ]
        stats = _compute_session_stats(sessions)
        # 31 / 3 = 10.333... → 10.3
        assert stats["avg_session_min"] == 10.3

    def test_sessions_without_duration_count_as_zero(self) -> None:
        from musical_mcp.resources import _compute_session_stats

        sessions = [{"topic": "groove"}]  # no duration_minutes
        stats = _compute_session_stats(sessions)
        assert stats["total_minutes"] == 0


# ---------------------------------------------------------------------------
# Pure function: _compute_category_counts
# ---------------------------------------------------------------------------


class TestComputeCategoryCounts:
    def test_empty_returns_empty_dict(self) -> None:
        from musical_mcp.resources import _compute_category_counts

        assert _compute_category_counts([]) == {}

    def test_single_category(self) -> None:
        from musical_mcp.resources import _compute_category_counts

        notes = [_make_note("discovery"), _make_note("discovery")]
        counts = _compute_category_counts(notes)
        assert counts["discovery"] == 2

    def test_multiple_categories(self) -> None:
        from musical_mcp.resources import _compute_category_counts

        notes = [
            _make_note("discovery"),
            _make_note("problem"),
            _make_note("idea"),
            _make_note("problem"),
        ]
        counts = _compute_category_counts(notes)
        assert counts["discovery"] == 1
        assert counts["problem"] == 2
        assert counts["idea"] == 1

    def test_result_is_sorted_by_key(self) -> None:
        from musical_mcp.resources import _compute_category_counts

        notes = [_make_note("z_cat"), _make_note("a_cat")]
        counts = _compute_category_counts(notes)
        assert list(counts.keys()) == sorted(counts.keys())

    def test_missing_category_field_counted_as_unknown(self) -> None:
        from musical_mcp.resources import _compute_category_counts

        notes = [{"title": "No category field"}]
        counts = _compute_category_counts(notes)
        assert "unknown" in counts


# ---------------------------------------------------------------------------
# Pure function: _filter_sessions
# ---------------------------------------------------------------------------


class TestFilterSessions:
    def test_no_filters_returns_all(self) -> None:
        from musical_mcp.resources import _filter_sessions

        sessions = [_make_session("groove"), _make_session("chords")]
        result = _filter_sessions(sessions, "", "", "")
        assert len(result) == 2

    def test_date_from_excludes_older(self) -> None:
        from musical_mcp.resources import _filter_sessions

        sessions = [
            _make_session(logged_at="2025-01-01T00:00:00"),
            _make_session(logged_at="2025-06-01T00:00:00"),
        ]
        result = _filter_sessions(sessions, "2025-03-01", "", "")
        assert len(result) == 1
        assert result[0]["logged_at"] == "2025-06-01T00:00:00"

    def test_date_to_excludes_newer(self) -> None:
        from musical_mcp.resources import _filter_sessions

        sessions = [
            _make_session(logged_at="2025-01-01T00:00:00"),
            _make_session(logged_at="2025-12-01T00:00:00"),
        ]
        result = _filter_sessions(sessions, "", "2025-06-01", "")
        assert len(result) == 1
        assert result[0]["logged_at"] == "2025-01-01T00:00:00"

    def test_date_range_both_ends(self) -> None:
        from musical_mcp.resources import _filter_sessions

        sessions = [
            _make_session(logged_at="2025-01-01T00:00:00"),
            _make_session(logged_at="2025-04-15T00:00:00"),
            _make_session(logged_at="2025-12-01T00:00:00"),
        ]
        result = _filter_sessions(sessions, "2025-03-01", "2025-06-01", "")
        assert len(result) == 1
        assert result[0]["logged_at"] == "2025-04-15T00:00:00"

    def test_topic_contains_case_insensitive(self) -> None:
        from musical_mcp.resources import _filter_sessions

        sessions = [
            _make_session(topic="Groove and rhythm"),
            _make_session(topic="chord theory"),
        ]
        result = _filter_sessions(sessions, "", "", "groove")
        assert len(result) == 1
        assert result[0]["topic"] == "Groove and rhythm"

    def test_invalid_date_from_ignored(self) -> None:
        from musical_mcp.resources import _filter_sessions

        sessions = [_make_session()]
        result = _filter_sessions(sessions, "not-a-date", "", "")
        assert len(result) == 1  # filter ignored, all returned

    def test_invalid_date_to_ignored(self) -> None:
        from musical_mcp.resources import _filter_sessions

        sessions = [_make_session()]
        result = _filter_sessions(sessions, "", "bad-date", "")
        assert len(result) == 1

    def test_combined_filters_are_and_logic(self) -> None:
        from musical_mcp.resources import _filter_sessions

        sessions = [
            _make_session(topic="groove", logged_at="2025-06-01T00:00:00"),
            _make_session(topic="chords", logged_at="2025-06-01T00:00:00"),
            _make_session(topic="groove", logged_at="2025-01-01T00:00:00"),
        ]
        result = _filter_sessions(sessions, "2025-03-01", "", "groove")
        # Only the one with groove AND after 2025-03-01
        assert len(result) == 1
        assert result[0]["topic"] == "groove"
        assert result[0]["logged_at"] == "2025-06-01T00:00:00"


# ---------------------------------------------------------------------------
# Pure function: _filter_notes
# ---------------------------------------------------------------------------


class TestFilterNotes:
    def test_no_filters_returns_all(self) -> None:
        from musical_mcp.resources import _filter_notes

        notes = [_make_note("discovery"), _make_note("idea")]
        result = _filter_notes(notes, "", "", "", "")
        assert len(result) == 2

    def test_category_exact_match_case_insensitive(self) -> None:
        from musical_mcp.resources import _filter_notes

        notes = [
            _make_note("discovery"),
            _make_note("DISCOVERY"),
            _make_note("idea"),
        ]
        result = _filter_notes(notes, "discovery", "", "", "")
        assert len(result) == 2

    def test_tag_substring_match_case_insensitive(self) -> None:
        from musical_mcp.resources import _filter_notes

        notes = [
            _make_note(tags=["Organic House", "chords"]),
            _make_note(tags=["techno"]),
        ]
        result = _filter_notes(notes, "", "organic", "", "")
        assert len(result) == 1

    def test_date_from_filter(self) -> None:
        from musical_mcp.resources import _filter_notes

        notes = [
            _make_note(created_at="2025-01-01T00:00:00"),
            _make_note(created_at="2025-08-01T00:00:00"),
        ]
        result = _filter_notes(notes, "", "", "2025-06-01", "")
        assert len(result) == 1
        assert result[0]["created_at"] == "2025-08-01T00:00:00"

    def test_date_to_filter(self) -> None:
        from musical_mcp.resources import _filter_notes

        notes = [
            _make_note(created_at="2025-01-01T00:00:00"),
            _make_note(created_at="2025-08-01T00:00:00"),
        ]
        result = _filter_notes(notes, "", "", "", "2025-06-01")
        assert len(result) == 1
        assert result[0]["created_at"] == "2025-01-01T00:00:00"

    def test_category_and_tag_combined(self) -> None:
        from musical_mcp.resources import _filter_notes

        notes = [
            _make_note("discovery", tags=["setlist"]),
            _make_note("discovery", tags=["practice"]),
            _make_note("idea", tags=["setlist"]),
        ]
        result = _filter_notes(notes, "discovery", "setlist", "", "")
        assert len(result) == 1

    def test_note_with_no_tags_excluded_by_tag_filter(self) -> None:
        from musical_mcp.resources import _filter_notes

        notes = [_make_note(tags=[]), _make_note(tags=["groove"])]
        result = _filter_notes(notes, "", "groove", "", "")
        assert len(result) == 1

    def test_none_tags_field_handled_gracefully(self) -> None:
        from musical_mcp.resources import _filter_notes

        note = {"category": "idea", "tags": None}
        result = _filter_notes([note], "", "groove", "", "")
        assert len(result) == 0  # no match but no crash


# ---------------------------------------------------------------------------
# Pure function: _classify_source_types
# ---------------------------------------------------------------------------


class TestClassifySourceTypes:
    def test_empty_sources(self) -> None:
        from musical_mcp.resources import _classify_source_types

        result = _classify_source_types([])
        assert result == {"pdf": 0, "youtube": 0, "markdown": 0, "other": 0}

    def test_pdf_classification(self) -> None:
        from musical_mcp.resources import _classify_source_types

        sources = [{"source_path": "docs/manual.pdf", "chunk_count": 15}]
        result = _classify_source_types(sources)
        assert result["pdf"] == 15

    def test_youtube_classification(self) -> None:
        from musical_mcp.resources import _classify_source_types

        sources = [{"source_path": "https://youtube.com/watch?v=abc", "chunk_count": 8}]
        result = _classify_source_types(sources)
        assert result["youtube"] == 8

    def test_markdown_classification(self) -> None:
        from musical_mcp.resources import _classify_source_types

        sources = [{"source_path": "courses/pete_tong.md", "chunk_count": 30}]
        result = _classify_source_types(sources)
        assert result["markdown"] == 30

    def test_other_classification(self) -> None:
        from musical_mcp.resources import _classify_source_types

        sources = [{"source_path": "data/unknown.csv", "chunk_count": 5}]
        result = _classify_source_types(sources)
        assert result["other"] == 5

    def test_all_types_summed_correctly(self) -> None:
        from musical_mcp.resources import _classify_source_types

        sources = [
            {"source_path": "a.pdf", "chunk_count": 10},
            {"source_path": "https://youtube.com/v=x", "chunk_count": 5},
            {"source_path": "course.md", "chunk_count": 8},
            {"source_path": "data.csv", "chunk_count": 3},
        ]
        result = _classify_source_types(sources)
        assert result["pdf"] == 10
        assert result["youtube"] == 5
        assert result["markdown"] == 8
        assert result["other"] == 3


# ---------------------------------------------------------------------------
# File I/O: read_practice_logs
# ---------------------------------------------------------------------------


class TestReadPracticeLogs:
    def _patch(self, tmp_file: Path):
        """Context manager that patches _SESSIONS_FILE to tmp_file."""
        return patch("musical_mcp.resources._SESSIONS_FILE", tmp_file)

    def test_missing_file_returns_empty_response(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_practice_logs

        missing = tmp_path / "nonexistent.json"
        with self._patch(missing):
            result = json.loads(read_practice_logs())
        assert result["sessions"] == []
        assert result["total"] == 0

    def test_corrupted_json_returns_error_response(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_practice_logs

        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{ invalid json }", encoding="utf-8")
        with self._patch(bad_file):
            result = json.loads(read_practice_logs())
        assert result["sessions"] == []
        assert "error" in result

    def test_empty_list_file(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_practice_logs

        f = tmp_path / "sessions.json"
        f.write_text("[]", encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_practice_logs())
        assert result["total"] == 0
        assert result["sessions"] == []

    def test_returns_all_sessions_within_limit(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_practice_logs

        sessions = [_make_session(f"topic_{i}", 30 + i) for i in range(5)]
        f = tmp_path / "sessions.json"
        f.write_text(json.dumps(sessions), encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_practice_logs(limit=10))
        assert result["total"] == 5
        assert len(result["sessions"]) == 5

    def test_pagination_limit(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_practice_logs

        sessions = [_make_session(f"topic_{i}") for i in range(10)]
        f = tmp_path / "sessions.json"
        f.write_text(json.dumps(sessions), encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_practice_logs(limit=3))
        assert len(result["sessions"]) == 3
        assert result["total"] == 10
        assert result["limit"] == 3

    def test_pagination_offset(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_practice_logs

        sessions = [_make_session(f"topic_{i}") for i in range(5)]
        f = tmp_path / "sessions.json"
        f.write_text(json.dumps(sessions), encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_practice_logs(limit=2, offset=3))
        assert len(result["sessions"]) == 2
        assert result["offset"] == 3
        assert result["sessions"][0]["topic"] == "topic_3"

    def test_offset_beyond_total_returns_empty(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_practice_logs

        sessions = [_make_session() for _ in range(3)]
        f = tmp_path / "sessions.json"
        f.write_text(json.dumps(sessions), encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_practice_logs(offset=100))
        assert result["sessions"] == []
        assert result["total"] == 3  # total is pre-pagination count

    def test_topic_contains_filter(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_practice_logs

        sessions = [
            _make_session("groove training"),
            _make_session("chord theory"),
            _make_session("Groove mastery"),
        ]
        f = tmp_path / "sessions.json"
        f.write_text(json.dumps(sessions), encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_practice_logs(topic_contains="groove"))
        assert result["total"] == 2

    def test_date_from_filter(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_practice_logs

        sessions = [
            _make_session(logged_at="2025-01-01T00:00:00"),
            _make_session(logged_at="2025-09-01T00:00:00"),
        ]
        f = tmp_path / "sessions.json"
        f.write_text(json.dumps(sessions), encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_practice_logs(date_from="2025-06-01"))
        assert result["total"] == 1

    def test_response_includes_stats(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_practice_logs

        sessions = [_make_session("groove", 45), _make_session("chords", 30)]
        f = tmp_path / "sessions.json"
        f.write_text(json.dumps(sessions), encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_practice_logs())
        assert "stats" in result
        assert result["stats"]["total_sessions"] == 2
        assert result["stats"]["total_minutes"] == 75

    def test_limit_clamped_to_max_100(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_practice_logs

        sessions = [_make_session() for _ in range(5)]
        f = tmp_path / "sessions.json"
        f.write_text(json.dumps(sessions), encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_practice_logs(limit=999))
        assert result["limit"] == 100

    def test_limit_clamped_to_min_1(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_practice_logs

        sessions = [_make_session() for _ in range(5)]
        f = tmp_path / "sessions.json"
        f.write_text(json.dumps(sessions), encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_practice_logs(limit=0))
        assert result["limit"] == 1

    def test_result_is_always_valid_json(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_practice_logs

        f = tmp_path / "sessions.json"
        f.write_text("null", encoding="utf-8")  # valid JSON but not a list
        with self._patch(f):
            raw = read_practice_logs()
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)
        assert "sessions" in parsed


# ---------------------------------------------------------------------------
# File I/O: read_session_notes
# ---------------------------------------------------------------------------


class TestReadSessionNotes:
    def _patch(self, tmp_file: Path):
        return patch("musical_mcp.resources._NOTES_FILE", tmp_file)

    def test_missing_file_returns_empty_response(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_session_notes

        missing = tmp_path / "nonexistent.json"
        with self._patch(missing):
            result = json.loads(read_session_notes())
        assert result["notes"] == []
        assert result["total"] == 0

    def test_category_filter(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_session_notes

        notes = [
            _make_note("discovery"),
            _make_note("discovery"),
            _make_note("idea"),
        ]
        f = tmp_path / "notes.json"
        f.write_text(json.dumps(notes), encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_session_notes(category="discovery"))
        assert result["total"] == 2

    def test_tag_filter(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_session_notes

        notes = [
            _make_note(tags=["setlist", "groove"]),
            _make_note(tags=["practice"]),
        ]
        f = tmp_path / "notes.json"
        f.write_text(json.dumps(notes), encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_session_notes(tag="setlist"))
        assert result["total"] == 1

    def test_category_counts_over_full_dataset_before_filter(self, tmp_path: Path) -> None:
        """category_counts reflects the FULL dataset, not the filtered page."""
        from musical_mcp.resources import read_session_notes

        notes = [
            _make_note("discovery"),
            _make_note("discovery"),
            _make_note("idea"),
        ]
        f = tmp_path / "notes.json"
        f.write_text(json.dumps(notes), encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_session_notes(category="idea"))
        # Only 1 note in filtered result, but category_counts has all 3
        assert result["total"] == 1
        assert result["category_counts"]["discovery"] == 2
        assert result["category_counts"]["idea"] == 1

    def test_pagination_works(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_session_notes

        notes = [_make_note(f"cat_{i}") for i in range(8)]
        f = tmp_path / "notes.json"
        f.write_text(json.dumps(notes), encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_session_notes(limit=3, offset=2))
        assert len(result["notes"]) == 3
        assert result["offset"] == 2
        assert result["total"] == 8

    def test_response_contains_required_keys(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_session_notes

        f = tmp_path / "notes.json"
        f.write_text("[]", encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_session_notes())
        for key in ("notes", "total", "offset", "limit", "category_counts"):
            assert key in result, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# File I/O: read_setlist
# ---------------------------------------------------------------------------


class TestReadSetlist:
    def _patch(self, tmp_file: Path):
        return patch("musical_mcp.resources._NOTES_FILE", tmp_file)

    def test_missing_file_returns_empty_setlist(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_setlist

        missing = tmp_path / "nonexistent.json"
        with self._patch(missing):
            result = json.loads(read_setlist())
        assert result["setlist_notes"] == []
        assert result["total"] == 0
        assert result["last_updated"] is None

    def test_notes_without_setlist_tag_excluded(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_setlist

        notes = [
            _make_note(tags=["practice"]),
            _make_note(tags=["groove"]),
        ]
        f = tmp_path / "notes.json"
        f.write_text(json.dumps(notes), encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_setlist())
        assert result["total"] == 0
        assert result["setlist_notes"] == []

    def test_notes_with_setlist_tag_included(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_setlist

        notes = [
            _make_note(tags=["setlist", "groove"]),
            _make_note(tags=["practice"]),
            _make_note(tags=["setlist"]),
        ]
        f = tmp_path / "notes.json"
        f.write_text(json.dumps(notes), encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_setlist())
        assert result["total"] == 2

    def test_last_updated_is_max_created_at(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_setlist

        notes = [
            _make_note(tags=["setlist"], created_at="2025-03-01T10:00:00"),
            _make_note(tags=["setlist"], created_at="2025-06-15T10:00:00"),
            _make_note(tags=["setlist"], created_at="2025-01-10T10:00:00"),
        ]
        f = tmp_path / "notes.json"
        f.write_text(json.dumps(notes), encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_setlist())
        assert result["last_updated"] == "2025-06-15T10:00:00"

    def test_last_updated_none_when_no_setlist_notes(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_setlist

        f = tmp_path / "notes.json"
        f.write_text("[]", encoding="utf-8")
        with self._patch(f):
            result = json.loads(read_setlist())
        assert result["last_updated"] is None

    def test_response_always_valid_json_on_corrupt_file(self, tmp_path: Path) -> None:
        from musical_mcp.resources import read_setlist

        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{ bad json", encoding="utf-8")
        with self._patch(bad_file):
            raw = read_setlist()
        parsed = json.loads(raw)
        assert "setlist_notes" in parsed


# ---------------------------------------------------------------------------
# read_kb_metadata — no DATABASE_URL path
# ---------------------------------------------------------------------------


class TestReadKbMetadata:
    def test_no_database_url_returns_unavailable(self) -> None:
        from musical_mcp.resources import read_kb_metadata

        with patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False):
            result = json.loads(read_kb_metadata())
        assert result["status"] == "unavailable"
        assert result["total_chunks"] == 0
        assert result["sources"] == []

    def test_unavailable_response_has_reason(self) -> None:
        from musical_mcp.resources import read_kb_metadata

        with patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False):
            result = json.loads(read_kb_metadata())
        assert "reason" in result
        assert len(result["reason"]) > 0
