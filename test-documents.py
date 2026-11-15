#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "documents for testing"
API = os.environ.get("DOCUMENTS_AI_API_URL", "http://127.0.0.1:8000/api").rstrip("/")
EMAIL = os.environ.get("SEED_EMPLOYEE_EMAIL", "employee@acme.example")
PASSWORD = os.environ.get("SEED_EMPLOYEE_PASSWORD", "employee-local-only")
COMPOSE = ["docker", "compose"]

QUESTIONS = [
    {
        "question": "How many PTO days do full-time employees get after three completed years of service?",
        "expect_any": ["20 days", "160 hours"],
        "expect_doc": "pto_policy",
    },
    {
        "question": "When should an employee notify their manager about their illness?",
        "expect_any": ["as soon as practical", "before their scheduled start time"],
        "expect_doc": "pto_policy",
    },
    {
        "question": "What is the maximum meal reimbursement during approved business travel?",
        "expect_any": ["$60", "60 per person"],
        "expect_doc": "expense_policy",
    },
    {
        "question": "Do I need to get manager approval for expenses above $250?",
        "expect_any": ["$250", "written manager approval"],
        "expect_doc": "expense_policy",
    },
    {
        "question": "What are IT Support hours?",
        "expect_any": ["8:00", "6:00", "8 a.m."],
        "expect_doc": "it_support_troubleshooting_manual",
    },
    { 
        "question": "How many sick-leave hours do full-time employees get each calendar year?",
        "expect_any": ["48 hours"],
        "expect_doc": "pto_policy",
    },
    {
        "question": "What is the maximum PTO balance I can carry over?",
        "expect_any": ["200 hours"],
        "expect_doc": "pto_policy",
    },
    {
        "question": "What should I do if I suspect a phishing email?",
        "expect_any": ["security@documentai.example", "it support", "it portal"],
        "expect_doc": "it_support_troubleshooting_manual",
    },
    {
        "question": "Who should I contact with expense questions?",
        "expect_any": ["finance@documentai.example"],
        "expect_doc": "expense_policy",
    },
    {
        "question": "What are the standard office collaboration hours?",
        "expect_any": ["9:00", "3:00"],
        "expect_doc": "employee_handbook",
    },
    {
        "question": "How much PTO do employees with fewer than three years of service get each year?",
        "expect_any": ["15 days", "120 hours"],
        "expect_doc": "pto_policy",
    },
    {
        "question": "How far in advance should I submit planned PTO for a five-day vacation?",
        "expect_any": ["20 calendar days", "20 days"],
        "expect_doc": "pto_policy",
    },
    {
        "question": "What is the receipt threshold for expense reports?",
        "expect_any": ["$25", "25"],
        "expect_doc": "expense_policy",
    },
    {
        "question": "How many days do I have to submit an expense after the transaction?",
        "expect_any": ["30 calendar days", "30 days"],
        "expect_doc": "expense_policy",
    },
    {
        "question": "When is Finance approval also required for an expense?",
        "expect_any": ["$1,000", "1,000"],
        "expect_doc": "expense_policy",
    },
    {
        "question": "What is the target initial response time for a Priority 1 IT ticket?",
        "expect_any": ["30 minutes"],
        "expect_doc": "it_support_troubleshooting_manual",
    },
    {
        "question": "What should I do if my account is locked?",
        "expect_any": ["submit a ticket", "stop repeated"],
        "expect_doc": "it_support_troubleshooting_manual",
    },
    {
        "question": "Who owns the onboarding checklist?",
        "expect_any": ["people operations"],
        "expect_doc": "onboarding_checklist",
    },
    {
        "question": "Do I need approval to work from another state or country?",
        "expect_any": ["written approval", "people operations"],
        "expect_doc": "remote_work_policy",
    },
    {
        "question": "Which holidays does DocumentAI observe?",
        "expect_any": ["memorial day", "thanksgiving", "christmas"],
        "expect_doc": "pto_policy",
    },
    {
        "question": "What should I do if I receive an unexpected MFA prompt?",
        "expect_any": ["escalate", "compromise", "report"],
        "expect_doc": "it_support_troubleshooting_manual",
    },
    {
        "question": "What is the capital of France?",
        "expect_any": ["couldn't find", "could not find"],
        "expect_doc": None,
    },
]

INGEST_SCRIPT = r'''
import json
from pathlib import Path
from time import sleep

from ask.models import Chunk
from ask.providers import ProviderError, embed_question
from documents.models import Document
from users.models import User, Workspace

payload = json.loads(Path("/tmp/testing-docs.json").read_text())
workspace = Workspace.objects.get(slug="engineering")
uploader = (
    User.objects.filter(workspace=workspace, role=User.Role.ADMIN).first()
    or User.objects.filter(workspace=workspace).first()
)

titles = [item["title"] for item in payload] + ["Test Handbook"]
deleted, _ = Document.objects.filter(workspace=workspace, title__in=titles).delete()
print(f"Removed {deleted} existing test rows.")

for item in payload:
    document = Document.objects.create(
        workspace=workspace,
        title=item["title"],
        file_path=f"documents for testing/{item['title']}.{item['file_type']}",
        file_type=item["file_type"],
        size=item["size"],
        status=Document.Status.READY,
        uploaded_by=uploader,
    )
    for index, chunk in enumerate(item["chunks"]):
        last_error = None
        for attempt in range(3):
            try:
                embedding = embed_question(chunk["text"])
                break
            except ProviderError as exc:
                last_error = exc
                if attempt < 2:
                    sleep(2)
        else:
            raise last_error
        Chunk.objects.create(
            document=document,
            chunk_index=index,
            text=chunk["text"],
            page=chunk.get("page"),
            slide=chunk.get("slide"),
            row_start=chunk.get("row_start"),
            row_end=chunk.get("row_end"),
            embedding=embedding,
        )
    print(f"Ingested {document.title}: {len(item['chunks'])} chunks")

print("Documents:", Document.objects.filter(workspace=workspace).count())
print("Chunks:", Chunk.objects.filter(document__workspace=workspace).count())
'''


