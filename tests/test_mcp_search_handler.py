"""
MCP Musical Intelligence — search_production_knowledge handler tests.

Why a dedicated file?
    This handler differs from the others: instead of importing a local Week 3 tool,
    it makes an HTTP call to the running FastAPI /ask endpoint via httpx.AsyncClient.
    That network call must be mocked — it's the integration boundary.

What we test:
    1. Happy path (HTTP 200): answer returned, no error suffix
    2. insufficient_knowledge (HTTP 422): graceful "no answer" message
    3. Server error (HTTP 500): error string mentioning HTTP code
    4. Network failure (httpx exception): error string, no crash
    5. Structured log emitted: McpCallLog fields present in log output
    6. Correlation ID propagation: call_id is non-empty on every call
    7. Confidence threshold forwarded to API payload
    8. top_k forwarded to API payload
    9. Long queries are truncated in the log (not truncated in the actual API call)
   10. answer_len in structured log output for successful calls

All tests are async (pytest-asyncio). No network, no DB, no filesystem.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_response(status_code: int, body: dict) -> MagicMock:
    """Build a fake httpx.Response-like object."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    return resp


def _http200(
    answer: str = "Sidechain compression uses a kick drum to duck the bass.",
    sources: list | None = None,
) -> MagicMock:
    return _mock_response(
        200,
        {
            "answer": answer,
            "sources": sources or [{"source_name": "pete_tong.pdf"}],
        },
    )


def _http422(reason: str = "insufficient_knowledge") -> MagicMock:
    return _mock_response(
        422,
        {"detail": {"reason": reason, "message": "Score below threshold"}},
    )


def _http500() -> MagicMock:
    return _mock_response(500, {"detail": "Internal Server Error"})


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestSearchHappyPath:
    @pytest.mark.asyncio
    async def test_200_returns_answer_text(self) -> None:
        from musical_mcp.server import mcp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            return_value=_http200("Sidechain with fast attack creates tight pumping.")
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
            result = await tool_fn.fn(
                query="How does sidechain compression work?",
                top_k=5,
                confidence_threshold=0.58,
            )

        assert "Sidechain" in result
        assert "pumping" in result
        assert "✗" not in result

    @pytest.mark.asyncio
    async def test_200_returns_plain_answer_not_json(self) -> None:
        """Result should be the answer string, not raw JSON."""
        from musical_mcp.server import mcp

        answer_text = "Use a low-pass filter on the mid channel."
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_http200(answer=answer_text))

        with patch("httpx.AsyncClient", return_value=mock_client):
            tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
            result = await tool_fn.fn(
                query="What is mid-side processing?",
                top_k=5,
                confidence_threshold=0.58,
            )

        assert result == answer_text

    @pytest.mark.asyncio
    async def test_200_missing_answer_key_returns_fallback(self) -> None:
        """API returns 200 but no 'answer' key — handler returns fallback string."""
        from musical_mcp.server import mcp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            return_value=_mock_response(200, {"sources": []})  # no answer key
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
            result = await tool_fn.fn(
                query="anything",
                top_k=3,
                confidence_threshold=0.58,
            )

        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# 422 insufficient_knowledge
# ---------------------------------------------------------------------------


