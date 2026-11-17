from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connections
from django.test import Client, TestCase, TransactionTestCase, override_settings

from ask.models import Answer, Citation
from ask.services import NO_ANSWER
from ask.tests.factories import make_chunk, make_ready_document, vector
from core.llm import LLMError
from documents.models import Chunk, Document
from documents.processing import save_chunks, set_status
from documents.tests.factories import make_document
from users.tests.factories import auth_header, make_admin, make_user, make_workspace
from users.tokens import create_access_token

ANSWER = "You get 20 vacation days [1]."


class AskRequestMixin:
    def setUp(self):
        super().setUp()
        self.user = make_user()
        self.workspace = self.user.workspace

    def ask(self, question="How many vacation days do I get?", user=None, path="/api/ask"):
        token = create_access_token(user or self.user)
        return self.client.post(
            path,
            {"question": question},
            content_type="application/json",
            headers=auth_header(token),
        )


class AskTestCase(AskRequestMixin, TestCase):
    pass


@patch("core.llm.ask", return_value=ANSWER)
@patch("core.llm.embed", return_value=[vector(0)])
class SuccessfulAnswerTests(AskTestCase):
    def test_returns_answer_with_citations(self, embed, ask):
        document = make_ready_document(self.workspace, title="Employee Handbook")
        chunk = make_chunk(
            document,
            text="Employees receive 20 days of paid vacation each year.",
            page=12,
        )

        response = self.ask()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["answer"], ANSWER)
        self.assertEqual(body["model"], "fake")
        self.assertEqual(len(body["citations"]), 1)

        citation = body["citations"][0]
        self.assertEqual(citation["chunk_id"], chunk.id)
        self.assertEqual(citation["document_id"], document.id)
        self.assertEqual(citation["document_title"], "Employee Handbook")
        self.assertEqual(citation["page"], 12)
        self.assertEqual(citation["section"], "")
        self.assertEqual(citation["text"], chunk.text)
        self.assertAlmostEqual(citation["score"], 1.0)

    def test_sends_the_question_and_excerpts_to_the_llm(self, embed, ask):
        document = make_ready_document(self.workspace, title="Employee Handbook")
        make_chunk(document, text="20 days of paid vacation.", page=12)

        self.ask("How many vacation days?")

        prompt, instructions, provider = ask.call_args.args
        self.assertIn("Question: How many vacation days?", prompt)
        self.assertIn("[1] Employee Handbook, page 12\n20 days of paid vacation.", prompt)
        self.assertIn("only the numbered document excerpts", instructions)
        self.assertEqual(provider, "openai")

    def test_docx_excerpts_are_labelled_with_their_heading(self, embed, ask):
        document = make_ready_document(self.workspace, title="Benefits")
        make_chunk(document, section="Dental", page=3)

        self.ask()

        prompt = ask.call_args.args[0]
        self.assertIn("[1] Benefits, Dental\n", prompt)

    def test_saves_question_answer_model_and_citations(self, embed, ask):
        document = make_ready_document(self.workspace)
        chunk = make_chunk(document, section="Dental")

        response = self.ask("What is the policy?")

        record = Answer.objects.get(pk=response.json()["id"])
        self.assertEqual(record.workspace, self.workspace)
        self.assertEqual(record.user, self.user)
        self.assertEqual(record.question, "What is the policy?")
        self.assertEqual(record.answer, ANSWER)
        self.assertEqual(record.model_name, "fake")
        self.assertTrue(record.used_llm)

        citation = Citation.objects.get(answer=record)
        self.assertEqual(citation.chunk, chunk)
        self.assertEqual(citation.section, "Dental")
        self.assertEqual(citation.rank, 1)
        self.assertAlmostEqual(citation.score, 1.0)

    def test_admin_can_ask(self, embed, ask):
        self.assertEqual(self.ask(user=make_admin()).status_code, 200)

    def test_logs_answer_timing(self, embed, ask):
        document = make_ready_document(self.workspace)
        make_chunk(document)

        with self.assertLogs("ask.api", "INFO") as logs:
            self.ask()

        line = logs.output[0].split(":", 2)[2]
        self.assertTrue(line.startswith("Answer "))
        self.assertTrue(line.endswith("s (fake)"))

    def test_only_ready_documents_from_your_workspace_are_searched(self, embed, ask):
        ready = make_ready_document(self.workspace, title="Ready")
        make_chunk(ready, text="Ready text.")

        queued = make_document(self.workspace, title="Queued")
        make_chunk(queued, text="Queued text.")

        other_workspace = make_workspace(slug="sales", name="Sales")
        other = make_ready_document(other_workspace, title="Other workspace")
        make_chunk(other, text="Other text.")

        response = self.ask()

        self.assertEqual(response.status_code, 200)
        citations = response.json()["citations"]
        self.assertEqual([c["document_title"] for c in citations], ["Ready"])

    def test_best_match_comes_first(self, embed, ask):
        document = make_ready_document(self.workspace)
        # Cosine similarity 0.8 with vector(0)
        close = vector(0)
        close[0], close[1] = 0.8, 0.6
        make_chunk(document, text="Close.", order=0, embedding=close)
        make_chunk(document, text="Exact.", order=1, embedding=vector(0))

        citations = self.ask().json()["citations"]

        self.assertEqual([c["text"] for c in citations], ["Exact.", "Close."])
        self.assertAlmostEqual(citations[1]["score"], 0.8, places=5)

    @override_settings(ASK_MAX_CONTEXT_CHUNKS=2)
    def test_sends_at_most_ask_max_context_chunks(self, embed, ask):
        document = make_ready_document(self.workspace)
        for order in range(3):
            make_chunk(document, order=order)

        self.assertEqual(len(self.ask().json()["citations"]), 2)

    def test_chunks_below_the_cutoff_are_not_cited(self, embed, ask):
        document = make_ready_document(self.workspace)
        make_chunk(document, text="Good match.", order=0, embedding=vector(0))
        make_chunk(document, text="Unrelated.", order=1, embedding=vector(1))

        response = self.ask()

        self.assertEqual([c["text"] for c in response.json()["citations"]], ["Good match."])


