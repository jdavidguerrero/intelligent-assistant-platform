"""Tests for eval/report.py — scoring, report building, rendering, and serialisation.

All report functions are pure (no I/O), so tests are fully deterministic.
QueryResult objects are constructed directly without network calls.
JudgeScore is built manually to exercise judge-augmented code paths.
"""

from __future__ import annotations

import json

from eval.dataset import Difficulty, GoldenQuery, SubDomain
from eval.judge import JudgeScore
from eval.report import (
    EvalReport,
    QueryScore,
    build_report,
    render_report,
    report_to_dict,
    score_results,
)
from eval.runner import QueryResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_golden_query(
    qid: str = "test_001",
    sub_domain: SubDomain = SubDomain.MIXING,
    adversarial: bool = False,
    expected_topics: list[str] | None = None,
    expected_sources: list[str] | None = None,
) -> GoldenQuery:
    """Create a minimal GoldenQuery for testing."""
    return GoldenQuery(
        id=qid,
        question="What is EQ?",
        expected_topics=expected_topics if expected_topics is not None else ["eq", "frequency"],
        expected_sources=expected_sources if expected_sources is not None else ["pete-tong", "mixing"],
        sub_domain=sub_domain,
        difficulty=Difficulty.EASY,
        adversarial=adversarial,
    )


def _make_query_result(
    query: GoldenQuery,
    status_code: int = 200,
    answer: str = "Use EQ to separate kick and bass frequencies.",
    sources: list[str] | None = None,
) -> QueryResult:
    """Create a QueryResult without touching any real HTTP stack."""
    return QueryResult(
        query=query,
        status_code=status_code,
        answer=answer,
        sources=sources if sources is not None else ["pete-tong-course.pdf"],
        citations=[],
        mode="rag",
        latency_ms=42.0,
        warnings=[],
    )


def _make_judge_score(
    musical_accuracy: int = 4,
    relevance: int = 4,
    actionability: int = 4,
    verdict: str = "PASS",
) -> JudgeScore:
    """Create a JudgeScore without calling the LLM."""
    return JudgeScore(
        musical_accuracy=musical_accuracy,
        relevance=relevance,
        actionability=actionability,
        reasoning="Test judge score.",
        verdict=verdict,
    )


# ---------------------------------------------------------------------------
# score_results()
# ---------------------------------------------------------------------------

class TestScoreResults:
    """Tests for score_results() — converts raw QueryResult list to QueryScore list."""

    def test_score_results_basic(self) -> None:
        """score_results without judge scores produces QueryScore list with correct ids."""
        query = _make_golden_query()
        result = _make_query_result(query, answer="Use EQ to set frequency and eq balance.")
        scores = score_results([result])
        assert len(scores) == 1
        assert scores[0].query_id == "test_001"
        assert scores[0].sub_domain == SubDomain.MIXING.value

    def test_score_results_with_judge(self) -> None:
        """Judge scores are carried through into QueryScore fields."""
        query = _make_golden_query()
        result = _make_query_result(query)
        judge = _make_judge_score(musical_accuracy=5, relevance=4, actionability=3, verdict="PASS")
        scores = score_results([result], judge_scores=[judge])
        assert scores[0].musical_accuracy == 5.0
        assert scores[0].relevance == 4.0
        assert scores[0].actionability == 3.0
        assert scores[0].verdict == "PASS"

    def test_score_results_no_judge_fields_default_to_zero(self) -> None:
        """Without judge scores, judge metric fields default to 0.0."""
        query = _make_golden_query()
        result = _make_query_result(query, answer="eq frequency analysis is key.")
        scores = score_results([result])
        assert scores[0].musical_accuracy == 0.0
        assert scores[0].relevance == 0.0
        assert scores[0].actionability == 0.0

    def test_score_results_precision_computed(self) -> None:
        """Retrieval precision_at_5 is computed from sources vs expected_sources."""
        query = _make_golden_query(expected_sources=["pete-tong"])
        result = _make_query_result(query, sources=["pete-tong-course.pdf", "unrelated.pdf"])
        scores = score_results([result])
        # 1 out of 2 returned sources is relevant → precision = 0.5
        assert scores[0].precision_at_5 == 0.5

    def test_score_results_multiple_queries(self) -> None:
        """score_results processes multiple results in order."""
        q1 = _make_golden_query("q1")
        q2 = _make_golden_query("q2")
        r1 = _make_query_result(q1, answer="eq frequency balance.")
        r2 = _make_query_result(q2, answer="eq frequency mixing.")
        scores = score_results([r1, r2])
        assert len(scores) == 2
        assert scores[0].query_id == "q1"
        assert scores[1].query_id == "q2"


