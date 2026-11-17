#!/usr/bin/env bash
# Quick end-to-end check of POST /api/ask on your running stack.
# Run from the API folder: bash scripts/test-ask.sh
set -euo pipefail

API=${API:-http://127.0.0.1:8000}
# Git Bash on Windows often has python but not python3
PY=$(command -v python3 || command -v python)

# Starts the stack if it isn't up, leaves it alone if it is
docker compose up -d --wait
docker compose ps
docker compose exec api python -c "import documents, ask; print('imports ok')"
docker compose exec api python manage.py showmigrations ask documents users
docker compose exec api python manage.py shell -c "from django.conf import settings as s; from core.llm import EMBEDDING_DIMENSIONS; print('provider:', s.LLM_PROVIDER); print('openai key:', bool(s.OPENAI_API_KEY)); print('embedding:', s.EMBEDDING_MODEL, EMBEDDING_DIMENSIONS); print('chat:', s.CHAT_MODEL); print('cutoff:', s.ASK_SIMILARITY_CUTOFF)"
docker compose exec api python manage.py shell -c "from core import llm; print('embedding size:', len(llm.embed(['vacation policy'])[0]))"

docker compose exec -T api python manage.py shell <<'PY'
from core import llm
from documents.models import Chunk, Document
from users.models import User

user = User.objects.get(email="employee@acme.example")
Document.objects.filter(workspace=user.workspace, title="Test Handbook").delete()
doc = Document.objects.create(
    workspace=user.workspace,
    title="Test Handbook",
    file_path="documents/test.pdf",
    file_type=Document.FileType.PDF,
    size=1,
    status=Document.Status.READY,
    uploaded_by=user,
)
text = "Employees receive 20 days of paid vacation each year."
Chunk.objects.create(
    document=doc,
    workspace=user.workspace,
    text=text,
    page=12,
    section="",
    order=0,
    embedding=llm.embed([text])[0],
)
print("Seeded document", doc.id)
PY

TOKEN=$(curl -s -X POST "$API/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"employee@acme.example","password":"employee-local-only"}' \
  | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["access"])')

echo
echo "Answerable question:"
curl -sS -X POST "$API/api/ask" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"question":"How many vacation days do employees get?"}'
echo

docker compose exec api python manage.py shell -c "from ask.models import Answer; a=Answer.objects.latest('id'); print(a.question, '|', a.model_name, '| used_llm:', a.used_llm, '| citations:', a.citations.count())"

echo
echo "Off-topic question:"
curl -sS -X POST "$API/api/ask" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the capital of France?"}'
echo

docker compose exec api python manage.py shell -c "from documents.models import Document; Document.objects.filter(title='Test Handbook').delete(); print('Removed Test Handbook')"
