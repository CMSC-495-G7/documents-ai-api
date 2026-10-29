"""Small diagnostic endpoints to validate the API and its database connection."""

from typing import Literal

from django.db import DatabaseError, connection
from ninja import Router, Schema

router = Router(tags=["Health"])


class HealthResponse(Schema):
    status: Literal["ok"]
    service: str


class ReadinessResponse(Schema):
    status: Literal["ok", "error"]
    database: Literal["ok", "unavailable"]
    pgvector: Literal["ok", "missing", "unknown"]


@router.get("/health", response=HealthResponse)
def health(request):
    """Liveness: the API can answer HTTP requests; no database access required."""
    return {"status": "ok", "service": "documents-ai-api"}


@router.get("/ready", response={200: ReadinessResponse, 503: ReadinessResponse})
def ready(request):
    """Readiness: PostgreSQL responds and the vector extension is enabled."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            vector_enabled = cursor.fetchone() is not None
    except DatabaseError:
        # Keep connection details and credentials out of API responses.
        return 503, {"status": "error", "database": "unavailable", "pgvector": "unknown"}

    if not vector_enabled:
        return 503, {"status": "error", "database": "ok", "pgvector": "missing"}
    return 200, {"status": "ok", "database": "ok", "pgvector": "ok"}
