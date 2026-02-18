"""
Tests for create_session_note tool.

Uses temporary files for persistence tests — never touches real data/session_notes.json.

Coverage:
  - _extract_tags: keyword detection
  - SessionNote schema: fields, immutability
  - CreateSessionNote: interface, validation, happy path, persistence
  - load_notes: read from file
"""

import json
import tempfile
from pathlib import Path

from tools.music.create_session_note import (
    VALID_CATEGORIES,
    CreateSessionNote,
    SessionNote,
    _extract_tags,
    load_notes,
)

# ---------------------------------------------------------------------------
# _extract_tags
# ---------------------------------------------------------------------------


class TestExtractTags:
    def test_sidechain_extracted(self):
        tags = _extract_tags("sidechain compression on the kick")
        assert "sidechain" in tags
        assert "compression" in tags
        assert "kick" in tags

    def test_midi_extracted(self):
        tags = _extract_tags("MIDI pattern with arp and chord")
        assert "midi" in tags
        assert "arp" in tags
        assert "chord" in tags

    def test_no_keywords_returns_empty(self):
        tags = _extract_tags("today was a productive day")
        assert tags == []

    def test_deduplication(self):
        tags = _extract_tags("bass bass bass")
        assert tags.count("bass") == 1

    def test_returns_sorted_list(self):
        tags = _extract_tags("reverb delay eq filter")
        assert tags == sorted(tags)

    def test_case_insensitive(self):
        tags = _extract_tags("EQ and COMPRESSION make the mix")
        assert "eq" in tags
        assert "compression" in tags

    def test_word_boundary_match(self):
        """'bass' should not match inside 'database'."""
        tags = _extract_tags("database query optimization")
        assert "bass" not in tags


# ---------------------------------------------------------------------------
# SessionNote schema
# ---------------------------------------------------------------------------


class TestSessionNoteSchema:
    def test_is_immutable(self):
        note = SessionNote(
            note_id="test",
            created_at="2025-01-01T00:00:00",
            category="discovery",
            title="Test",
            content="Content",
            tags=("bass",),
            linked_topic="",
            action_items=(),
        )
        try:
            note.title = "Modified"  # type: ignore[misc]
            raise AssertionError("Should be frozen")
        except Exception:
            pass

    def test_tags_is_tuple(self):
        note = SessionNote(
            note_id="x",
            created_at="2025-01-01T00:00:00",
            category="idea",
            title="T",
            content="C",
            tags=("a", "b"),
            linked_topic="",
            action_items=(),
        )
        assert isinstance(note.tags, tuple)

    def test_action_items_is_tuple(self):
        note = SessionNote(
            note_id="x",
            created_at="2025-01-01T00:00:00",
            category="next_steps",
            title="T",
            content="C",
            tags=(),
            linked_topic="",
            action_items=("do this", "do that"),
        )
        assert isinstance(note.action_items, tuple)


# ---------------------------------------------------------------------------
# CreateSessionNote tool — interface
# ---------------------------------------------------------------------------


class TestCreateSessionNoteProperties:
    _tool = CreateSessionNote(notes_file=Path(tempfile.mktemp(suffix=".json")))

    def test_name(self):
        assert self._tool.name == "create_session_note"

    def test_description_mentions_categories(self):
        desc = self._tool.description.lower()
        assert "discovery" in desc
        assert "idea" in desc

    def test_required_params(self):
        required = [p.name for p in self._tool.parameters if p.required]
        assert "category" in required
        assert "title" in required
        assert "content" in required

    def test_optional_params(self):
        optional = [p.name for p in self._tool.parameters if not p.required]
        assert "linked_topic" in optional
        assert "action_items" in optional
        assert "tags" in optional


# ---------------------------------------------------------------------------
# CreateSessionNote tool — validation
# ---------------------------------------------------------------------------


class TestCreateSessionNoteValidation:
    def _tool(self):
        return CreateSessionNote(notes_file=Path(tempfile.mktemp(suffix=".json")))

    def test_empty_category_rejected(self):
        result = self._tool()(category="", title="T", content="C")
        assert result.success is False
        assert "category" in result.error.lower()

    def test_invalid_category_rejected(self):
        result = self._tool()(category="nonsense", title="T", content="C")
        assert result.success is False
        assert "category" in result.error.lower()

    def test_all_valid_categories_accepted(self):
        for cat in VALID_CATEGORIES:
            t = self._tool()
            result = t(category=cat, title="T", content="C")
            assert result.success is True, f"Category '{cat}' should be valid"

    def test_empty_title_rejected(self):
        result = self._tool()(category="discovery", title="", content="C")
        assert result.success is False
        assert "title" in result.error.lower()

    def test_empty_content_rejected(self):
        result = self._tool()(category="discovery", title="T", content="")
        assert result.success is False
        assert "content" in result.error.lower()

    def test_title_too_long_rejected(self):
        from tools.music.create_session_note import MAX_TITLE_LENGTH

        result = self._tool()(category="discovery", title="X" * (MAX_TITLE_LENGTH + 1), content="C")
        assert result.success is False
        assert "title" in result.error.lower()

    def test_content_too_long_rejected(self):
        from tools.music.create_session_note import MAX_CONTENT_LENGTH

        result = self._tool()(
            category="discovery", title="T", content="X" * (MAX_CONTENT_LENGTH + 1)
        )
        assert result.success is False
        assert "content" in result.error.lower()

    def test_action_items_not_list_rejected(self):
        result = self._tool()(category="next_steps", title="T", content="C", action_items="do this")
        assert result.success is False
        assert "action_items" in result.error.lower()

    def test_too_many_action_items_rejected(self):
        from tools.music.create_session_note import MAX_ACTION_ITEMS

        items = [f"item {i}" for i in range(MAX_ACTION_ITEMS + 1)]
        result = self._tool()(category="next_steps", title="T", content="C", action_items=items)
        assert result.success is False

    def test_action_item_non_string_rejected(self):
        result = self._tool()(category="next_steps", title="T", content="C", action_items=[123])
        assert result.success is False

    def test_tags_not_list_rejected(self):
        result = self._tool()(category="discovery", title="T", content="C", tags="bass")
        assert result.success is False
        assert "tags" in result.error.lower()


