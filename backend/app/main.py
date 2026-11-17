"""FastAPI application."""

from fastapi import FastAPI

app = FastAPI(title="Okane", version="0.1.0")


@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
