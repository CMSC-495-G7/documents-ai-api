"""Shared local settings for macOS and Windows, configured through .env."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DJANGO_DEBUG=(bool, False))
# Use an absolute path so .env loads regardless of the terminal's working folder.
# Existing environment variables take precedence over the file.
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "[::1]"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "ninja",  # Serves the interactive API documentation assets (local)
    "core.apps.CoreConfig",
    "users.apps.UsersConfig",
    "documents.apps.DocumentsConfig",
    "ask.apps.AskConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Match the existing Compose service; there is no SQLite fallback.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", default="documents_ai"),
        "USER": env("POSTGRES_USER", default="documents_ai"),
        "PASSWORD": env("POSTGRES_PASSWORD", default="documents_ai"),
        "HOST": env("POSTGRES_HOST", default="127.0.0.1"),
        "PORT": env.int("POSTGRES_PORT", default=5432),
        "OPTIONS": {"connect_timeout": 5},
    },
}

# Has to be set before the first migrate, changing it later means wiping the db.
AUTH_USER_MODEL = "users.User"

JWT_ACCESS_TOKEN_MINUTES = env.int("JWT_ACCESS_TOKEN_MINUTES", default=15)
JWT_REFRESH_TOKEN_DAYS = env.int("JWT_REFRESH_TOKEN_DAYS", default=7)

# Used by seed_identity.
SEED_ADMIN_EMAIL = env("SEED_ADMIN_EMAIL", default="admin@acme.example")
SEED_ADMIN_PASSWORD = env("SEED_ADMIN_PASSWORD", default="")
SEED_EMPLOYEE_EMAIL = env("SEED_EMPLOYEE_EMAIL", default="employee@acme.example")
SEED_EMPLOYEE_PASSWORD = env("SEED_EMPLOYEE_PASSWORD", default="")

# Biggest upload POST /api/documents accepts.
DOCUMENT_MAX_UPLOAD_MB = env.int("DOCUMENT_MAX_UPLOAD_MB", default=16)

# POST /api/ask: retrieval and an OpenAI-compatible embedding/chat provider.
# Defaults use the Google Gemini free tier. Set GEMINI_API_KEY once, or use the
# ASK_* keys/URLs to point at any other OpenAI-compatible provider.
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
GEMINI_BASE_URL = env(
    "GEMINI_BASE_URL", default="https://generativelanguage.googleapis.com/v1beta/openai"
)
ASK_EMBEDDING_MODEL = env("ASK_EMBEDDING_MODEL", default="gemini-embedding-2")
ASK_EMBEDDING_DIMENSIONS = env.int("ASK_EMBEDDING_DIMENSIONS", default=3072)
ASK_EMBEDDING_API_KEY = env("ASK_EMBEDDING_API_KEY", default="") or GEMINI_API_KEY
ASK_EMBEDDING_BASE_URL = env("ASK_EMBEDDING_BASE_URL", default=GEMINI_BASE_URL)
ASK_EMBEDDING_TIMEOUT_SECONDS = env.int("ASK_EMBEDDING_TIMEOUT_SECONDS", default=10)
ASK_LLM_MODEL = env("ASK_LLM_MODEL", default="gemini-3.1-flash-lite")
ASK_LLM_API_KEY = env("ASK_LLM_API_KEY", default="") or GEMINI_API_KEY
ASK_LLM_BASE_URL = env("ASK_LLM_BASE_URL", default=GEMINI_BASE_URL)
ASK_LLM_TIMEOUT_SECONDS = env.int("ASK_LLM_TIMEOUT_SECONDS", default=30)
ASK_MAX_ANSWER_TOKENS = env.int("ASK_MAX_ANSWER_TOKENS", default=1024)
ASK_MAX_CONTEXT_CHUNKS = env.int("ASK_MAX_CONTEXT_CHUNKS", default=6)
ASK_SIMILARITY_CUTOFF = env.float("ASK_SIMILARITY_CUTOFF", default=0.35)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
# Uploaded files, the "uploads" volume in Docker.
MEDIA_ROOT = BASE_DIR / "uploads"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