class TestVerdictAssignment:
    """Tests for how verdicts are assigned based on query type and response."""

    def test_adversarial_correctly_refused_verdict(self) -> None:
        """Adversarial query + HTTP 422 → verdict = 'REFUSED'."""
        query = _make_golden_query(
            adversarial=True,
            sub_domain=SubDomain.ADVERSARIAL,
            expected_topics=[],
            expected_sources=[],
        )
        result = _make_query_result(query, status_code=422, answer="", sources=[])
        scores = score_results([result])
        assert scores[0].verdict == "REFUSED"

    def test_adversarial_not_refused_verdict(self) -> None:
        """Adversarial query that returns HTTP 200 → verdict = 'FAIL'."""
        query = _make_golden_query(
            adversarial=True,
            sub_domain=SubDomain.ADVERSARIAL,
            expected_topics=[],
            expected_sources=[],
        )
        result = _make_query_result(
            query, status_code=200, answer="Here is a detailed answer..."
        )
        scores = score_results([result])
        assert scores[0].verdict == "FAIL"

    def test_non_adversarial_pass_when_topic_hit(self) -> None:
        """Non-adversarial HTTP 200 with topic present → verdict = 'PASS' (no judge)."""
        query = _make_golden_query(expected_topics=["eq", "frequency"])
        result = _make_query_result(query, answer="Apply eq to fix the frequency clash.")
        scores = score_results([result])
        assert scores[0].verdict == "PASS"

    def test_non_adversarial_partial_when_no_topic_hit(self) -> None:
        """Non-adversarial HTTP 200 but no topic hit → verdict = 'PARTIAL' (no judge)."""
        query = _make_golden_query(expected_topics=["eq", "frequency"])
        result = _make_query_result(query, answer="Use a compressor on the drum bus.")
        scores = score_results([result])
        assert scores[0].verdict == "PARTIAL"

    def test_non_adversarial_fail_on_non_200(self) -> None:
        """Non-adversarial HTTP 500 → verdict = 'FAIL' (no judge)."""
        query = _make_golden_query()
        result = _make_query_result(query, status_code=500, answer="", sources=[])
        scores = score_results([result])
        assert scores[0].verdict == "FAIL"

    def test_judge_verdict_overrides_fallback(self) -> None:
        """When judge is present, the judge's verdict is used instead of fallback."""
        query = _make_golden_query(expected_topics=["eq"])
        result = _make_query_result(query, answer="Use eq to balance the frequency.")
        # Judge says PARTIAL even though fallback would say PASS
        judge = _make_judge_score(verdict="PARTIAL")
        scores = score_results([result], judge_scores=[judge])
        assert scores[0].verdict == "PARTIAL"


# ---------------------------------------------------------------------------
# build_report()
# ---------------------------------------------------------------------------

