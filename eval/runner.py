"""Evaluation runner — batch query executor.

Sends all 50 golden queries to the /ask endpoint via FastAPI TestClient
and collects raw results.  Does NOT score — scoring is handled by
``judge.py`` and ``retrieval_metrics.py``.

Usage
-----
    runner = EvalRunner(confidence_threshold=0.58, top_k=5)
    results = runner.run(dataset=GOLDEN_DATASET, verbose=True)
    # results is a list[QueryResult]
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from .dataset import GoldenQuery

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Raw result from executing one golden query.

    Attributes
    ----------
    query:
        The original ``GoldenQuery``.
    status_code:
        HTTP status code from /ask.
    answer:
        The answer text (empty string on non-200 responses).
    sources:
        List of source names returned by /ask (order preserved = relevance order).
    citations:
        List of citation dicts returned by /ask.
    mode:
        ``"rag"`` | ``"tool"`` | ``"degraded"`` | ``"unknown"``.
    latency_ms:
        Wall-clock time in milliseconds.
    error:
        Error message if the request itself failed (network/timeout).
    warnings:
        Warnings list from the /ask response.
    """

    query: GoldenQuery
    status_code: int
    answer: str
    sources: list[str]
    citations: list[dict]
    mode: str
    latency_ms: float
    error: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """True if the query returned HTTP 200."""
        return self.status_code == 200

    @property
    def correctly_refused(self) -> bool:
        """True if adversarial query was correctly refused (422)."""
        return self.query.adversarial and self.status_code == 422

    def topics_found(self) -> list[str]:
        """Return which expected topics appear in the answer (case-insensitive)."""
        answer_lower = self.answer.lower()
        return [t for t in self.query.expected_topics if t.lower() in answer_lower]

    def topic_hit(self) -> bool:
        """True if at least one expected topic appears in the answer."""
        return len(self.topics_found()) > 0


class EvalRunner:
    """Execute the golden dataset against the /ask endpoint.

    Parameters
    ----------
    confidence_threshold:
        Forwarded to the /ask request payload.
    top_k:
        Number of chunks to retrieve per query.
    use_tools:
        Whether to enable the tool-first pipeline.  Defaults to True.
    query_delay_s:
        Seconds to sleep between queries.  Use to avoid hitting LLM
        rate limits (e.g. OpenAI TPM) when running large eval batches.
        Defaults to 0 (no delay).
    """

    def __init__(
        self,
        confidence_threshold: float = 0.58,
        top_k: int = 5,
        use_tools: bool = True,
        query_delay_s: float = 0.0,
    ) -> None:
        self._threshold = confidence_threshold
        self._top_k = top_k
        self._use_tools = use_tools
        self._query_delay_s = query_delay_s

    def _make_client(self):  # type: ignore[return]
        """Lazy-import TestClient to avoid import at module level."""
        from fastapi.testclient import TestClient  # noqa: PLC0415

        from api.main import app  # noqa: PLC0415

        return TestClient(app)

    def run(
        self,
        dataset: list[GoldenQuery] | None = None,
        verbose: bool = False,
    ) -> list[QueryResult]:
        """Execute all queries and return raw results.

        Parameters
        ----------
        dataset:
            Subset to run.  Defaults to the full ``GOLDEN_DATASET``.
        verbose:
            Print progress to stdout.
        """
        from .dataset import GOLDEN_DATASET  # noqa: PLC0415

        queries = dataset if dataset is not None else GOLDEN_DATASET
        client = self._make_client()
        results: list[QueryResult] = []

        for i, query in enumerate(queries, start=1):
            if verbose:
                print(f"  [{i:02d}/{len(queries)}] {query.id}: {query.question[:60]}...")

            if i > 1 and self._query_delay_s > 0:
                time.sleep(self._query_delay_s)

            start = time.perf_counter()
            try:
                resp = client.post(
                    "/ask",
                    json={
                        "query": query.question,
                        "top_k": self._top_k,
                        "confidence_threshold": self._threshold,
                        "use_tools": self._use_tools,
                        "session_id": f"eval_{query.id}",
                    },
                )
                elapsed_ms = (time.perf_counter() - start) * 1000
                data = resp.json()

                if resp.status_code == 200:
                    result = QueryResult(
                        query=query,
                        status_code=200,
                        answer=data.get("answer", ""),
                        sources=[s.get("source_name", "") for s in data.get("sources", [])],
                        citations=data.get("citations", []),
                        mode=data.get("mode", "unknown"),
                        latency_ms=elapsed_ms,
                        warnings=data.get("warnings", []),
                    )
                else:
                    result = QueryResult(
                        query=query,
                        status_code=resp.status_code,
                        answer="",
                        sources=[],
                        citations=[],
                        mode="refused",
                        latency_ms=elapsed_ms,
                        error=str(data.get("detail", "")),
                    )

            except Exception as exc:  # noqa: BLE001
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.error("Query %s failed: %s", query.id, exc)
                result = QueryResult(
                    query=query,
                    status_code=0,
                    answer="",
                    sources=[],
                    citations=[],
                    mode="error",
                    latency_ms=elapsed_ms,
                    error=str(exc),
                )

            results.append(result)

            if verbose:
                status_icon = "✓" if result.success or result.correctly_refused else "✗"
                print(
                    f"         {status_icon} HTTP {result.status_code} | "
                    f"{result.latency_ms:.0f}ms | "
                    f"sources={len(result.sources)}"
                )

        return results