@patch("core.llm.ask", return_value=ANSWER)
@patch("core.llm.embed", return_value=[vector(0)])
class AnswerProviderTests(AskTestCase):
    def setUp(self):
        super().setUp()
        make_chunk(make_ready_document(self.workspace))

    def use_gemini(self):
        self.workspace.answer_provider = "gemini"
        self.workspace.save()

    def test_uses_the_workspace_provider(self, embed, ask):
        self.use_gemini()

        self.ask()

        self.assertEqual(ask.call_args.args[2], "gemini")

    @override_settings(LLM_PROVIDER="openai", OPENAI_API_KEY="sk-test", CHAT_MODEL="gpt-test")
    def test_saves_the_openai_model_name(self, embed, ask):
        self.assertEqual(self.ask().json()["model"], "gpt-test")

    @override_settings(LLM_PROVIDER="openai", GEMINI_API_KEY="gm-test", GEMINI_CHAT_MODEL="gemini-test")
    def test_saves_the_gemini_model_name(self, embed, ask):
        self.use_gemini()

        self.assertEqual(self.ask().json()["model"], "gemini-test")


@patch("core.llm.ask", return_value=ANSWER)
@patch("core.llm.embed", return_value=[vector(0)])
class SavedCitationTests(AskTestCase):
    def setUp(self):
        super().setUp()
        self.document = make_ready_document(self.workspace, title="Employee Handbook")
        make_chunk(self.document, text="20 days of paid vacation.", page=12)

    def assert_keeps_its_source(self, citation):
        self.assertEqual(citation.document_title, "Employee Handbook")
        self.assertEqual(citation.page, 12)
        self.assertEqual(citation.text, "20 days of paid vacation.")

    def test_survives_the_document_being_processed_again(self, embed, ask):
        answer_id = self.ask().json()["id"]

        # Processing again replaces the chunks
        Chunk.objects.filter(document=self.document).delete()

        citation = Citation.objects.get(answer_id=answer_id)
        self.assertIsNone(citation.chunk)
        self.assertEqual(citation.document, self.document)
        self.assert_keeps_its_source(citation)

    def test_survives_the_document_being_deleted(self, embed, ask):
        answer_id = self.ask().json()["id"]

        self.document.delete()

        citation = Citation.objects.get(answer_id=answer_id)
        self.assertIsNone(citation.chunk)
        self.assertIsNone(citation.document)
        self.assert_keeps_its_source(citation)


