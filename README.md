# DocumentsAI API

Local Django Ninja API with PostgreSQL 17 and pgvector. This is a development
scaffold: health checks, interactive API documentation, sign-in, document upload,
and question answering work; background document ingestion is not implemented yet.

## Django apps

- `core`: API health checks and the migration that enables pgvector.
- `users`: workspaces, the custom `User` model (email login, `admin`/`employee`
  role), JWT sign-in (`/api/auth/*`), role checks, and the `seed_identity` command.
- `documents`: the `Document` model, `storage.py` (handles
  uploaded files), and `/api/documents` (admins upload
  PDF/DOCX up to 16 MB, lists their workspace's documents).
- `ask`: document chunks with embeddings, saved answers and citations, and
  `POST /api/ask` (searches ready documents in the user's workspace, cites the
  chunks it used, and skips the LLM below the similarity cutoff).

## Requirements

- Docker Desktop with Docker Compose. Start Docker Desktop before running commands.
- macOS: install the [Apple Silicon or Intel edition](https://docs.docker.com/desktop/setup/install/mac-install/)
  matching your computer.
- Windows x64 (Intel or AMD): follow the [Windows installation instructions](https://docs.docker.com/desktop/setup/install/windows-install/),
  enable the WSL 2 backend, and use Linux containers. Run the commands below in PowerShell.

You do not need Python, PostgreSQL, Node.js, or a virtual environment installed
on your computer for this Docker setup. Docker chooses the Linux image for your
computer's architecture. Native Windows ARM64 has not been verified.

## Download and start

Clone this repository or download its ZIP and extract it. Open a terminal in the
API folder containing `compose.yaml`, `Dockerfile`, and `manage.py`. When using
the parent workspace, this is `documents-ai-app/documents-ai-api`.

The same command works on macOS and Windows PowerShell:

```sh
docker compose up --build
```

The first run downloads images and installs the pinned Python dependencies.
Compose waits for PostgreSQL to be healthy, then the API automatically runs all
migrations (including enabling pgvector) and starts on port 8000. Leave this
terminal open. Wait for Django's `Starting development server` message.

Open:

- [Interactive API documentation](http://127.0.0.1:8000/api/docs)
- [Health check](http://127.0.0.1:8000/api/health)
- [Database and pgvector check](http://127.0.0.1:8000/api/ready)
- [OpenAPI schema](http://127.0.0.1:8000/api/openapi.json)

The health check returns:

```json
{"status": "ok", "service": "documents-ai-api"}
```

The readiness check returns HTTP 200 with:

```json
{"status": "ok", "database": "ok", "pgvector": "ok"}
```

It returns HTTP 503 when PostgreSQL is unavailable or pgvector is missing.
The database is accessible only inside the Compose network; no host database
port is needed. Database data is stored in this stack's named PostgreSQL volume
and persists when containers are recreated.

To start in the background and wait for both services to be healthy, use:

```sh
docker compose up --build --wait
docker compose ps
```

Both `api` and `db` should show as healthy. A failed migration prevents the API
from starting; check `docker compose logs api` for the error.

## Test accounts and sign-in

Create the Engineering workspace with one admin and one employee (safe to run again):

```sh
docker compose exec api python manage.py seed_identity
```

Emails and passwords come from `SEED_*` in `.env` (defaults are in `.env.example`).
Sign in with `POST /api/auth/login`, then send `Authorization: Bearer <access>` on
other requests. Every endpoint needs a token unless it sets `auth=None`.

## Ask a question

`POST /api/ask` takes `{"question": "How many vacation days do I get?"}` and
returns the answer, the model name, and the cited chunks (document title, page /
slide / row range, and chunk ID). It only searches `ready` documents in the user's
workspace and saves every question, answer, and citation.

The defaults use Google Gemini's free tier. Get a key at
[aistudio.google.com/apikey](https://aistudio.google.com/apikey) and add it to
`.env`:

```sh
GEMINI_API_KEY=your-key
```

You can also point the `ASK_*_BASE_URL` / `ASK_*_MODEL` values at any other
OpenAI-compatible provider (see `.env.example`). Without an API key, the endpoint
returns a clear 502 instead of calling out. If the best chunk scores below
`ASK_SIMILARITY_CUTOFF`, the LLM is skipped and the answer is
`"I couldn't find this in the documents"` with no citations.

## Check and test

With the services running, use another terminal in this same API folder:

```sh
docker compose exec api python manage.py check
docker compose exec api python manage.py makemigrations --check --dry-run
docker compose exec api python manage.py test
```

Tests create and remove a separate test database. They check the health and
readiness endpoints, API docs, database failures, and a real pgvector operation.

## Settings and troubleshooting

No `.env` file is required. To customize the defaults, copy `.env.example` once.
Keep any existing `.env` file instead of overwriting it.

macOS:

```sh
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

- **Port 8000 is occupied:** set `DOCUMENTS_AI_API_PORT=8001` in `.env`, run
  `docker compose up --build` again, and use port 8001 in the browser links.
  The API's internal port remains 8000.
- **Docker connection error:** start Docker Desktop and wait until its engine is
  running. `docker info` and `docker compose version` should both succeed.
- **Windows image/platform error:** ensure Docker Desktop is using Linux containers
  with WSL 2, rather than Windows containers.
- **API or database unhealthy:** run `docker compose logs api db`. The first build
  needs internet access to download the images and Python packages.
- **Database authentication fails after changing credentials:** the PostgreSQL
  image applies its credentials when the volume is first initialized. Restore
  the original values, or use the reset command below if you can discard the data.
- **Source or dependency changes:** rerun `docker compose up --build`. Source is
  copied into the image; local edits are not mounted into the running container.

Compose connects the API to `db:5432` inside its network. `DJANGO_DEBUG` is enabled for local
development and API docs assets. This setup uses Django's development server and
local credentials; it is intended for development on your own computer.

## Stop, restart, and reset

Stop a foreground run with `Ctrl+C`, then remove its containers with:

```sh
docker compose down
```

This keeps the PostgreSQL volume. Restart with `docker compose up --build`;
migrations safely run again and existing data remains.

To **permanently delete this stack's database data**, stop it and remove its volume:

```sh
docker compose down --volumes
```

Quit Docker Desktop separately from its menu bar icon on macOS or system tray
icon on Windows. The React UI is a separate project and is not started by this
Compose file.