# ---------------------------------------------------------------------------
# CreateSessionNote tool — happy path
# ---------------------------------------------------------------------------


class TestCreateSessionNoteHappyPath:
    def _tool(self):
        return CreateSessionNote(notes_file=Path(tempfile.mktemp(suffix=".json")))

    def test_basic_discovery_note_saved(self):
        result = self._tool()(
            category="discovery",
            title="Sidechain pumping trick",
            content="Using 0.1ms attack on the compressor sidechain creates tight pumping.",
        )
        assert result.success is True

    def test_result_has_note_id(self):
        result = self._tool()(category="idea", title="T", content="C")
        assert "note_id" in result.data
        assert len(result.data["note_id"]) == 15  # YYYYMMDDTHHmmss

    def test_result_has_category(self):
        result = self._tool()(category="reference", title="T", content="C")
        assert result.data["category"] == "reference"

    def test_tags_auto_extracted_from_content(self):
        result = self._tool()(
            category="discovery",
            title="Bass trick",
            content="Using sidechain compression on kick and bass",
        )
        assert result.success is True
        assert "bass" in result.data["tags"]
        assert "sidechain" in result.data["tags"]

    def test_custom_tags_used_when_provided(self):
        result = self._tool()(
            category="discovery",
            title="T",
            content="Some content",
            tags=["custom", "tag"],
        )
        assert "custom" in result.data["tags"]

    def test_linked_topic_preserved(self):
        result = self._tool()(
            category="discovery",
            title="T",
            content="C",
            linked_topic="bass design",
        )
        assert result.data["linked_topic"] == "bass design"

    def test_action_items_preserved(self):
        result = self._tool()(
            category="next_steps",
            title="T",
            content="C",
            action_items=["try with 808", "test on organic house"],
        )
        assert "try with 808" in result.data["action_items"]
        assert "test on organic house" in result.data["action_items"]

    def test_empty_action_items_ignored(self):
        """Empty strings in action_items should be silently dropped."""
        result = self._tool()(
            category="next_steps",
            title="T",
            content="C",
            action_items=["real item", "", "  "],
        )
        assert result.success is True
        assert "real item" in result.data["action_items"]
        assert "" not in result.data["action_items"]

    def test_total_notes_increments(self):
        t = self._tool()
        r1 = t(category="idea", title="T1", content="C1")
        r2 = t(category="idea", title="T2", content="C2")
        assert r1.data["total_notes"] == 1
        assert r2.data["total_notes"] == 2

    def test_note_persisted_to_file(self):
        tmp = Path(tempfile.mktemp(suffix=".json"))
        t = CreateSessionNote(notes_file=tmp)
        t(category="discovery", title="Persisted", content="This was saved to disk.")
        assert tmp.exists()
        data = json.loads(tmp.read_text())
        assert len(data) == 1
        assert data[0]["title"] == "Persisted"

    def test_multiple_notes_appended(self):
        tmp = Path(tempfile.mktemp(suffix=".json"))
        t = CreateSessionNote(notes_file=tmp)
        t(category="idea", title="Note 1", content="C1")
        t(category="problem", title="Note 2", content="C2")
        data = json.loads(tmp.read_text())
        assert len(data) == 2

    def test_category_lowercased(self):
        result = self._tool()(category="DISCOVERY", title="T", content="C")
        assert result.data["category"] == "discovery"

    def test_metadata_has_category(self):
        result = self._tool()(category="idea", title="T", content="C")
        assert result.metadata["category"] == "idea"

    def test_metadata_tags_auto_extracted_flag(self):
        result = self._tool()(category="idea", title="T", content="C")
        assert result.metadata["tags_auto_extracted"] is True

    def test_metadata_tags_not_auto_extracted_when_provided(self):
        result = self._tool()(category="idea", title="T", content="C", tags=["manual"])
        assert result.metadata["tags_auto_extracted"] is False


# ---------------------------------------------------------------------------
# load_notes
# ---------------------------------------------------------------------------


class TestLoadNotes:
    def test_returns_empty_when_file_missing(self):
        tmp = Path(tempfile.mktemp(suffix=".json"))
        assert load_notes(tmp) == []

    def test_returns_notes_after_save(self):
        tmp = Path(tempfile.mktemp(suffix=".json"))
        t = CreateSessionNote(notes_file=tmp)
        t(category="discovery", title="T", content="C")
        notes = load_notes(tmp)
        assert len(notes) == 1
        assert notes[0]["title"] == "T"

    def test_returns_all_saved_notes(self):
        tmp = Path(tempfile.mktemp(suffix=".json"))
        t = CreateSessionNote(notes_file=tmp)
        for i in range(3):
            t(category="idea", title=f"Note {i}", content=f"Content {i}")
        notes = load_notes(tmp)
        assert len(notes) == 3

    def test_corrupt_file_returns_empty(self):
        tmp = Path(tempfile.mktemp(suffix=".json"))
        tmp.write_text("not valid json", encoding="utf-8")
        assert load_notes(tmp) == []
