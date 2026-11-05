"""API entry point. Add each app's router here.

Endpoints need a login unless they set auth=None.
"""

from ninja import NinjaAPI

from core.api import router as health_router
from users.api import router as auth_router
from users.auth import JWTAuth

api = NinjaAPI(
    title="DocumentsAI API",
    version="0.1.0",
    description="Local MVP. Sign-in works; document ingestion, retrieval, and chat are not implemented yet.",
    auth=JWTAuth(),
)
api.add_router("/", health_router)
api.add_router("/auth", auth_router)
