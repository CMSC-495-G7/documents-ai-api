from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings

from ask.models import Answer, Citation
from ask.providers import ProviderError
from ask.services import NO_ANSWER
from ask.tests.factories import make_chunk, make_ready_document, vector
from documents.tests.factories import make_document
from users.tests.factories import auth_header, make_admin, make_user, make_workspace
from users.tokens import create_access_token


class AskTestCase(TestCase):
    def setUp(self):
        self.user = make_user()
        self.workspace = self.user.workspace

    def ask(self, question="How many vacation days do I get?", user=None):
        token = create_access_token(user or self.user)
        return self.client.post(
            "/api/ask",
            {"question": question},
            content_type="application/json",
            headers=auth_header(token),
        )


@patch("ask.services.generate_answer", return_value="You get 20 vacation days [1].")
@patch("ask.services.embed_question", return_value=vector(0))
class SuccessfulAnswerTests(AskTestCase):
    def test_returns_answer_with_citations(self, embed, generate):
        document = make_ready_document(self.workspace, title="Employee Handbook")
        chunk = make_chunk(
            document,
            text="Employees receive 20 days of paid vacation each year.",
            page=12,
        )

        response = self.ask()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["answer"], "You get 20 vacation days [1].")
        self.assertEqual(body["model"], settings.ASK_LLM_MODEL)
        self.assertEqual(len(body["citations"]), 1)

        citation = body["citations"][0]
        self.assertEqual(citation["chunk_id"], chunk.id)
        self.assertEqual(citation["document_id"], document.id)
        self.assertEqual(citation["document_title"], "Employee Handbook")
        self.assertEqual(citation["page"], 12)
        self.assertIsNone(citation["slide"])
        self.assertIsNone(citation["row_start"])
        self.assertIsNone(citation["row_end"])
        self.assertEqual(citation["text"], chunk.text)
        self.assertAlmostEqual(citation["score"], 1.0)

        generate.assert_called_once()
        question, sources = generate.call_args.args
        self.assertEqual(question, "How many vacation days do I get?")
        self.assertEqual(sources[0].text, chunk.text)

    def test_saves_question_answer_model_and_citations(self, embed, generate):
        document = make_ready_document(self.workspace)
        chunk = make_chunk(document, row_start=4, row_end=6)

        response = self.ask("What is the policy?")

        record = Answer.objects.get(pk=response.json()["id"])
        self.assertEqual(record.workspace, self.workspace)
        self.assertEqual(record.user, self.user)
        self.assertEqual(record.question, "What is the policy?")
        self.assertEqual(record.answer, "You get 20 vacation days [1].")
        self.assertEqual(record.model_name, settings.ASK_LLM_MODEL)
        self.assertTrue(record.used_llm)

        citation = Citation.objects.get(answer=record)
        self.assertEqual(citation.chunk, chunk)
        self.assertEqual(citation.rank, 1)
        self.assertAlmostEqual(citation.score, 1.0)

    def test_admin_can_ask(self, embed, generate):
        self.assertEqual(self.ask(user=make_admin()).status_code, 200)

    def test_only_ready_documents_are_searched(self, embed, generate):
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

    def test_chunks_below_the_cutoff_are_not_cited(self, embed, generate):
        document = make_ready_document(self.workspace)
        make_chunk(document, text="Good match.", chunk_index=0, embedding=vector(0))
        make_chunk(document, text="Unrelated.", chunk_index=1, embedding=vector(1))

        response = self.ask()

        self.assertEqual([c["text"] for c in response.json()["citations"]], ["Good match."])

    def test_row_range_is_returned(self, embed, generate):
        document = make_ready_document(self.workspace)
        make_chunk(document, row_start=2, row_end=8)

        citation = self.ask().json()["citations"][0]
        self.assertEqual(citation["row_start"], 2)
        self.assertEqual(citation["row_end"], 8)


class AskPermissionsTests(AskTestCase):
    def test_no_token_gets_401(self):
        response = self.client.post(
            "/api/ask",
            {"question": "Anything?"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_blank_question_gets_422(self):
        token = create_access_token(self.user)
        response = self.client.post(
            "/api/ask",
            {"question": "   "},
            content_type="application/json",
            headers=auth_header(token),
        )
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


@patch("ask.services.generate_answer")
@patch("ask.services.embed_question", return_value=vector(0))
class NoGoodMatchTests(AskTestCase):
    def test_below_cutoff_skips_the_llm_and_returns_no_citations(self, embed, generate):
        document = make_ready_document(self.workspace)
        make_chunk(document, embedding=vector(1))

        response = self.ask("What is the capital of France?")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["answer"], NO_ANSWER)
        self.assertEqual(body["model"], "")
        self.assertEqual(body["citations"], [])
        generate.assert_not_called()

        record = Answer.objects.get(pk=body["id"])
        self.assertFalse(record.used_llm)
        self.assertFalse(record.citations.exists())

    def test_no_chunks_skips_embedding_and_the_llm(self, embed, generate):
        response = self.ask()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], NO_ANSWER)
        self.assertEqual(response.json()["citations"], [])
        embed.assert_not_called()
        generate.assert_not_called()

    def test_only_unready_documents_skips_the_llm(self, embed, generate):
        document = make_document(self.workspace)
        make_chunk(document)

        response = self.ask()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], NO_ANSWER)
        embed.assert_not_called()
        generate.assert_not_called()


class ProviderFailureTests(AskTestCase):
    @patch("ask.services.generate_answer", side_effect=ProviderError("down"))
    @patch("ask.services.embed_question", return_value=vector(0))
    def test_llm_outage_returns_clear_502(self, embed, generate):
        document = make_ready_document(self.workspace)
        make_chunk(document)

        response = self.ask()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json(),
            {"detail": "The answer service is unavailable. Please try again."},
        )
        self.assertFalse(Answer.objects.exists())

    @patch("ask.services.embed_question", side_effect=ProviderError("down"))
    def test_embedding_outage_returns_clear_502(self, embed):
        document = make_ready_document(self.workspace)
        make_chunk(document)

        response = self.ask()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json(),
            {"detail": "The answer service is unavailable. Please try again."},
        )
        self.assertFalse(Answer.objects.exists())


class MissingConfigurationTests(AskTestCase):
    @override_settings(GEMINI_API_KEY="", ASK_EMBEDDING_API_KEY="", ASK_LLM_API_KEY="")
    def test_unconfigured_service_returns_502(self):
        document = make_ready_document(self.workspace)
        make_chunk(document)

        response = self.ask()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json(),
            {"detail": "The answer service is unavailable. Please try again."},
        )