class TestBuildReport:
    """Tests for build_report() — assembles EvalReport from QueryScore list."""

    def _make_score(
        self,
        query_id: str,
        sub_domain: str,
        verdict: str,
        adversarial: bool = False,
        precision: float = 0.8,
        recall: float = 0.8,
        mrr_score: float = 0.8,
    ) -> QueryScore:
        """Helper to build a minimal QueryScore."""
        return QueryScore(
            query_id=query_id,
            sub_domain=sub_domain,
            difficulty="easy",
            adversarial=adversarial,
            status_code=200 if verdict != "FAIL" else 422,
            topic_hit=verdict == "PASS",
            precision_at_5=precision,
            recall_at_5=recall,
            mrr_score=mrr_score,
            musical_accuracy=0.0,
            relevance=0.0,
            actionability=0.0,
            verdict=verdict,
            latency_ms=50.0,
        )

    def test_build_report_pass_rate(self) -> None:
        """Overall pass rate = PASS count / non-adversarial total."""
        scores = [
            self._make_score("q1", "mixing", "PASS"),
            self._make_score("q2", "mixing", "PASS"),
            self._make_score("q3", "mixing", "FAIL"),
            self._make_score("q4", "mixing", "PARTIAL"),
        ]
        report = build_report(scores)
        # 2 PASS out of 4 non-adversarial → 0.5
        assert report.overall_pass_rate == pytest.approx(0.5)

    def test_build_report_adversarial_pass_rate(self) -> None:
        """Adversarial pass rate = REFUSED count / adversarial total."""
        scores = [
            self._make_score("adv1", "adversarial", "REFUSED", adversarial=True),
            self._make_score("adv2", "adversarial", "REFUSED", adversarial=True),
            self._make_score("adv3", "adversarial", "FAIL", adversarial=True),
        ]
        report = build_report(scores)
        assert report.adversarial_pass_rate == pytest.approx(2 / 3)

    def test_build_report_subdomain_summaries(self) -> None:
        """Sub-domain summaries are present for every sub-domain that has scores."""
        scores = [
            self._make_score("m1", "mixing", "PASS"),
            self._make_score("m2", "mixing", "FAIL"),
            self._make_score("sd1", "sound_design", "PASS"),
        ]
        report = build_report(scores)
        assert "mixing" in report.sub_domain_summaries
        assert "sound_design" in report.sub_domain_summaries
        assert "arrangement" not in report.sub_domain_summaries

    def test_build_report_total_queries(self) -> None:
        """total_queries equals the length of the input scores list."""
        scores = [
            self._make_score("q1", "mixing", "PASS"),
            self._make_score("q2", "arrangement", "FAIL"),
        ]
        report = build_report(scores)
        assert report.total_queries == 2

    def test_build_report_run_metadata_forwarded(self) -> None:
        """run_metadata dict is stored verbatim on the report."""
        meta = {"timestamp": "2025-01-01", "version": "1.0"}
        scores = [self._make_score("q1", "mixing", "PASS")]
        report = build_report(scores, run_metadata=meta)
        assert report.run_metadata == meta

    def test_build_report_empty_scores(self) -> None:
        """Empty QueryScore list produces a zeroed-out report."""
        report = build_report([])
        assert report.total_queries == 0
        assert report.overall_pass_rate == pytest.approx(0.0)
        assert report.sub_domain_summaries == {}

    def test_build_report_subdomain_summary_counts(self) -> None:
        """Sub-domain summary counts (passed/partial/failed/total) are correct."""
        scores = [
            self._make_score("m1", "mixing", "PASS"),
            self._make_score("m2", "mixing", "PARTIAL"),
            self._make_score("m3", "mixing", "FAIL"),
        ]
        report = build_report(scores)
        summary = report.sub_domain_summaries["mixing"]
        assert summary.total == 3
        assert summary.passed == 1
        assert summary.partial == 1
        assert summary.failed == 1


import pytest  # noqa: E402  (needed for pytest.approx reference above)

# ---------------------------------------------------------------------------
# render_report()
# ---------------------------------------------------------------------------

class TestRenderReport:
    """Tests for render_report() — text rendering of EvalReport."""

    def _minimal_report(self) -> EvalReport:
        """Build a minimal EvalReport with one passing mixing query."""
        scores = [
            QueryScore(
                query_id="mix_001",
                sub_domain="mixing",
                difficulty="easy",
                adversarial=False,
                status_code=200,
                topic_hit=True,
                precision_at_5=1.0,
                recall_at_5=1.0,
                mrr_score=1.0,
                musical_accuracy=0.0,
                relevance=0.0,
                actionability=0.0,
                verdict="PASS",
                latency_ms=50.0,
            )
        ]
        return build_report(scores)

    def _report_with_failures(self) -> EvalReport:
        """Build a report that contains at least one FAIL verdict."""
        scores = [
            QueryScore(
                query_id="mix_fail",
                sub_domain="mixing",
                difficulty="easy",
                adversarial=False,
                status_code=500,
                topic_hit=False,
                precision_at_5=0.0,
                recall_at_5=0.0,
                mrr_score=0.0,
                musical_accuracy=0.0,
                relevance=0.0,
                actionability=0.0,
                verdict="FAIL",
                latency_ms=10.0,
            )
        ]
        return build_report(scores)

    def test_render_report_contains_overall_summary(self) -> None:
        """Rendered text must contain the 'OVERALL SUMMARY' section header."""
        rendered = render_report(self._minimal_report())
        assert "OVERALL SUMMARY" in rendered

    def test_render_report_contains_per_subdomain(self) -> None:
        """Rendered text must contain 'PER-SUB-DOMAIN' section header."""
        rendered = render_report(self._minimal_report())
        assert "PER-SUB-DOMAIN" in rendered

    def test_render_report_contains_failing_section_when_failures(self) -> None:
        """Rendered text contains 'FAILING' section when failures exist."""
        rendered = render_report(self._report_with_failures())
        assert "FAILING" in rendered

    def test_render_report_contains_query_id_in_failures(self) -> None:
        """Failing query ids appear in the rendered report."""
        rendered = render_report(self._report_with_failures())
        assert "mix_fail" in rendered

    def test_render_report_is_string(self) -> None:
        """render_report must return a plain str."""
        rendered = render_report(self._minimal_report())
        assert isinstance(rendered, str)

    def test_render_report_key_metrics_present(self) -> None:
        """Key metric labels appear in the rendered output."""
        rendered = render_report(self._minimal_report())
        for label in ("Precision@5", "Recall@5", "MRR"):
            assert label in rendered, f"Expected '{label}' in rendered report"


