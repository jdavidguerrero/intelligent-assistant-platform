"""
Ask route — hybrid tool-first + RAG question-answering.

``POST /ask`` — routes to tools when intent is detected, falls back to RAG.

Pipeline (hybrid mode, use_tools=True):
    0. Tool routing — detect intent, execute tool if matched
       0a. If tool succeeds → synthesize natural language response via LLM → return (mode="tool")
       0b. If no tool matches → continue to RAG pipeline (mode="rag")
    1. Expand query (intent detection + query expansion + sub-domain detection)
    2. Embed query
    3. Search vector store — namespaced by sub-domain if detected, global fallback
    4. Confidence check (reject if max_score < threshold)
    5. Rerank results
    6. Format context block
    7. Build system + user prompts (inject active_sub_domains)
    8. Generate response via LLM
    9. Parse and validate citations

Response modes:
    "tool" — Tool executed and summarized. No RAG, no citations.
    "rag"  — Pure RAG. No tool matched or use_tools=False.
"""

import logging
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db, get_embedding_provider, get_generation_provider
from api.schemas.ask import (
    AskRequest,
    AskResponse,
    SourceReference,
    ToolCallRecord,
    UsageMetadata,
)
from core.generation.base import GenerationProvider, GenerationRequest, Message
from core.query_expansion import detect_mastering_intent, expand_query
from core.rag.citations import extract_citations, validate_citations
from core.rag.context import RetrievedChunk, format_context_block, format_source_list
from core.rag.prompts import build_system_prompt, build_user_prompt
from core.sub_domain_detector import detect_sub_domains
from db.rerank import rerank_results
from db.search import search_chunks
from ingestion.embeddings import OpenAIEmbeddingProvider
from tools.router import ToolRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ask"])

DbSession = Annotated[Session, Depends(get_db)]
Embedder = Annotated[OpenAIEmbeddingProvider, Depends(get_embedding_provider)]
Generator = Annotated[GenerationProvider, Depends(get_generation_provider)]

# ---------------------------------------------------------------------------
# Tool synthesis prompts
# ---------------------------------------------------------------------------

_TOOL_SYSTEM_PROMPT = (
    "You are a music production assistant. "
    "A tool was just executed on behalf of the user. "
    "Summarize what happened in a friendly, concise way (2-4 sentences). "
    "If the tool succeeded, confirm what was done and highlight key results. "
    "If it failed, explain clearly what went wrong and what the user can do. "
    "Do NOT add information that wasn't in the tool result. "
    "Do NOT use citations — this is not a RAG response."
)


def _build_tool_synthesis_prompt(query: str, tool_name: str, tool_data: dict) -> str:
    """
    Build the user prompt for LLM synthesis of a tool result.

    Pure function — no I/O.

    Args:
        query:     Original user query
        tool_name: Name of the tool that was executed
        tool_data: Tool result data dict

    Returns:
        Formatted user prompt string
    """
    import json

    data_str = json.dumps(tool_data, indent=2, ensure_ascii=False, default=str)
    return (
        f"User query: {query}\n\n"
        f"Tool executed: {tool_name}\n\n"
        f"Tool result:\n{data_str}\n\n"
        "Please summarize the result in a friendly, conversational way."
    )


def _summarize_tool_data(tool_name: str, data: dict | None) -> dict[str, Any]:
    """
    Trim tool result data to the most important fields for the ToolCallRecord.

    Avoids bloating the API response with full tool output.

    Pure function — no I/O.

    Args:
        tool_name: Tool name for context-specific trimming
        data:      Full tool result data

    Returns:
        Dict with key summary fields only
    """
    if not data:
        return {}

    # Tool-specific key fields to surface in the record
    key_fields: dict[str, list[str]] = {
        "log_practice_session": ["session_id", "topic", "duration_minutes", "logged_at"],
        "create_session_note": ["note_id", "category", "title", "tags", "total_notes"],
        "analyze_track": ["bpm", "key", "energy", "analysis_method"],
        "suggest_chord_progression": ["key", "mood", "genre", "bars", "roman_analysis"],
        "generate_midi_pattern": ["total_events", "bpm", "style", "midi_file"],
        "search_by_genre": ["genre", "total_found", "query"],
        "suggest_compatible_tracks": ["reference", "total_found", "compatible_keys"],
        "extract_style_from_context": ["confidence_label", "suggestion_params", "midi_params"],
    }

    fields = key_fields.get(tool_name, list(data.keys())[:5])
    return {k: data[k] for k in fields if k in data}


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------


