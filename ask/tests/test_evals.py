import csv
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from ask.evals import load_questions, not_found, retrieval_hit, summarize
from ask.models import Answer
from ask.services import NO_ANSWER
from ask.tests.factories import make_chunk, make_ready_document
from core.llm import fake_vector
from users.tests.factories import make_user

HANDBOOK = {"id": "A01", "kind": "answerable", "question": "How many vacation days do employees get each year?",
            "document": "Handbook", "pages": [3, 4]}
OFF_TOPIC = {"id": "U01", "kind": "unanswerable", "question": "What is the capital of France?"}


def cited(title, page):
    return {"document_title": title, "page": page, "score": 0.6}


def row(kind, seconds=5, hit=True, found=True):
    if kind == "answerable":
        return {"kind": kind, "seconds": seconds, "retrieval_hit": hit}
    return {"kind": kind, "seconds": seconds, "not_found": found}


class QuestionSetTests(SimpleTestCase):
    """The real set in evals/questions.json."""

    def setUp(self):
        self.questions = load_questions(Path(settings.BASE_DIR) / "evals" / "questions.json")

    def test_has_15_answerable_and_5_unanswerable(self):
        kinds = [question["kind"] for question in self.questions]
        self.assertEqual(kinds.count("answerable"), 15)
        self.assertEqual(kinds.count("unanswerable"), 5)

    def test_ids_are_unique(self):
        ids = [question["id"] for question in self.questions]
        self.assertEqual(len(ids), len(set(ids)))

    def test_answerable_questions_name_a_sample_document_and_pages(self):
        samples = {
            "FINA 2.30.015 Expense and Reimbursement CLEAN for Posting",
            "Remote-Work-POLICY",
            "staff-handbook-california",
            "staff-loa-policy",
            "wfp-onboarding-checklist",
        }
        for question in self.questions:
            if question["kind"] == "answerable":
                with self.subTest(question=question["id"]):
                    self.assertIn(question["document"], samples)
                    self.assertTrue(all(isinstance(page, int) and page > 0 for page in question["pages"]))


class LoadQuestionsTests(SimpleTestCase):
    def load(self, questions):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "questions.json"
            path.write_text(json.dumps(questions), encoding="utf-8")
            return load_questions(path)

    def test_unknown_kind_is_an_error(self):
        with self.assertRaisesMessage(ValueError, "A01: kind must be one of"):
            self.load([{**HANDBOOK, "kind": "maybe"}])

    def test_answerable_needs_pages(self):
        with self.assertRaisesMessage(ValueError, "A01: answerable questions need a document and pages"):
            self.load([{**HANDBOOK, "pages": []}])


class RetrievalHitTests(SimpleTestCase):
    def test_hit_when_a_citation_is_the_right_document_and_page(self):
        self.assertTrue(retrieval_hit(HANDBOOK, [cited("Policy", 1), cited("Handbook", 4)]))

    def test_miss_on_the_wrong_page(self):
        self.assertFalse(retrieval_hit(HANDBOOK, [cited("Handbook", 9)]))

    def test_miss_on_the_wrong_document(self):
        self.assertFalse(retrieval_hit(HANDBOOK, [cited("Policy", 3)]))

    def test_miss_without_citations(self):
        self.assertFalse(retrieval_hit(HANDBOOK, []))


class NotFoundTests(SimpleTestCase):
    def test_the_not_found_reply_without_the_llm(self):
        self.assertTrue(not_found(NO_ANSWER, used_llm=False))

    def test_an_answer_is_not_not_found(self):
        self.assertFalse(not_found("Paris [1].", used_llm=True))


class SummarizeTests(SimpleTestCase):
    def test_counts_hits_not_found_and_fast_answers(self):
        rows = [
            row("answerable", hit=True),
            row("answerable", hit=False, seconds=31),
            row("unanswerable", found=True),
        ]

        summary = summarize(rows)

        self.assertEqual(summary["retrieval_hits"], 1)
        self.assertEqual(summary["answerable"], 2)
        self.assertEqual(summary["not_found"], 1)
        self.assertEqual(summary["unanswerable"], 1)
        self.assertEqual(summary["fast"], 2)
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["slowest_seconds"], 31)

    def test_all_targets_met(self):
        rows = [row("answerable")] * 12 + [row("answerable", hit=False)] * 3 + [row("unanswerable")] * 4 + [
            row("unanswerable", found=False)
        ]

        self.assertEqual(summarize(rows)["met"], {"retrieval": True, "not_found": True, "speed": True})

    def test_targets_missed(self):
        rows = [row("answerable", hit=False, seconds=40)] * 15 + [row("unanswerable", found=False)] * 5

        self.assertEqual(summarize(rows)["met"], {"retrieval": False, "not_found": False, "speed": False})

    def test_30_seconds_is_too_slow(self):
        self.assertEqual(summarize([row("answerable", seconds=30)])["fast"], 0)


class RunEvalCommandTests(TestCase):
    """The whole command, with the fake provider."""

    def setUp(self):
        self.user = make_user()
        document = make_ready_document(self.user.workspace, title="Handbook")
        text = "Employees get 20 vacation days each year."
        make_chunk(document, text=text, page=3, embedding=fake_vector(text))

        self.folder = Path(tempfile.mkdtemp())
        self.questions = self.folder / "questions.json"
        self.questions.write_text(json.dumps([HANDBOOK, OFF_TOPIC]), encoding="utf-8")

    def run_eval(self, **options):
        output = StringIO()
        call_command(
            "run_eval", questions=str(self.questions), out=str(self.folder / "results"),
            commit="abc1234", stdout=output, **options,
        )
        return output.getvalue()

    def test_scores_every_question_and_writes_a_report(self):
        output = self.run_eval()

        self.assertIn("Retrieval hits: 1/1", output)
        self.assertIn("Not found:      1/1", output)
        report = next((self.folder / "results").glob("*-abc1234.json"))
        data = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(data["config"]["commit"], "abc1234")
        self.assertEqual(data["config"]["cutoff"], settings.ASK_SIMILARITY_CUTOFF)
        self.assertEqual(data["config"]["embedding_model"], "fake")
        self.assertEqual([r["id"] for r in data["rows"]], ["A01", "U01"])
        self.assertTrue(data["rows"][0]["retrieval_hit"])
        self.assertEqual(data["rows"][0]["top_match"]["page"], 3)

    def test_adds_one_line_per_run_to_runs_csv(self):
        self.run_eval()
        self.run_eval()

        with (self.folder / "results" / "runs.csv").open(encoding="utf-8") as file:
            runs = list(csv.DictReader(file))
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0]["commit"], "abc1234")
        self.assertEqual(runs[0]["retrieval_hits"], "1")

    def test_removes_its_answers_from_history(self):
        self.run_eval()
        self.assertFalse(Answer.objects.exists())

    def test_can_keep_its_answers(self):
        self.run_eval(keep_answers=True)
        self.assertEqual(Answer.objects.count(), 2)

    def test_needs_ready_documents(self):
        self.user.workspace.documents.all().delete()

        with self.assertRaisesMessage(CommandError, "Upload the sample PDFs first"):
            self.run_eval()

    def test_needs_the_user(self):
        with self.assertRaisesMessage(CommandError, "No user nobody@acme.example"):
            self.run_eval(email="nobody@acme.example")
