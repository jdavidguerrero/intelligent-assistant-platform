"""Tests for eval/runner.py — EvalRunner and QueryResult behaviour.

EvalRunner makes live HTTP calls via FastAPI TestClient.  All tests here
either construct QueryResult objects directly (unit tests) or mock the
TestClient to avoid real network calls and database access.

No real /ask calls are made.  All tests are deterministic and fast.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from eval.dataset import Difficulty, GoldenQuery, SubDomain
from eval.runner import EvalRunner, QueryResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_golden_query(
    qid: str = "mix_001",
    adversarial: bool = False,
    sub_domain: SubDomain = SubDomain.MIXING,
    expected_topics: list[str] | None = None,
    expected_sources: list[str] | None = None,
) -> GoldenQuery:
    """Construct a minimal GoldenQuery for testing."""
    return GoldenQuery(
        id=qid,
        question="How do you use EQ to separate kick and bass frequencies?",
        expected_topics=expected_topics if expected_topics is not None else ["eq", "frequency"],
        expected_sources=expected_sources if expected_sources is not None else ["pete-tong", "mixing"],
        sub_domain=sub_domain,
        difficulty=Difficulty.EASY,
        adversarial=adversarial,
    )


def _make_ask_200_response(
    answer: str = "Use EQ to separate kick and bass by cutting around 200Hz.",
    sources: list[dict] | None = None,
    citations: list[dict] | None = None,
    mode: str = "rag",
    warnings: list[str] | None = None,
) -> dict:
    """Build a fake /ask 200 response payload."""
    return {
        "answer": answer,
        "sources": sources if sources is not None else [
            {"source_name": "pete-tong-mixing.pdf"},
            {"source_name": "mixing-guide.pdf"},
        ],
        "citations": citations if citations is not None else [{"index": 1, "source": "pete-tong-mixing.pdf"}],
        "mode": mode,
        "warnings": warnings or [],
    }


def _make_ask_422_response(detail: str = "insufficient_knowledge") -> dict:
    """Build a fake /ask 422 response payload."""
    return {"detail": detail}


# ---------------------------------------------------------------------------
# QueryResult unit tests (no runner, no HTTP)
# ---------------------------------------------------------------------------

class TestQueryResult:
    """Unit tests for QueryResult properties and methods."""

    def test_success_true_on_200(self) -> None:
        """success property returns True for HTTP 200."""
        query = _make_golden_query()
        result = QueryResult(
            query=query,
            status_code=200,
            answer="Use EQ to separate kick and bass frequency.",
            sources=["pete-tong.pdf"],
            citations=[],
            mode="rag",
            latency_ms=50.0,
        )
        assert result.success is True

    def test_success_false_on_non_200(self) -> None:
        """success property returns False for HTTP 422."""
        query = _make_golden_query()
        result = QueryResult(
            query=query,
            status_code=422,
            answer="",
            sources=[],
            citations=[],
            mode="refused",
            latency_ms=20.0,
        )
        assert result.success is False

    def test_correctly_refused_adversarial_422(self) -> None:
        """correctly_refused is True for adversarial query with 422."""
        query = _make_golden_query(
            adversarial=True,
            sub_domain=SubDomain.ADVERSARIAL,
            expected_topics=[],
            expected_sources=[],
        )
        result = QueryResult(
            query=query,
            status_code=422,
            answer="",
            sources=[],
            citations=[],
            mode="refused",
            latency_ms=15.0,
        )
        assert result.correctly_refused is True

    def test_correctly_refused_false_for_non_adversarial(self) -> None:
        """correctly_refused is False for a non-adversarial 422."""
        query = _make_golden_query(adversarial=False)
        result = QueryResult(
            query=query,
            status_code=422,
            answer="",
            sources=[],
            citations=[],
            mode="refused",
            latency_ms=15.0,
        )
        assert result.correctly_refused is False

    def test_correctly_refused_false_when_200(self) -> None:
        """correctly_refused is False for an adversarial query that returned 200."""
        query = _make_golden_query(
            adversarial=True,
            sub_domain=SubDomain.ADVERSARIAL,
            expected_topics=[],
            expected_sources=[],
        )
        result = QueryResult(
            query=query,
            status_code=200,
            answer="Here is an answer...",
            sources=[],
            citations=[],
            mode="rag",
            latency_ms=60.0,
        )
        assert result.correctly_refused is False

    def test_runner_topic_hit_true(self) -> None:
        """topic_hit() returns True when at least one expected topic appears in the answer."""
        query = _make_golden_query(expected_topics=["eq", "frequency"])
        result = QueryResult(
            query=query,
            status_code=200,
            answer="Use EQ to cut at the conflicting frequency range.",
            sources=[],
            citations=[],
            mode="rag",
            latency_ms=30.0,
        )
        assert result.topic_hit() is True

    def test_runner_topic_miss(self) -> None:
        """topic_hit() returns False when no expected topic appears in the answer."""
        query = _make_golden_query(expected_topics=["eq", "frequency"])
        result = QueryResult(
            query=query,
            status_code=200,
            answer="Use a reverb to add depth to the mix.",
            sources=[],
            citations=[],
            mode="rag",
            latency_ms=30.0,
        )
        assert result.topic_hit() is False

    def test_runner_topic_hit_case_insensitive(self) -> None:
        """topic_hit() matching is case-insensitive."""
        query = _make_golden_query(expected_topics=["EQ", "Frequency"])
        result = QueryResult(
            query=query,
            status_code=200,
            answer="apply eq to the frequency range below 200hz.",
            sources=[],
            citations=[],
            mode="rag",
            latency_ms=30.0,
        )
        assert result.topic_hit() is True

    def test_runner_topic_hit_empty_expected(self) -> None:
        """topic_hit() returns False when expected_topics is empty."""
        query = _make_golden_query(expected_topics=[])
        result = QueryResult(
            query=query,
            status_code=200,
            answer="Some answer text.",
            sources=[],
            citations=[],
            mode="rag",
            latency_ms=30.0,
        )
        assert result.topic_hit() is False

    def test_runner_topics_found_returns_matching_topics(self) -> None:
        """topics_found() returns the subset of expected topics present in the answer."""
        query = _make_golden_query(expected_topics=["eq", "frequency", "compressor"])
        result = QueryResult(
            query=query,
            status_code=200,
            answer="Apply EQ to the frequency spectrum.",
            sources=[],
            citations=[],
            mode="rag",
            latency_ms=30.0,
        )
        found = result.topics_found()
        assert "eq" in found
        assert "frequency" in found
        assert "compressor" not in found

    def test_runner_sources_extracted(self) -> None:
        """sources list is stored correctly on the QueryResult."""
        query = _make_golden_query()
        sources = ["pete-tong-mixing.pdf", "bob-katz-mastering.pdf"]
        result = QueryResult(
            query=query,
            status_code=200,
            answer="Use EQ.",
            sources=sources,
            citations=[],
            mode="rag",
            latency_ms=40.0,
        )
        assert result.sources == sources

    def test_error_defaults_to_empty_string(self) -> None:
        """error field defaults to empty string when not provided."""
        query = _make_golden_query()
        result = QueryResult(
            query=query,
            status_code=200,
            answer="Answer.",
            sources=[],
            citations=[],
            mode="rag",
            latency_ms=10.0,
        )
        assert result.error == ""

    def test_warnings_defaults_to_empty_list(self) -> None:
        """warnings field defaults to empty list when not provided."""
        query = _make_golden_query()
        result = QueryResult(
            query=query,
            status_code=200,
            answer="Answer.",
            sources=[],
            citations=[],
            mode="rag",
            latency_ms=10.0,
        )
        assert result.warnings == []


# ---------------------------------------------------------------------------
# EvalRunner integration tests with mocked client
# ---------------------------------------------------------------------------

class TestEvalRunner:
    """Tests for EvalRunner using a mocked FastAPI TestClient."""

    def _mock_client_200(
        self,
        answer: str = "Use EQ to separate kick and bass frequency.",
        source_names: list[str] | None = None,
    ) -> MagicMock:
        """Build a mock TestClient that returns a successful /ask response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_ask_200_response(
            answer=answer,
            sources=[{"source_name": s} for s in (source_names or ["pete-tong-course.pdf"])],
        )
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        return mock_client

    def _mock_client_422(self, detail: str = "insufficient_knowledge") -> MagicMock:
        """Build a mock TestClient that returns a 422 refusal."""
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.json.return_value = _make_ask_422_response(detail)
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        return mock_client

    def _mock_client_raises(self, exc: Exception) -> MagicMock:
        """Build a mock TestClient that raises an exception on post()."""
        mock_client = MagicMock()
        mock_client.post.side_effect = exc
        return mock_client

    def test_runner_successful_query(self) -> None:
        """A mocked 200 response produces a QueryResult with success=True."""
        runner = EvalRunner()
        runner._make_client = lambda: self._mock_client_200()
        query = _make_golden_query()

        results = runner.run(dataset=[query])

        assert len(results) == 1
        r = results[0]
        assert r.success is True
        assert r.status_code == 200

    def test_runner_answer_extracted(self) -> None:
        """answer is extracted from the /ask response body."""
        runner = EvalRunner()
        runner._make_client = lambda: self._mock_client_200(
            answer="Apply EQ at 200Hz for kick-bass separation."
        )
        query = _make_golden_query()
        results = runner.run(dataset=[query])
        assert results[0].answer == "Apply EQ at 200Hz for kick-bass separation."

    def test_runner_sources_extracted_from_response(self) -> None:
        """sources are extracted from the /ask response sources list."""
        runner = EvalRunner()
        runner._make_client = lambda: self._mock_client_200(
            source_names=["pete-tong.pdf", "mixing-guide.pdf"]
        )
        query = _make_golden_query()
        results = runner.run(dataset=[query])
        assert "pete-tong.pdf" in results[0].sources
        assert "mixing-guide.pdf" in results[0].sources

    def test_runner_refused_query(self) -> None:
        """A mocked 422 response produces a QueryResult with status_code=422."""
        runner = EvalRunner()
        runner._make_client = lambda: self._mock_client_422()
        query = _make_golden_query()

        results = runner.run(dataset=[query])

        assert results[0].status_code == 422
        assert results[0].success is False

    def test_runner_refused_answer_is_empty(self) -> None:
        """On 422, the answer field should be empty string."""
        runner = EvalRunner()
        runner._make_client = lambda: self._mock_client_422()
        query = _make_golden_query()
        results = runner.run(dataset=[query])
        assert results[0].answer == ""

    def test_runner_correctly_refused_adversarial(self) -> None:
        """Adversarial query + 422 response → correctly_refused=True."""
        runner = EvalRunner()
        runner._make_client = lambda: self._mock_client_422()
        query = _make_golden_query(
            adversarial=True,
            sub_domain=SubDomain.ADVERSARIAL,
            expected_topics=[],
            expected_sources=[],
        )

        results = runner.run(dataset=[query])

        assert results[0].correctly_refused is True

    def test_runner_error_handling(self) -> None:
        """Exception during request → status_code=0, error non-empty, no crash."""
        runner = EvalRunner()
        runner._make_client = lambda: self._mock_client_raises(
            ConnectionError("Connection refused")
        )
        query = _make_golden_query()

        results = runner.run(dataset=[query])

        assert len(results) == 1
        r = results[0]
        assert r.status_code == 0
        assert r.error != ""
        assert "Connection refused" in r.error

    def test_runner_error_mode_is_error(self) -> None:
        """On exception, mode is set to 'error'."""
        runner = EvalRunner()
        runner._make_client = lambda: self._mock_client_raises(
            TimeoutError("Request timed out")
        )
        query = _make_golden_query()
        results = runner.run(dataset=[query])
        assert results[0].mode == "error"

    def test_runner_error_sources_empty(self) -> None:
        """On exception, sources list is empty."""
        runner = EvalRunner()
        runner._make_client = lambda: self._mock_client_raises(RuntimeError("boom"))
        query = _make_golden_query()
        results = runner.run(dataset=[query])
        assert results[0].sources == []

    def test_runner_processes_multiple_queries(self) -> None:
        """Runner processes all queries in dataset and returns one result each."""
        runner = EvalRunner()
        runner._make_client = lambda: self._mock_client_200()
        queries = [
            _make_golden_query("mix_001"),
            _make_golden_query("mix_002"),
            _make_golden_query("sd_001"),
        ]
        results = runner.run(dataset=queries)
        assert len(results) == 3
        result_ids = [r.query.id for r in results]
        assert result_ids == ["mix_001", "mix_002", "sd_001"]

    def test_runner_mode_forwarded(self) -> None:
        """mode field from the response body is stored on QueryResult."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "answer": "Answer text about EQ.",
            "sources": [],
            "citations": [],
            "mode": "tool",
            "warnings": [],
        }
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp

        runner = EvalRunner()
        runner._make_client = lambda: mock_client
        results = runner.run(dataset=[_make_golden_query()])
        assert results[0].mode == "tool"

    def test_runner_warnings_forwarded(self) -> None:
        """warnings list from the response body is stored on QueryResult."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "answer": "Answer about EQ.",
            "sources": [],
            "citations": [],
            "mode": "rag",
            "warnings": ["low_confidence", "invalid_citations"],
        }
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp

        runner = EvalRunner()
        runner._make_client = lambda: mock_client
        results = runner.run(dataset=[_make_golden_query()])
        assert "low_confidence" in results[0].warnings
        assert "invalid_citations" in results[0].warnings

    def test_runner_latency_recorded(self) -> None:
        """latency_ms is a non-negative float."""
        runner = EvalRunner()
        runner._make_client = lambda: self._mock_client_200()
        results = runner.run(dataset=[_make_golden_query()])
        assert results[0].latency_ms >= 0.0

    def test_runner_query_reference_preserved(self) -> None:
        """The original GoldenQuery is stored on the QueryResult."""
        runner = EvalRunner()
        runner._make_client = lambda: self._mock_client_200()
        query = _make_golden_query("unique_id_xyz")
        results = runner.run(dataset=[query])
        assert results[0].query is query

    def test_runner_empty_dataset(self) -> None:
        """Running with an empty dataset returns an empty list."""
        runner = EvalRunner()
        runner._make_client = lambda: self._mock_client_200()
        results = runner.run(dataset=[])
        assert results == []

    def test_runner_error_detail_extracted(self) -> None:
        """On non-200, error is populated from the 'detail' field in response JSON."""
        runner = EvalRunner()
        runner._make_client = lambda: self._mock_client_422("insufficient_knowledge")
        query = _make_golden_query()
        results = runner.run(dataset=[query])
        assert results[0].error == "insufficient_knowledge"
