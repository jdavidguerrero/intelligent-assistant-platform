from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from api.deps import get_response_cache
from api.routes.analyze import router as analyze_router
from api.routes.ask import router as ask_router
from api.routes.generate import router as generate_router
from api.routes.memory import router as memory_router
from api.routes.mix import router as mix_router
from api.routes.search import router as search_router
from api.routes.session_intelligence import router as session_intelligence_router
from api.routes.tools import router as tools_router
from infrastructure.metrics import get_metrics_response

app = FastAPI(title="Intelligent Assistant")

# CORS — allow the Copilot UI (React dev server) to call the API
# Include both localhost and 127.0.0.1 variants — browsers treat them as different origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_router)
app.include_router(ask_router)
app.include_router(memory_router)
app.include_router(analyze_router)
app.include_router(generate_router)
app.include_router(mix_router)
app.include_router(session_intelligence_router)
app.include_router(tools_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Return a simple liveness check."""
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    """Prometheus metrics endpoint.

    Returns metrics in Prometheus text exposition format.
    Returns empty response if prometheus_client is not installed.
    """
    body, content_type = get_metrics_response()
    return Response(content=body, media_type=content_type)


@app.post("/cache/invalidate")
def cache_invalidate(source_name: str) -> dict[str, int]:
    """Invalidate all cached responses that cited a given source.

    Call this after re-ingesting a document to ensure stale answers
    are not served from the response cache.

    Args:
        source_name: Filename or source identifier to invalidate
            (e.g. ``Bob_Katz.pdf``).

    Returns:
        Dict with ``deleted`` count.
    """
    cache = get_response_cache()
    deleted = cache.invalidate_source(source_name)
    return {"deleted": deleted}


@app.get("/cache/stats")
def cache_stats() -> dict:
    """Return basic response cache statistics."""
    cache = get_response_cache()
    return cache.stats()
