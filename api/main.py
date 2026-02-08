from fastapi import FastAPI

from api.routes.search import router as search_router

app = FastAPI(title="Intelligent Assistant")

app.include_router(search_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Return a simple liveness check."""
    return {"status": "ok"}