# ---------------------------------------------------------------------------
# report_to_dict()
# ---------------------------------------------------------------------------

class TestReportToDict:
    """Tests for report_to_dict() — JSON serialisability and structure."""

    def _sample_report(self) -> EvalReport:
        """Build a report covering both adversarial and non-adversarial queries."""
        scores = [
            QueryScore(
                query_id="mix_001",
                sub_domain="mixing",
                difficulty="easy",
                adversarial=False,
                status_code=200,
                topic_hit=True,
                precision_at_5=0.8,
                recall_at_5=0.6,
                mrr_score=1.0,
                musical_accuracy=0.0,
                relevance=0.0,
                actionability=0.0,
                verdict="PASS",
                latency_ms=45.0,
                warnings=["low_confidence"],
            ),
            QueryScore(
                query_id="adv_001",
                sub_domain="adversarial",
                difficulty="easy",
                adversarial=True,
                status_code=422,
                topic_hit=False,
                precision_at_5=0.0,
                recall_at_5=0.0,
                mrr_score=0.0,
                musical_accuracy=0.0,
                relevance=0.0,
                actionability=0.0,
                verdict="REFUSED",
                latency_ms=20.0,
            ),
        ]
        return build_report(scores)

    def test_report_to_dict_serializable(self) -> None:
        """report_to_dict() output must be JSON-serializable via json.dumps."""
        d = report_to_dict(self._sample_report())
        # Should not raise
        serialized = json.dumps(d)
        assert isinstance(serialized, str)

    def test_report_to_dict_top_level_keys(self) -> None:
        """Top-level keys match the documented contract."""
        d = report_to_dict(self._sample_report())
        expected_keys = {
            "total_queries",
            "overall_pass_rate",
            "adversarial_pass_rate",
            "overall_precision_at_5",
            "overall_recall_at_5",
            "overall_mrr",
            "overall_musical_accuracy",
            "overall_relevance",
            "overall_actionability",
            "mean_latency_ms",
            "run_metadata",
            "sub_domain_summaries",
            "query_scores",
        }
        assert set(d.keys()) == expected_keys

    def test_report_to_dict_query_scores_list(self) -> None:
        """query_scores in the dict is a list with one entry per scored query."""
        d = report_to_dict(self._sample_report())
        assert isinstance(d["query_scores"], list)
        assert len(d["query_scores"]) == 2

    def test_report_to_dict_query_score_fields(self) -> None:
        """Each query score dict contains the required fields."""
        d = report_to_dict(self._sample_report())
        first = d["query_scores"][0]
        for key in ("query_id", "sub_domain", "verdict", "status_code", "precision_at_5"):
            assert key in first, f"Missing key '{key}' in query_score dict"

    def test_report_to_dict_sub_domain_summaries_structure(self) -> None:
        """sub_domain_summaries is a dict keyed by domain name strings."""
        d = report_to_dict(self._sample_report())
        summaries = d["sub_domain_summaries"]
        assert isinstance(summaries, dict)
        assert "mixing" in summaries
        for key, val in summaries.items():
            assert isinstance(key, str)
            assert "pass_rate" in val

    def test_report_to_dict_roundtrip(self) -> None:
        """Values survive a JSON serialization/deserialization roundtrip."""
        original = report_to_dict(self._sample_report())
        restored = json.loads(json.dumps(original))
        assert restored["total_queries"] == original["total_queries"]
        assert restored["overall_pass_rate"] == pytest.approx(original["overall_pass_rate"])