@router.post("/ask", response_model=AskResponse)
def ask(
    body: AskRequest,
    db: DbSession,
    embedder: Embedder,
    generator: Generator,
) -> AskResponse:
    """
    Answer a question using hybrid tool routing + grounded RAG.

    When use_tools=True (default), attempts tool routing first:
      - If a tool intent is detected, executes the tool and returns
        a natural language summary (mode="tool").
      - If no tool matches, falls back to pure RAG (mode="rag").

    When use_tools=False, always uses pure RAG.

    Returns:
        AskResponse with answer, mode, tool_calls, sources, and usage metadata.

    Raises:
        HTTPException 422: Insufficient knowledge (RAG mode only).
        HTTPException 500: Embedding, search, or generation failure.
    """
    t_start = time.perf_counter()
    warnings: list[str] = []

    # ------------------------------------------------------------------
    # Step 0: Tool routing (hybrid mode only)
    # ------------------------------------------------------------------
    if body.use_tools:
        tool_response = _try_tool_route(
            query=body.query,
            generator=generator,
            t_start=t_start,
            body=body,
        )
        if tool_response is not None:
            return tool_response

    # ------------------------------------------------------------------
    # Steps 1–9: Pure RAG pipeline
    # ------------------------------------------------------------------

    # 1. Query expansion + sub-domain detection
    intent = detect_mastering_intent(body.query)
    expanded_query = expand_query(body.query, intent)
    sub_domain_result = detect_sub_domains(body.query)
    active_sub_domains = list(sub_domain_result.active)

    # 2. Embed query
    t_embed = time.perf_counter()
    try:
        embeddings = embedder.embed_texts([expanded_query])
        query_embedding = embeddings[0]
    except Exception as exc:
        logger.error("Embedding failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to embed query") from exc
    embedding_ms = (time.perf_counter() - t_embed) * 1000

    # 3. Search chunks — namespaced by sub-domain when detected, with global fallback
    #
    # Strategy:
    #   a) If sub-domains detected: search each active sub-domain, merge, deduplicate.
    #   b) If the filtered search returns fewer than MIN_FILTERED_RESULTS chunks,
    #      fall back to global search (avoids empty responses for niche queries).
    #   c) If no sub-domains detected: global search directly.
    _MIN_FILTERED_RESULTS = 3
    t_search = time.perf_counter()
    try:
        if active_sub_domains:
            # Per-sub-domain search: allocate top_k * 3 slots, split across domains
            per_domain_k = max(body.top_k * 2, 6)
            seen_ids: set[int] = set()
            merged: list = []
            for sd in active_sub_domains:
                for record, score in search_chunks(
                    db, query_embedding, top_k=per_domain_k, sub_domain=sd
                ):
                    rid = id(record)
                    if rid not in seen_ids:
                        seen_ids.add(rid)
                        merged.append((record, score))

            if len(merged) >= _MIN_FILTERED_RESULTS:
                raw_results = merged
                logger.info(
                    "Sub-domain search: domains=%s, results=%d",
                    active_sub_domains,
                    len(raw_results),
                )
            else:
                # Not enough filtered results — fall back to global search
                logger.info(
                    "Sub-domain search returned %d results (< %d) — falling back to global",
                    len(merged),
                    _MIN_FILTERED_RESULTS,
                )
                raw_results = search_chunks(db, query_embedding, top_k=body.top_k * 3)
                active_sub_domains = []  # clear so prompt stays generic
        else:
            raw_results = search_chunks(db, query_embedding, top_k=body.top_k * 3)
    except Exception as exc:
        logger.error("Search failed: %s", exc)
        raise HTTPException(status_code=500, detail="Search failed") from exc

    # 4. Rerank
    filename_keywords = None
    if intent.category in ("mastering", "mixing"):
        filename_keywords = ["mastering", "mixing", "masterclass", "mix-mastering"]

    try:
        reranked = rerank_results(
            raw_results,
            top_k=body.top_k,
            max_per_document=1,
            course_boost=1.25,
            youtube_boost=1.0,
            filename_keywords=filename_keywords,
            filename_boost=1.20,
            query_embedding=query_embedding,
            mmr_lambda=0.7,
            use_mmr=True,
        )
    except Exception as exc:
        logger.warning("Reranking failed, using raw results: %s", exc)
        warnings.append("reranking_failed")
        reranked = raw_results[: body.top_k]

    search_ms = (time.perf_counter() - t_search) * 1000

    # 5. Confidence check
    if not reranked:
        raise HTTPException(
            status_code=422,
            detail={
                "reason": "insufficient_knowledge",
                "message": "No relevant chunks found for this query.",
            },
        )

    max_score = max(score for _, score in reranked)
    if max_score < body.confidence_threshold:
        raise HTTPException(
            status_code=422,
            detail={
                "reason": "insufficient_knowledge",
                "message": (
                    f"Top similarity score ({max_score:.2f}) is below "
                    f"confidence threshold ({body.confidence_threshold})."
                ),
            },
        )

    # 6. Build context
    retrieved_chunks = [
        RetrievedChunk(
            text=record.text,
            source_name=record.source_name,
            source_path=record.source_path,
            chunk_index=record.chunk_index,
            score=score,
            page_number=record.page_number,
        )
        for record, score in reranked
    ]

    context_block = format_context_block(retrieved_chunks)
    sources_list = format_source_list(retrieved_chunks)

    # 7. Build prompts — inject sub-domain context when available
    system_prompt = build_system_prompt(
        active_sub_domains=active_sub_domains if active_sub_domains else None,
    )
    user_prompt = build_user_prompt(body.query, context_block)

    # 8. Generate response
    t_gen = time.perf_counter()
    try:
        gen_response = generator.generate(
            GenerationRequest(
                messages=(
                    Message(role="system", content=system_prompt),
                    Message(role="user", content=user_prompt),
                ),
                temperature=body.temperature,
                max_tokens=body.max_tokens,
            )
        )
    except Exception as exc:
        logger.error("Generation failed: %s", exc)
        raise HTTPException(status_code=500, detail="LLM generation failed") from exc
    generation_ms = (time.perf_counter() - t_gen) * 1000

    # 9. Parse and validate citations
    extracted_citations = extract_citations(gen_response.content)
    citation_result = validate_citations(extracted_citations, num_sources=len(retrieved_chunks))

    if citation_result.invalid_citations:
        warnings.append("invalid_citations")

    total_ms = (time.perf_counter() - t_start) * 1000

    return AskResponse(
        query=body.query,
        answer=gen_response.content,
        sources=[
            SourceReference(
                index=src["index"],  # type: ignore[arg-type]
                source_name=src["source_name"],  # type: ignore[arg-type]
                source_path=src["source_path"],  # type: ignore[arg-type]
                page_number=src["page_number"],  # type: ignore[arg-type]
                score=src["score"],  # type: ignore[arg-type]
            )
            for src in sources_list
        ],
        citations=list(citation_result.citations),
        reason="invalid_citations" if citation_result.invalid_citations else None,
        warnings=warnings,
        usage=UsageMetadata(
            input_tokens=gen_response.usage_input_tokens,
            output_tokens=gen_response.usage_output_tokens,
            total_tokens=gen_response.usage_input_tokens + gen_response.usage_output_tokens,
            embedding_ms=round(embedding_ms, 2),
            search_ms=round(search_ms, 2),
            generation_ms=round(generation_ms, 2),
            total_ms=round(total_ms, 2),
            model=gen_response.model,
        ),
        mode="rag",
        tool_calls=[],
    )


