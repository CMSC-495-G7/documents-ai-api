"""The API entry point. Register each future app's router here."""

from ninja import NinjaAPI

from core.api import router as health_router

api = NinjaAPI(
    title="DocumentsAI API",
    version="0.1.0",
    description="Local MVP scaffold. Document ingestion, retrieval, and chat are not implemented yet.",
)
api.add_router("/", health_router)