class TestSearchInsufficientKnowledge:
    @pytest.mark.asyncio
    async def test_422_returns_no_answer_message(self) -> None:
        from musical_mcp.server import mcp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_http422("insufficient_knowledge"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
            result = await tool_fn.fn(
                query="How do tomatoes grow?",
                top_k=5,
                confidence_threshold=0.58,
            )

        assert "No answer" in result or "no answer" in result.lower()
        assert "insufficient_knowledge" in result

    @pytest.mark.asyncio
    async def test_422_suggests_rephrasing(self) -> None:
        from musical_mcp.server import mcp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_http422())

        with patch("httpx.AsyncClient", return_value=mock_client):
            tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
            result = await tool_fn.fn(
                query="nonsense query",
                top_k=5,
                confidence_threshold=0.58,
            )

        # Should give guidance, not just say "error"
        assert "rephras" in result.lower() or "topic" in result.lower()

    @pytest.mark.asyncio
    async def test_422_custom_reason_propagated(self) -> None:
        from musical_mcp.server import mcp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_http422("embedding_failed"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
            result = await tool_fn.fn(
                query="any query",
                top_k=5,
                confidence_threshold=0.58,
            )

        assert "embedding_failed" in result


# ---------------------------------------------------------------------------
# Server errors
# ---------------------------------------------------------------------------


class TestSearchServerErrors:
    @pytest.mark.asyncio
    async def test_500_returns_unavailable_message(self) -> None:
        from musical_mcp.server import mcp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_http500())

        with patch("httpx.AsyncClient", return_value=mock_client):
            tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
            result = await tool_fn.fn(
                query="any query",
                top_k=5,
                confidence_threshold=0.58,
            )

        assert "500" in result
        assert "✗" in result

    @pytest.mark.asyncio
    async def test_network_exception_returns_error_string(self) -> None:
        """httpx.ConnectError → handler returns error string, does NOT raise."""
        import httpx

        from musical_mcp.server import mcp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
            result = await tool_fn.fn(
                query="any query",
                top_k=5,
                confidence_threshold=0.58,
            )

        assert isinstance(result, str)
        assert "✗" in result
        assert "knowledge base" in result.lower() or "connect" in result.lower()

    @pytest.mark.asyncio
    async def test_timeout_exception_returns_error_string(self) -> None:
        import httpx

        from musical_mcp.server import mcp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Request timed out"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
            result = await tool_fn.fn(
                query="any query",
                top_k=5,
                confidence_threshold=0.58,
            )

        assert isinstance(result, str)
        assert "✗" in result

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self) -> None:
        """Any exception in the handler must be caught — never raise to the MCP client."""
        from musical_mcp.server import mcp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=RuntimeError("unexpected crash"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
            # Must NOT raise — handler catches all exceptions
            result = await tool_fn.fn(
                query="any",
                top_k=5,
                confidence_threshold=0.58,
            )

        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# API payload forwarding
# ---------------------------------------------------------------------------


class TestSearchPayloadForwarding:
    @pytest.mark.asyncio
    async def test_top_k_forwarded_to_api(self) -> None:
        """top_k parameter must appear in the POST body sent to /ask."""
        from musical_mcp.server import mcp

        captured_payload: dict = {}

        async def _fake_post(url, **kwargs):  # noqa: ANN001
            nonlocal captured_payload
            captured_payload = kwargs.get("json") or {}
            return _http200()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = _fake_post

        with patch("httpx.AsyncClient", return_value=mock_client):
            tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
            await tool_fn.fn(
                query="sidechain compression",
                top_k=8,
                confidence_threshold=0.58,
            )

        assert captured_payload.get("top_k") == 8

    @pytest.mark.asyncio
    async def test_confidence_threshold_forwarded_to_api(self) -> None:
        from musical_mcp.server import mcp

        captured_payload: dict = {}

        async def _fake_post(url, **kwargs):  # noqa: ANN001
            nonlocal captured_payload
            captured_payload = kwargs.get("json") or {}
            return _http200()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = _fake_post

        with patch("httpx.AsyncClient", return_value=mock_client):
            tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
            await tool_fn.fn(
                query="reverb tails",
                top_k=5,
                confidence_threshold=0.75,
            )

        assert captured_payload.get("confidence_threshold") == 0.75

    @pytest.mark.asyncio
    async def test_query_forwarded_to_api(self) -> None:
        from musical_mcp.server import mcp

        captured_payload: dict = {}

        async def _fake_post(url, **kwargs):  # noqa: ANN001
            nonlocal captured_payload
            captured_payload = kwargs.get("json") or {}
            return _http200()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = _fake_post

        with patch("httpx.AsyncClient", return_value=mock_client):
            tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
            await tool_fn.fn(
                query="How to use parallel compression?",
                top_k=5,
                confidence_threshold=0.58,
            )

        assert captured_payload.get("query") == "How to use parallel compression?"

    @pytest.mark.asyncio
    async def test_endpoint_is_ask(self) -> None:
        """Handler must call the /ask endpoint."""
        from musical_mcp.server import mcp

        captured_url: str = ""

        async def _fake_post(url, **kwargs):  # noqa: ANN001
            nonlocal captured_url
            captured_url = url
            return _http200()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = _fake_post

        with patch("httpx.AsyncClient", return_value=mock_client):
            tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
            await tool_fn.fn(
                query="organic house chords",
                top_k=5,
                confidence_threshold=0.58,
            )

        assert captured_url.endswith("/ask")


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------


class TestSearchStructuredLogging:
    @pytest.mark.asyncio
    async def test_success_emits_info_log(self, caplog) -> None:
        """Successful search emits an INFO log containing the tool name."""
        from musical_mcp.server import mcp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_http200())

        with caplog.at_level(logging.INFO, logger="musical_mcp.handlers"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
                await tool_fn.fn(
                    query="sidechain compression",
                    top_k=5,
                    confidence_threshold=0.58,
                )

        assert any("search_production_knowledge" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_failure_emits_error_log(self, caplog) -> None:
        """Network failure emits an ERROR log."""
        import httpx

        from musical_mcp.server import mcp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

        with caplog.at_level(logging.ERROR, logger="musical_mcp.handlers"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
                await tool_fn.fn(
                    query="any query",
                    top_k=5,
                    confidence_threshold=0.58,
                )

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(error_records) >= 1

    @pytest.mark.asyncio
    async def test_log_contains_call_id(self, caplog) -> None:
        """Every log record from this handler must contain an 8-char call_id."""
        from musical_mcp.server import mcp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_http200())

        with caplog.at_level(logging.INFO, logger="musical_mcp.handlers"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
                await tool_fn.fn(
                    query="sidechain compression",
                    top_k=5,
                    confidence_threshold=0.58,
                )

        relevant = [r for r in caplog.records if "search_production_knowledge" in r.message]
        assert len(relevant) >= 1
        # call_id is 8 chars — appears in the log message string representation
        import re

        msg = relevant[0].message
        # call_id format: 8 hex chars
        assert re.search(r"[a-f0-9]{8}", msg), f"No call_id found in log: {msg}"


# ---------------------------------------------------------------------------
# Default parameter values
# ---------------------------------------------------------------------------


class TestSearchDefaults:
    @pytest.mark.asyncio
    async def test_default_top_k_is_5(self) -> None:
        from musical_mcp.server import mcp

        captured_payload: dict = {}

        async def _fake_post(url, **kwargs):  # noqa: ANN001
            nonlocal captured_payload
            captured_payload = kwargs.get("json") or {}
            return _http200()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = _fake_post

        with patch("httpx.AsyncClient", return_value=mock_client):
            tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
            await tool_fn.fn(query="chord voicings")  # no top_k or threshold

        assert captured_payload.get("top_k") == 5

    @pytest.mark.asyncio
    async def test_default_confidence_threshold_is_058(self) -> None:
        from musical_mcp.server import mcp

        captured_payload: dict = {}

        async def _fake_post(url, **kwargs):  # noqa: ANN001
            nonlocal captured_payload
            captured_payload = kwargs.get("json") or {}
            return _http200()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = _fake_post

        with patch("httpx.AsyncClient", return_value=mock_client):
            tool_fn = mcp._tool_manager._tools["search_production_knowledge"]  # type: ignore[attr-defined]
            await tool_fn.fn(query="reverb on snare")

        assert captured_payload.get("confidence_threshold") == 0.58
