"""
Ask route for grounded RAG question-answering.

``POST /ask`` — retrieve relevant chunks, build context, generate answer with citations.

Pipeline:
    1. Expand query (intent detection + query expansion)
    2. Embed query
    3. Search vector store
    4. Confidence check (reject if max_score < threshold)
    5. Format context block
    6. Build system + user prompts
    7. Generate response via LLM
    8. Parse and validate citations
"""

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db, get_embedding_provider, get_generation_provider
from api.schemas.ask import AskRequest, AskResponse, SourceReference, UsageMetadata
from core.generation.base import GenerationProvider, GenerationRequest, Message
from core.query_expansion import detect_mastering_intent, expand_query
from core.rag.citations import extract_citations, validate_citations
from core.rag.context import RetrievedChunk, format_context_block, format_source_list
from core.rag.prompts import build_system_prompt, build_user_prompt
from db.rerank import rerank_results
from db.search import search_chunks
from ingestion.embeddings import OpenAIEmbeddingProvider

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ask"])

DbSession = Annotated[Session, Depends(get_db)]
Embedder = Annotated[OpenAIEmbeddingProvider, Depends(get_embedding_provider)]
Generator = Annotated[GenerationProvider, Depends(get_generation_provider)]


@router.post("/ask", response_model=AskResponse)
def ask(
    body: AskRequest,
    db: DbSession,
    embedder: Embedder,
    generator: Generator,
) -> AskResponse:
    """
    Answer a question using grounded retrieval-augmented generation.

    Retrieves relevant chunks from the knowledge base, builds a context block,
    and generates a cited answer. Rejects queries when confidence is too low.

    Returns:
        AskResponse with answer, sources, citations, and usage metadata.

    Raises:
        HTTPException 422: If max_score < confidence_threshold (insufficient knowledge).
        HTTPException 500: If embedding, search, or generation fails.
    """
    t_start = time.perf_counter()
    warnings: list[str] = []

    # 1. Query expansion
    intent = detect_mastering_intent(body.query)
    expanded_query = expand_query(body.query, intent)

    # 2. Embed query
    t_embed = time.perf_counter()
    try:
        embeddings = embedder.embed_texts([expanded_query])
        query_embedding = embeddings[0]
    except Exception as exc:
        logger.error("Embedding failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to embed query") from exc
    embedding_ms = (time.perf_counter() - t_embed) * 1000

    # 3. Search chunks (fetch 3x for reranking diversity)
    t_search = time.perf_counter()
    try:
        raw_results = search_chunks(db, query_embedding, top_k=body.top_k * 3)
    except Exception as exc:
        logger.error("Search failed: %s", exc)
        raise HTTPException(status_code=500, detail="Search failed") from exc

    # 4. Rerank (resilient — degrade to raw results on failure)
    filename_keywords = None
    if intent.category in ("mastering", "mixing"):
        filename_keywords = ["mastering", "mixing", "masterclass", "mix-mastering"]

    try:
        reranked = rerank_results(
            raw_results,
            top_k=body.top_k,
            max_per_document=1,
            course_boost=1.15,
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

    # 7. Build prompts
    system_prompt = build_system_prompt()
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

    # 10. Build response
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
    )
