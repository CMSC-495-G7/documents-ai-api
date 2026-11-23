# Verifying the Alpha release

How to check the DocumentsAI Alpha from a clean machine: start it, run every test,
and walk through the main workflow. Each step lists what you should see.

## The release

| | API | UI |
| --- | --- | --- |
| Repository | [documents-ai-api](https://github.com/CMSC-495-G7/documents-ai-api) | [documents-ai-ui](https://github.com/CMSC-495-G7/documents-ai-ui) |
| Tag | `v0.1.0-alpha` | `v0.1.0-alpha` |
| CI on main | [Actions](https://github.com/CMSC-495-G7/documents-ai-api/actions?query=branch%3Amain) | [Actions](https://github.com/CMSC-495-G7/documents-ai-ui/actions?query=branch%3Amain) |

## What you need

- Docker Desktop (with Compose), started before running anything
- Node.js 22.22.2+ (22.x), 24.15.0+ (24.x) or 26+, for the UI
- Git

Python, PostgreSQL and Redis all run in Docker, nothing else to install.

## 1. Get the code

Put both repositories side by side and check out the release:

```sh
git clone https://github.com/CMSC-495-G7/documents-ai-api.git
git clone https://github.com/CMSC-495-G7/documents-ai-ui.git
git -C documents-ai-api checkout v0.1.0-alpha
git -C documents-ai-ui checkout v0.1.0-alpha
```

## 2. Settings

Everything has a working default in `compose.yaml`, so the API starts without a `.env`.
It then uses the **fake provider**: no key, no cost, real search and citations, but
the "answer" just repeats the question. For real answers, create `documents-ai-api/.env`:

| Variable | Needed? | What it does |
| --- | --- | --- |
| `LLM_PROVIDER` | For real answers | `openai` (default `fake`) |
| `OPENAI_API_KEY` | With `openai` | Embeddings and answers |
| `GEMINI_API_KEY` | Optional | Lets admins pick Gemini for answers in Settings |
| `DOCUMENTS_AI_API_PORT` | Optional | Host port for the API (default `8000`) |
| `ASK_SIMILARITY_CUTOFF` | Optional | Below this score the answer is "not found" (default `0.40`) |

`.env.example` lists every setting with its default.

## 3. Start the API

```sh
cd documents-ai-api
docker compose up --build --wait
docker compose ps
docker compose exec api python manage.py seed_identity
```

Expected:
- `docker compose ps`: `api`, `db` and `redis` are **healthy**, `worker` is **running**.
  Migrations run on start.
- `seed_identity` prints `Created admin: admin@acme.example`,
  `Created employee: employee@acme.example` and `Seed done.`
  (on a second run it says `Updated` instead of `Created`).
- <http://127.0.0.1:8000/api/ready> returns `{"status": "ok", "database": "ok", "pgvector": "ok"}`.

Test accounts (from `.env.example`): `admin@acme.example` / `admin-local-only` and
`employee@acme.example` / `employee-local-only`.

## 4. Run the API checks and tests

```sh
docker compose exec api python manage.py check
docker compose exec api python manage.py makemigrations --check --dry-run
docker compose exec api python manage.py test
```

Expected: `System check identified no issues`, `No changes detected`, then
`Ran 288 tests` and `OK`. These are the same steps CI runs on every pull request.

## 5. Start the UI and run its checks

```sh
cd ../documents-ai-ui
npm ci
npm run lint
npm run format:check
npm run build
npm test
npm run dev
```

Expected: lint and format report no problems, the build finishes, Vitest reports
`Tests 178 passed`, and Vite prints `Local: http://localhost:5173/`. If the API
isn't on port 8000, start Vite with `API_PROXY_TARGET=http://127.0.0.1:<port>`.

## 6. Walk through the workflow

Open <http://localhost:5173>.

1. **Sign in** as the admin. You land on **Chat**, with **Upload** in the side menu.
2. **Upload** `documents-ai-api/samples/Remote-Work-POLICY.pdf`. It appears as
   **Queued**, then **Processing**, then **Ready** on its own (about 10 seconds).
3. **Ask** on Chat: *How many days per week can employees work remotely?*
   With a real key you get an answer with a numbered citation like **[1]**. With the
   fake provider, ask with words from the PDF; the answer repeats the question, but the
   citation is real.
4. **Inspect the citation**: click **[1]**. The sources panel shows
   **Remote-Work-POLICY, Page 3** and the excerpt. Click **Original**: the PDF opens at
   page 3.
5. **Ask something the documents don't cover**: *What is the office Wi-Fi password?*
   The answer is *I couldn't find this in the documents*, with no citations.
6. **Reopen a saved answer**: the question is listed under **Recent questions** in the
   side panel. Reload the page, click it, and the same answer and citations come back.
   Sign out and in again: the history is still there.
7. **Settings** (admin, account menu): OpenAI and Gemini are listed. A provider without
   a key on the server shows as unavailable.

## 7. AI quality evaluation (Phase 4.6)

With `LLM_PROVIDER=openai` and a key in `.env`:

```sh
cd documents-ai-api
bash scripts/run-eval.sh
```

On Windows, run it from Git Bash, or from PowerShell with
`& "C:\Program Files\Git\bin\bash.exe" scripts/run-eval.sh`. A plain `bash` in
PowerShell starts WSL, which can't see Docker unless WSL integration is on.

It uploads the five sample PDFs (once), waits until they're ready, then asks the 20
questions in `evals/questions.json`: 15 with a known document and page, and 5 the
documents can't answer. Expected: one line per question, then

```
Retrieval hits: N/15 (target 12/15)
Not found:      N/5 (target 4/5)
Under 30 s:     N/20 (target 9 of 10)
```

Each run saves a full report in `evals/results/` and adds one line to
`evals/results/runs.csv` with the date, commit, models and cutoff, so runs before and
after a change can be compared. See `evals/README.md`.

## 8. Clean up

```sh
cd documents-ai-api
docker compose down --volumes
```

`--volumes` also deletes the database and uploaded files.

## Setup problems we hit, and the fixes

| Problem | Cause | Fix |
| --- | --- | --- |
| UI shows a 502 and Postman says "socket hang up" | API started from PyCharm bound to `127.0.0.1` inside the container | Start with `docker compose up`, or set the run host to `0.0.0.0` |
| Django rejects requests to `http://0.0.0.0:8000` | `0.0.0.0` isn't an allowed host | Call `http://127.0.0.1:8000` |
| Uploads stay **Queued** | The worker isn't running, or still has old job code | `docker compose up` starts it; run `docker compose restart worker` after editing job code |
| Old database errors after the custom user model arrived | Existing tables from before the model change | `docker compose down --volumes` once, then start again |
| `scripts/test-ask.sh` failed in Git Bash on Windows | It called `python3`, which Git Bash often doesn't have | Scripts now use `python3` or `python`, whichever exists |
| `bash scripts/run-eval.sh` in PowerShell said "docker could not be found in this WSL 2 distro" | Plain `bash` on Windows is WSL's, and WSL can't see Docker Desktop by default | Run it from Git Bash, or `& "C:\Program Files\Git\bin\bash.exe" scripts/run-eval.sh` |
| `scripts/test-ask.sh` interrupted other work | It restarted the shared Compose stack | It now only checks the stack is up |
| PDF preview blank under `npm run dev` | The PDF library couldn't find its worker in Vite's dev server | The UI sets the worker itself (`common/lib/pdf-worker.ts`) |
| First PDF opened made the page reload | Vite found a new dependency mid-session and re-bundled | `optimizeDeps.include: ['react-pdf']` in `vite.config.ts` |
| A UI test passed locally but failed in CI | CI runs Node 22, locally Node 24; a test helper used `instanceof Blob` | The helper checks the file's `type` field instead |
| CI failed on API `main` after PR #9 merged | New tests arrived without the change they test | Fixed in PR #13; CI runs on `main` as well as on pull requests |
| Chat shows "Could not reach the server" | The API is stopped and Vite's proxy answers with a bare 502 | Start the API (`docker compose up -d`), then Retry |
