"""Phase 4.6: ask the evaluation questions and score the answers.

Upload the sample PDFs first (evals/README.md), then:
    docker compose exec api python manage.py run_eval --commit $(git rev-parse --short HEAD)
"""

import csv
import json
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ask.evals import SLOW_SECONDS, load_questions, score, summarize
from ask.models import Answer
from ask.services import ask_question, search, searchable_chunks
from core import llm
from users.models import User

CSV_COLUMNS = [
    "date", "commit", "llm_provider", "embedding_model", "answer_model", "cutoff",
    "retrieval_hits", "answerable", "not_found", "unanswerable", "fast", "total",
    "slowest_seconds", "report",
]


class Command(BaseCommand):
    help = "Ask the evaluation questions as a user, score the answers and save a report."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="employee@acme.example", help="Who asks the questions")
        parser.add_argument("--questions", default="evals/questions.json")
        parser.add_argument("--out", default="evals/results", help="Where the reports go")
        # The container has no .git, so the commit comes from outside
        parser.add_argument("--commit", default="unknown", help="git rev-parse --short HEAD")
        parser.add_argument("--keep-answers", action="store_true", help="Keep them in the user's history")

    def handle(self, *args, **options):
        questions = load_questions(options["questions"])
        user = User.objects.filter(email=options["email"]).select_related("workspace").first()
        if user is None:
            raise CommandError(f"No user {options['email']}. Run seed_identity first.")
        if not searchable_chunks(user).exists():
            raise CommandError("No ready documents in that workspace. Upload the sample PDFs first (evals/README.md).")

        config = run_config(user, options["commit"])
        rows = []
        created = []
        try:
            for question in questions:
                rows.append(self.ask(user, question, created))
        finally:
            # The report keeps every answer, the history doesn't need 20 test questions
            if not options["keep_answers"]:
                Answer.objects.filter(pk__in=created).delete()

        summary = summarize(rows)
        report = write_report(Path(options["out"]), config, summary, rows)
        self.print_summary(summary, report)

    def ask(self, user, question, created):
        # Best match even under the cutoff, to see how close a miss was
        matches = search(question["question"], user)
        started = time.monotonic()
        try:
            answer = ask_question(user, question["question"])
        except llm.LLMError as error:
            raise CommandError(f"{question['id']}: the AI service failed: {error}") from error
        seconds = time.monotonic() - started
        created.append(answer.pk)

        citations = [
            {"document_title": c.document_title, "page": c.page, "score": round(c.score, 3)}
            for c in answer.citations.all()
        ]
        row = score(question, answer.answer, answer.used_llm, citations, seconds)
        if matches:
            chunk, top_score = matches[0]
            row["top_match"] = {"document_title": chunk.document.title, "page": chunk.page, "score": round(top_score, 3)}

        self.stdout.write(f"{question['id']}  {result_label(row):9}  {row['seconds']:5.1f} s  {question['question']}")
        return row

    def print_summary(self, summary, report):
        met = summary["met"]
        self.stdout.write("")
        self.stdout.write(
            f"Retrieval hits: {summary['retrieval_hits']}/{summary['answerable']} (target 12/15) "
            f"{'met' if met['retrieval'] else 'NOT met'}"
        )
        self.stdout.write(
            f"Not found:      {summary['not_found']}/{summary['unanswerable']} (target 4/5) "
            f"{'met' if met['not_found'] else 'NOT met'}"
        )
        self.stdout.write(
            f"Under {SLOW_SECONDS} s:    {summary['fast']}/{summary['total']} (target 9 of 10) "
            f"{'met' if met['speed'] else 'NOT met'}, slowest {summary['slowest_seconds']} s"
        )
        self.stdout.write(f"Report: {report}")


def result_label(row):
    if row["kind"] == "answerable":
        return "hit" if row["retrieval_hit"] else "miss"
    return "not found" if row["not_found"] else "ANSWERED"


def run_config(user, commit):
    provider = user.workspace.answer_provider
    fake = settings.LLM_PROVIDER == "fake"
    return {
        "date": timezone.now().isoformat(timespec="seconds"),
        "commit": commit,
        "llm_provider": settings.LLM_PROVIDER,
        "embedding_model": "fake" if fake else settings.EMBEDDING_MODEL,
        "answer_provider": provider,
        "answer_model": llm.answer_model(provider),
        "cutoff": settings.ASK_SIMILARITY_CUTOFF,
        "max_chunks": settings.ASK_MAX_CONTEXT_CHUNKS,
    }


def write_report(out, config, summary, rows):
    """A JSON file per run, and one line per run in runs.csv to compare them."""
    out.mkdir(parents=True, exist_ok=True)
    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    report = out / f"{stamp}-{config['commit']}.json"
    report.write_text(json.dumps({"config": config, "summary": summary, "rows": rows}, indent=2), encoding="utf-8")

    runs = out / "runs.csv"
    new_file = not runs.exists()
    with runs.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow({
            **{key: config[key] for key in ("date", "commit", "llm_provider", "embedding_model", "answer_model", "cutoff")},
            **{key: summary[key] for key in ("retrieval_hits", "answerable", "not_found", "unanswerable", "fast", "total", "slowest_seconds")},
            "report": report.name,
        })
    return report