class ConcurrentCitationTests(AskRequestMixin, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.document = make_ready_document(self.workspace, title="Employee Handbook")
        make_chunk(self.document, text="20 days of paid vacation.", page=12)

    def ask_while_source_changes(self, change_source):
        def change_on_separate_connection():
            try:
                change_source()
            finally:
                connections.close_all()

        def reply_after_change(*args):
            with ThreadPoolExecutor(max_workers=1) as worker:
                worker.submit(change_on_separate_connection).result()
            return ANSWER

        with (
            patch("core.llm.embed", return_value=[vector(0)]),
            patch("core.llm.ask", side_effect=reply_after_change),
        ):
            response = self.ask()

        self.assertEqual(response.status_code, 200)
        citation = Citation.objects.get(answer_id=response.json()["id"])
        self.assertIsNone(citation.chunk_id)
        self.assertEqual(citation.document_title, "Employee Handbook")
        self.assertEqual(citation.page, 12)
        self.assertEqual(citation.text, "20 days of paid vacation.")
        return citation

    def test_document_deleted_during_answer_generation(self):
        token = create_access_token(make_admin(workspace=self.workspace))

        def delete_document():
            response = Client().delete(
                f"/api/documents/{self.document.pk}", headers=auth_header(token)
            )
            self.assertEqual(response.status_code, 204)

        citation = self.ask_while_source_changes(delete_document)
        self.assertIsNone(citation.document_id)

    def test_chunks_replaced_during_answer_generation(self):
        def replace_chunks():
            document = Document.objects.get(pk=self.document.pk)
            self.assertTrue(set_status(document, Document.Status.PROCESSING))
            replacement = Chunk(text="Updated text.", page=2, order=0)
            self.assertTrue(save_chunks(document, [replacement], [vector(0)]))

        citation = self.ask_while_source_changes(replace_chunks)
        self.assertEqual(citation.document_id, self.document.pk)


class AskPermissionsTests(AskTestCase):
    def test_no_token_gets_401(self):
        response = self.client.post(
            "/api/ask",
            {"question": "Anything?"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_blank_question_gets_422(self):
        response = self.ask("   ")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "Ask a question."})

    def test_missing_question_gets_422(self):
        token = create_access_token(self.user)
        response = self.client.post(
            "/api/ask",
            {},
            content_type="application/json",
            headers=auth_header(token),
        )
        self.assertEqual(response.status_code, 422)


@patch("core.llm.ask")
@patch("core.llm.embed", return_value=[vector(0)])
class NoGoodMatchTests(AskTestCase):
    def test_below_cutoff_skips_the_llm_and_returns_no_citations(self, embed, ask):
        document = make_ready_document(self.workspace)
        make_chunk(document, embedding=vector(1))

        response = self.ask("What is the capital of France?")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["answer"], NO_ANSWER)
        self.assertEqual(body["model"], "")
        self.assertEqual(body["citations"], [])
        ask.assert_not_called()

        record = Answer.objects.get(pk=body["id"])
        self.assertFalse(record.used_llm)
        self.assertFalse(record.citations.exists())

    def test_no_chunks_skips_embedding_and_the_llm(self, embed, ask):
        response = self.ask()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], NO_ANSWER)
        self.assertEqual(response.json()["citations"], [])
        embed.assert_not_called()
        ask.assert_not_called()

    def test_only_unready_documents_skips_the_llm(self, embed, ask):
        document = make_document(self.workspace)
        make_chunk(document)

        response = self.ask()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], NO_ANSWER)
        embed.assert_not_called()
        ask.assert_not_called()


class ProviderFailureTests(AskTestCase):
    def setUp(self):
        super().setUp()
        make_chunk(make_ready_document(self.workspace))

    def assert_clear_502(self, response):
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json(),
            {"detail": "The answer service is unavailable. Please try again."},
        )
        self.assertFalse(Answer.objects.exists())

    @patch("core.llm.ask", side_effect=LLMError("down"))
    @patch("core.llm.embed", return_value=[vector(0)])
    def test_llm_outage_returns_clear_502(self, embed, ask):
        self.assert_clear_502(self.ask())

    @patch("core.llm.embed", side_effect=LLMError("down"))
    def test_embedding_outage_returns_clear_502(self, embed):
        self.assert_clear_502(self.ask())

    @override_settings(LLM_PROVIDER="openai", GEMINI_API_KEY="gm-test")
    @patch("core.llm.embed", return_value=[vector(0)])
    @patch("core.llm.openai.OpenAI")
    def test_empty_gemini_completion_returns_clear_502(self, client_class, embed):
        self.workspace.answer_provider = "gemini"
        self.workspace.save(update_fields=["answer_provider"])
        completion = client_class.return_value.chat.completions.create
        for choices in (
            [],
            [SimpleNamespace(message=SimpleNamespace())],
            [SimpleNamespace(message=SimpleNamespace(content=None))],
            [SimpleNamespace(message=SimpleNamespace(content="  "))],
        ):
            with self.subTest(choices=choices):
                completion.return_value = SimpleNamespace(choices=choices)
                self.assert_clear_502(self.ask())

    @override_settings(LLM_PROVIDER="openai", OPENAI_API_KEY="")
    def test_missing_key_returns_clear_502(self):
        self.assert_clear_502(self.ask())

    @patch("core.llm.ask", side_effect=LLMError("down"))
    @patch("core.llm.embed", return_value=[vector(0)])
    def test_other_endpoints_still_work_after_502(self, embed, ask):
        self.assert_clear_502(self.ask())

        token = create_access_token(self.user)
        response = self.client.get("/api/documents", headers=auth_header(token))

        self.assertEqual(response.status_code, 200)


class AskStreamTests(AskTestCase):
    def test_is_not_built_yet(self):
        response = self.ask(path="/api/ask/stream")
        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json(), {"detail": "Streaming answers aren't available yet."})

    def test_no_token_gets_401(self):
        response = self.client.post(
            "/api/ask/stream",
            {"question": "Anything?"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
