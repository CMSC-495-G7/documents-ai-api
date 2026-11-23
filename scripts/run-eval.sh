#!/usr/bin/env bash
# Phase 4.6 eval on your running stack: uploads the sample PDFs (once), waits for
# them to be ready, then asks the 20 questions in evals/questions.json.
# Run from the API folder: bash scripts/run-eval.sh
# Needs a real OPENAI_API_KEY in .env, the fake provider's scores mean nothing.
set -euo pipefail

API=${API:-http://127.0.0.1:8000}
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@acme.example}
ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin-local-only}
# Git Bash on Windows often has python but not python3
PY=$(command -v python3 || command -v python)

docker compose up -d --wait

TOKEN=$(curl -sf -X POST "$API/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
  | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["access"])')

titles() {
  curl -sf "$API/api/documents" -H "Authorization: Bearer $TOKEN" \
    | "$PY" -c 'import json,sys; [print(d["title"], d["status"], sep="\t") for d in json.load(sys.stdin)]'
}

# Upload the samples that aren't there yet
existing=$(titles | cut -f1)
for file in samples/*.pdf; do
  title=$(basename "$file" .pdf)
  if grep -qxF "$title" <<<"$existing"; then
    echo "Already uploaded: $title"
  else
    echo "Uploading: $title"
    curl -sf -X POST "$API/api/documents" -H "Authorization: Bearer $TOKEN" -F "file=@$file" >/dev/null
  fi
done

# Wait until nothing is queued or processing (about a minute for all five)
for _ in $(seq 1 60); do
  pending=$(titles | grep -cE $'\t(queued|processing)$' || true)
  [ "$pending" -eq 0 ] && break
  echo "Waiting for $pending document(s) to finish processing..."
  sleep 5
done
titles

COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
docker compose exec api python manage.py run_eval --commit "$COMMIT"
