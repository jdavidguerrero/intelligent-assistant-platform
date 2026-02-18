"""
Tests for search_by_genre tool.

Database calls are fully mocked — no Postgres, no pgvector, no embeddings needed.
Pure functions (_expand_genre) are tested without any mocking.

Mock strategy:
  - Patch `tools.music.search_by_genre._genre_search` inside each test call
    so the patch is active when execute() runs.
  - Inject a mock session_factory to prevent real DB connections.
  - Properties and validation tests don't need any mocking.
"""

from unittest.mock import MagicMock, patch

import numpy as np

from tools.music.search_by_genre import (
    MAX_GENRE_LENGTH,
    MAX_QUERY_LENGTH,
    MAX_TOP_K,
    MIN_TOP_K,
    SearchByGenre,
    _expand_genre,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PATCH_TARGET = "tools.music.search_by_genre._genre_search"


def _make_mock_record(
    source_name: str = "lesson.pdf",
    source_path: str = "/data/lesson.pdf",
    text: str = "Some content about organic house",
    page_number: int | None = 1,
    embedding: list[float] | None = None,
) -> MagicMock:
    """Build a mock ChunkRecord with configurable fields."""
    record = MagicMock()
    record.source_name = source_name
    record.source_path = source_path
    record.text = text
    record.page_number = page_number
    record.embedding = embedding or list(np.random.rand(1536).astype(np.float32))
    return record


def _make_tool(records: list[MagicMock] | None = None) -> SearchByGenre:
    """
    Build a SearchByGenre with a mock session_factory.

    Inject session_factory to prevent real DB connections.
    Callers must separately patch _genre_search around the tool() call.
    """
    records = records or []
    mock_session = MagicMock()
    mock_session.execute.return_value.scalars.return_value.all.return_value = records

    def _session_factory():
        yield mock_session

    return SearchByGenre(session_factory=_session_factory)


def _genre_search_return(records: list[MagicMock]) -> list[tuple[MagicMock, float]]:
    """Build a realistic _genre_search return value from records."""
    return [(r, round(0.85 - i * 0.05, 4)) for i, r in enumerate(records)]


# ---------------------------------------------------------------------------
# Tool properties
# ---------------------------------------------------------------------------


class TestSearchByGenreProperties:
    """Test tool interface contract."""

    def test_tool_name(self):
        """Tool name must be exactly 'search_by_genre'."""
        tool = SearchByGenre()
        assert tool.name == "search_by_genre"

    def test_description_mentions_key_concepts(self):
        """Description should mention genre and search."""
        tool = SearchByGenre()
        desc = tool.description.lower()
        assert "genre" in desc
        assert "search" in desc

    def test_has_three_parameters(self):
        """Tool should expose genre, query, top_k."""
        tool = SearchByGenre()
        names = [p.name for p in tool.parameters]
        assert "genre" in names
        assert "query" in names
        assert "top_k" in names

    def test_genre_is_required(self):
        """genre parameter must be required."""
        tool = SearchByGenre()
        genre_param = next(p for p in tool.parameters if p.name == "genre")
        assert genre_param.required is True

    def test_query_is_optional_with_empty_default(self):
        """query parameter should be optional with empty string default."""
        tool = SearchByGenre()
        query_param = next(p for p in tool.parameters if p.name == "query")
        assert query_param.required is False
        assert query_param.default == ""

    def test_top_k_is_optional_with_default_5(self):
        """top_k should default to 5."""
        tool = SearchByGenre()
        top_k_param = next(p for p in tool.parameters if p.name == "top_k")
        assert top_k_param.required is False
        assert top_k_param.default == 5


# ---------------------------------------------------------------------------
# Input validation — domain errors
# ---------------------------------------------------------------------------


class TestSearchByGenreValidation:
    """Test domain-level input validation (no DB needed)."""

    def _tool(self) -> SearchByGenre:
        """Return a tool wired to a mock session."""
        return _make_tool()

    def test_empty_genre_rejected(self):
        """Empty genre string should return error."""
        result = self._tool()(genre="", query="chords")
        assert result.success is False
        assert "genre" in result.error.lower()

    def test_whitespace_only_genre_rejected(self):
        """Whitespace-only genre should return error."""
        result = self._tool()(genre="   ", query="chords")
        assert result.success is False

    def test_genre_too_long_rejected(self):
        """Genre exceeding MAX_GENRE_LENGTH should return error."""
        result = self._tool()(genre="g" * (MAX_GENRE_LENGTH + 1))
        assert result.success is False
        assert str(MAX_GENRE_LENGTH) in result.error

    def test_query_too_long_rejected(self):
        """Query exceeding MAX_QUERY_LENGTH should return error."""
        result = self._tool()(genre="techno", query="q" * (MAX_QUERY_LENGTH + 1))
        assert result.success is False
        assert str(MAX_QUERY_LENGTH) in result.error

    def test_top_k_below_minimum_rejected(self):
        """top_k < MIN_TOP_K should return error."""
        result = self._tool()(genre="techno", top_k=MIN_TOP_K - 1)
        assert result.success is False
        # Validation fires before DB — no import needed
        assert result.error  # error message is present

    def test_top_k_above_maximum_rejected(self):
        """top_k > MAX_TOP_K should return error."""
        result = self._tool()(genre="techno", top_k=MAX_TOP_K + 1)
        assert result.success is False
        assert str(MAX_TOP_K) in result.error

    def test_missing_genre_returns_validation_error(self):
        """Missing required genre should fail base class validation."""
        result = self._tool()(query="chords")
        assert result.success is False
        assert "genre" in result.error

    def test_wrong_type_top_k_returns_validation_error(self):
        """String passed as top_k should fail type validation."""
        result = self._tool()(genre="techno", top_k="five")
        assert result.success is False
        assert "int" in result.error


# ---------------------------------------------------------------------------
# _expand_genre — pure function
# ---------------------------------------------------------------------------


class TestExpandGenre:
    """Test genre alias expansion (pure function — no I/O)."""

    def test_known_genre_returns_aliases(self):
        """'organic house' should return its known aliases."""
        terms = _expand_genre("organic house")
        assert "organic" in terms
        assert "organic house" in terms
        assert "all day i dream" in terms

    def test_partial_match_returns_aliases(self):
        """'organic' alone matches the 'organic house' canonical."""
        terms = _expand_genre("organic")
        assert isinstance(terms, list)
        assert len(terms) > 1

    def test_known_genre_case_insensitive(self):
        """Genre matching should be case-insensitive."""
        terms_lower = _expand_genre("techno")
        terms_upper = _expand_genre("TECHNO")
        assert set(terms_lower) == set(terms_upper)

    def test_unknown_genre_returns_self_and_words(self):
        """Unknown genre → [genre] + individual words (no duplicates)."""
        terms = _expand_genre("nu jazz")
        assert "nu jazz" in terms
        assert "nu" in terms
        assert "jazz" in terms

    def test_unknown_single_word_no_duplicates(self):
        """Single-word unknown genre → no duplicate entries."""
        terms = _expand_genre("ambient")
        assert terms.count("ambient") == 1

    def test_returns_list(self):
        """_expand_genre always returns a list."""
        terms = _expand_genre("techno")
        assert isinstance(terms, list)

    def test_acid_aliases(self):
        """'acid' should expand to include '303'."""
        terms = _expand_genre("acid")
        assert "303" in terms

    def test_melodic_house_aliases(self):
        """'melodic house' should include 'anjunadeep'."""
        terms = _expand_genre("melodic house")
        assert "anjunadeep" in terms

    def test_deep_house_aliases(self):
        """'deep house' should include 'soulful'."""
        terms = _expand_genre("deep house")
        assert "soulful" in terms


# ---------------------------------------------------------------------------
# Happy path — successful search
# ---------------------------------------------------------------------------


class TestSearchByGenreHappyPath:
    """Test successful search results with mocked DB + _genre_search."""

    def test_basic_search_returns_success(self):
        """Should return success with results list."""
        records = [_make_mock_record(text="organic house chord progression") for _ in range(3)]
        tool = _make_tool(records)
        with patch(_PATCH_TARGET, return_value=_genre_search_return(records)):
            result = tool(genre="organic house", query="chord progressions", top_k=3)
        assert result.success is True
        assert "results" in result.data
        assert "total_found" in result.data

    def test_result_count_matches_records(self):
        """total_found should match number of records returned."""
        records = [_make_mock_record() for _ in range(5)]
        tool = _make_tool(records)
        with patch(_PATCH_TARGET, return_value=_genre_search_return(records)):
            result = tool(genre="techno", top_k=5)
        assert result.data["total_found"] == 5

    def test_genre_echoed_in_response(self):
        """data['genre'] should match the input genre."""
        records = [_make_mock_record()]
        tool = _make_tool(records)
        with patch(_PATCH_TARGET, return_value=_genre_search_return(records)):
            result = tool(genre="deep house", query="bass lines")
        assert result.data["genre"] == "deep house"

    def test_query_echoed_in_response(self):
        """data['query'] should match the input query."""
        records = [_make_mock_record()]
        tool = _make_tool(records)
        with patch(_PATCH_TARGET, return_value=_genre_search_return(records)):
            result = tool(genre="techno", query="kick drum patterns")
        assert result.data["query"] == "kick drum patterns"

    def test_metadata_contains_genre_terms(self):
        """metadata should include genre_terms used for filtering."""
        records = [_make_mock_record()]
        tool = _make_tool(records)
        with patch(_PATCH_TARGET, return_value=_genre_search_return(records)):
            result = tool(genre="acid")
        assert "genre_terms" in result.metadata
        assert isinstance(result.metadata["genre_terms"], list)
        assert len(result.metadata["genre_terms"]) > 0

    def test_metadata_contains_effective_query(self):
        """metadata should include effective_query (genre + query combined)."""
        records = [_make_mock_record()]
        tool = _make_tool(records)
        with patch(_PATCH_TARGET, return_value=_genre_search_return(records)):
            result = tool(genre="techno", query="kick design")
        assert "effective_query" in result.metadata
        assert "techno" in result.metadata["effective_query"]
        assert "kick design" in result.metadata["effective_query"]

    def test_effective_query_genre_only_when_no_query(self):
        """When query is omitted, effective_query should just be the genre."""
        records = [_make_mock_record()]
        tool = _make_tool(records)
        with patch(_PATCH_TARGET, return_value=_genre_search_return(records)):
            result = tool(genre="deep house")
        assert result.metadata["effective_query"] == "deep house"

    def test_result_chunks_have_required_fields(self):
        """Each result chunk must have index, source_name, score, text_preview."""
        records = [_make_mock_record(source_name="organic.pdf", text="A" * 300)]
        tool = _make_tool(records)
        with patch(_PATCH_TARGET, return_value=_genre_search_return(records)):
            result = tool(genre="organic house")
        assert len(result.data["results"]) == 1
        chunk = result.data["results"][0]
        assert "index" in chunk
        assert "source_name" in chunk
        assert "score" in chunk
        assert "text_preview" in chunk

    def test_text_preview_truncated_to_200_chars(self):
        """text_preview should be at most 200 characters."""
        long_text = "A" * 500
        records = [_make_mock_record(text=long_text)]
        tool = _make_tool(records)
        with patch(_PATCH_TARGET, return_value=_genre_search_return(records)):
            result = tool(genre="techno")
        preview = result.data["results"][0]["text_preview"]
        assert len(preview) <= 200

    def test_empty_results_still_success(self):
        """Zero results should still return success (not an error)."""
        tool = _make_tool(records=[])
        with patch(_PATCH_TARGET, return_value=[]):
            result = tool(genre="obscure genre nobody knows")
        assert result.success is True
        assert result.data["total_found"] == 0

    def test_query_optional_omitted(self):
        """Should work without query parameter."""
        records = [_make_mock_record()]
        tool = _make_tool(records)
        with patch(_PATCH_TARGET, return_value=_genre_search_return(records)):
            result = tool(genre="melodic house")
        assert result.success is True

    def test_top_k_boundary_values(self):
        """top_k=1 and top_k=20 should both be accepted."""
        records = [_make_mock_record()]
        tool = _make_tool(records)
        with patch(_PATCH_TARGET, return_value=_genre_search_return(records)):
            result_1 = tool(genre="techno", top_k=1)
        with patch(_PATCH_TARGET, return_value=_genre_search_return(records)):
            result_20 = tool(genre="techno", top_k=20)
        assert result_1.success is True
        assert result_20.success is True

    def test_chunk_index_is_one_based(self):
        """First result should have index=1, not 0."""
        records = [_make_mock_record()]
        tool = _make_tool(records)
        with patch(_PATCH_TARGET, return_value=_genre_search_return(records)):
            result = tool(genre="techno")
        assert result.data["results"][0]["index"] == 1

    def test_score_is_rounded_float(self):
        """Score should be a float rounded to 4 decimal places."""
        records = [_make_mock_record()]
        tool = _make_tool(records)
        with patch(_PATCH_TARGET, return_value=[(records[0], 0.123456789)]):
            result = tool(genre="techno")
        score = result.data["results"][0]["score"]
        assert isinstance(score, float)
        # Rounded to 4 decimal places
        assert score == round(score, 4)


# ---------------------------------------------------------------------------
# Database error handling
# ---------------------------------------------------------------------------


class TestSearchByGenreErrorHandling:
    """Test graceful degradation on DB failures."""

    def test_genre_search_exception_returns_failure(self):
        """_genre_search raising exception → success=False with error message."""
        tool = _make_tool()
        with patch(_PATCH_TARGET, side_effect=Exception("DB connection lost")):
            result = tool(genre="techno")
        assert result.success is False
        assert "failed" in result.error.lower()
