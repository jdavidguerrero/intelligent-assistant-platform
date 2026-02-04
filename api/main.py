from fastapi import FastAPI

app = FastAPI(title="Intelligent Assistant")

@app.get("/health")
def health():
    return {"status": "ok"}