# ---------------------------------------------------------------------------
# Tool routing helper
# ---------------------------------------------------------------------------


def _try_tool_route(
    query: str,
    generator: GenerationProvider,
    t_start: float,
    body: AskRequest,
) -> AskResponse | None:
    """
    Attempt to route query to a tool. Returns AskResponse if tool handled it,
    None if no tool matched (caller should fall back to RAG).

    Args:
        query:     User query string
        generator: LLM provider for synthesis
        t_start:   Request start time (perf_counter)
        body:      Full request for token/temp settings

    Returns:
        AskResponse (mode="tool") if handled, else None
    """
    tool_router = ToolRouter()

    try:
        route_result = tool_router.route(query)
    except Exception as exc:
        logger.warning("Tool routing failed, falling back to RAG: %s", exc)
        return None

    # No tool matched → caller uses RAG
    if route_result.fallback_to_rag:
        return None

    # Build ToolCallRecord list
    tool_call_records: list[ToolCallRecord] = []
    successful_results = []

    for tool_name, tool_result, params in zip(
        route_result.matched_tools,
        route_result.tool_results,
        route_result.params_used,
        strict=False,
    ):
        record = ToolCallRecord(
            tool_name=tool_name,
            params=params,
            success=tool_result.success,
            error=tool_result.error,
            data_summary=_summarize_tool_data(tool_name, tool_result.data),
        )
        tool_call_records.append(record)
        if tool_result.success:
            successful_results.append((tool_name, tool_result))

    # If all tools failed → fall back to RAG
    if not successful_results:
        logger.warning("All tools failed for query %r — falling back to RAG", query[:80])
        return None

    # Synthesize natural language response from tool results
    # Use the first successful tool result for synthesis
    primary_tool_name, primary_result = successful_results[0]
    synthesis_prompt = _build_tool_synthesis_prompt(
        query=query,
        tool_name=primary_tool_name,
        tool_data=primary_result.data or {},
    )

    t_gen = time.perf_counter()
    try:
        gen_response = generator.generate(
            GenerationRequest(
                messages=(
                    Message(role="system", content=_TOOL_SYSTEM_PROMPT),
                    Message(role="user", content=synthesis_prompt),
                ),
                temperature=0.3,  # lower temp for factual confirmation
                max_tokens=512,
            )
        )
    except Exception as exc:
        logger.error("Tool synthesis generation failed: %s", exc)
        # Return minimal response without synthesis
        gen_response = None

    generation_ms = (time.perf_counter() - t_gen) * 1000
    total_ms = (time.perf_counter() - t_start) * 1000

    # Build answer: LLM synthesis or fallback to structured summary
    if gen_response:
        answer = gen_response.content
        input_tokens = gen_response.usage_input_tokens
        output_tokens = gen_response.usage_output_tokens
        model = gen_response.model
    else:
        answer = _fallback_tool_answer(route_result.matched_tools, tool_call_records)
        input_tokens = 0
        output_tokens = 0
        model = "none"

    return AskResponse(
        query=query,
        answer=answer,
        sources=[],
        citations=[],
        reason=None,
        warnings=[],
        usage=UsageMetadata(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            embedding_ms=0.0,
            search_ms=0.0,
            generation_ms=round(generation_ms, 2),
            total_ms=round(total_ms, 2),
            model=model,
        ),
        mode="tool",
        tool_calls=tool_call_records,
    )


def _fallback_tool_answer(
    tool_names: tuple[str, ...],
    records: list[ToolCallRecord],
) -> str:
    """
    Build a plain-text fallback answer when LLM synthesis fails.

    Pure function — no I/O.

    Args:
        tool_names: Names of tools that were called
        records:    ToolCallRecord list with success/error status

    Returns:
        Human-readable status string
    """
    lines = []
    for record in records:
        if record.success:
            lines.append(f"✓ {record.tool_name}: executed successfully.")
            if record.data_summary:
                for k, v in record.data_summary.items():
                    lines.append(f"  {k}: {v}")
        else:
            lines.append(f"✗ {record.tool_name}: failed — {record.error}")
    return "\n".join(lines) if lines else "Tools executed with no output."