def split_text(text, max_chars=1100, overlap=180):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            for index in range(0, len(sentence), max_chars - overlap):
                chunks.append(sentence[index:index + max_chars].strip())
            continue
        if len(current) + len(sentence) + 1 <= max_chars:
            current = (current + " " + sentence).strip()
        else:
            chunks.append(current.strip())
            tail = current[-overlap:] if overlap else ""
            current = (tail + " " + sentence).strip()
    if current.strip():
        chunks.append(current.strip())
    return [chunk for chunk in chunks if chunk]


def extract_documents():
    try:
        from docx import Document
        from pypdf import PdfReader
    except ImportError:
        print("Missing host dependencies. Run: python3 -m pip install pypdf python-docx")
        sys.exit(1)

    documents = []
    for path in sorted(SOURCE.iterdir()):
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            reader = PdfReader(str(path))
            chunks = []
            for page_number, page in enumerate(reader.pages, start=1):
                for text in split_text(page.extract_text() or ""):
                    chunks.append({
                        "text": text,
                        "page": page_number,
                        "slide": None,
                        "row_start": None,
                        "row_end": None,
                    })
            documents.append({
                "title": path.stem,
                "file_type": "pdf",
                "size": path.stat().st_size,
                "chunks": chunks,
            })
        elif suffix == ".docx":
            doc = Document(str(path))
            lines = [paragraph.text.strip() for paragraph in doc.paragraphs if paragraph.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    values = [cell.text.strip() for cell in row.cells]
                    if any(values):
                        lines.append(" | ".join(values))
            chunks = []
            for text in split_text("\n".join(lines)):
                chunks.append({
                    "text": text,
                    "page": None,
                    "slide": None,
                    "row_start": None,
                    "row_end": None,
                })
            documents.append({
                "title": path.stem,
                "file_type": "docx",
                "size": path.stat().st_size,
                "chunks": chunks,
            })
    return documents


def run_compose(*args, timeout=None, input_text=None):
    return subprocess.run(
        [*COMPOSE, *args],
        cwd=ROOT,
        check=True,
        text=True,
        timeout=timeout,
        input=input_text,
    )


def post(path, payload, token=None, attempts=1):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        API + path,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in (502, 503, 504) and attempt + 1 < attempts:
                print(f"  Provider returned {exc.code}; retrying...", flush=True)
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"{exc.code} from {path}: {body}") from exc
        except urllib.error.URLError as exc:
            if attempt + 1 < attempts:
                print(f"  Connection failed; retrying...", flush=True)
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"Could not reach {API}. Is the API running? {exc}") from exc
    raise RuntimeError(f"Request to {path} failed after {attempts} attempts.")


def main():
    if not SOURCE.is_dir():
        print(f"Missing folder: {SOURCE}")
        sys.exit(1)

    documents = extract_documents()
    if not documents:
        print("No PDF or DOCX files found.")
        sys.exit(1)

    print("Starting services...")
    run_compose("up", "-d", "--wait", timeout=300)

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(documents, handle)
        json_path = handle.name
    os.chmod(json_path, 0o644)

    try:
        print("Copying extracted text into the API container...")
        run_compose("cp", json_path, "api:/tmp/testing-docs.json", timeout=120)
        print("Embedding and saving documents...")
        run_compose("exec", "-T", "api", "python", "manage.py", "shell", timeout=900, input_text=INGEST_SCRIPT)
    finally:
        Path(json_path).unlink(missing_ok=True)

    print("\nSigning in...")
    login = post("/auth/login", {"email": EMAIL, "password": PASSWORD}, attempts=3)
    token = login["access"]

    failures = 0
    for item in QUESTIONS:
        result = post("/ask", {"question": item["question"]}, token, attempts=4)
        answer = result["answer"]
        cited = [citation["document_title"] for citation in result["citations"]]
        answer_ok = any(token.lower() in answer.lower() for token in item["expect_any"])
        citation_ok = item["expect_doc"] is None or item["expect_doc"] in cited

        status = "PASS" if answer_ok and citation_ok else "FAIL"
        if status == "FAIL":
            failures += 1

        print(f"\n[{status}] {item['question']}")
        print(f"  Answer: {answer}")
        print(f"  Cited: {', '.join(dict.fromkeys(cited)) or 'none'}")
        if not answer_ok:
            print(f"  Expected answer to mention one of: {item['expect_any']}")
        if not citation_ok:
            print(f"  Expected citation from: {item['expect_doc']}")

    print(f"\n{len(QUESTIONS) - failures}/{len(QUESTIONS)} checks passed.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
