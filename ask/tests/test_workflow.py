"""The whole Alpha flow through the API, the way the UI uses it.

Upload -> processing -> ready -> ask -> citation -> history -> saved answer -> file.
Tests run Huey jobs right away and use the fake provider, so no Redis or key is needed.
"""

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from ask.services import NO_ANSWER
from core.llm import LLMError
from documents.tests.factories import TempStorageMixin, pdf_with
from users.tests.factories import auth_header, make_admin, make_user, make_workspace
from users.tokens import create_access_token

POLICY = pdf_with(
    "Parking is in the north garage.",
    "Remote work: employees may work remotely two days per week.",
)
QUESTION = "How many days per week may employees work remotely?"


class WorkflowTestCase(TempStorageMixin, TestCase):
    def setUp(self):
        super().setUp()
        workspace = make_workspace()
        self.admin = make_admin(workspace=workspace)
        self.employee = make_user(workspace=workspace)

    def call(self, method, path, user, **kwargs):
        headers = auth_header(create_access_token(user))
        return getattr(self.client, method)(path, headers=headers, **kwargs)

    def upload(self, content=POLICY, name="Remote Work Policy.pdf"):
        file = SimpleUploadedFile(name, content, content_type="application/pdf")
        # The job is queued after the upload commits, run it like the worker would
        with self.captureOnCommitCallbacks(execute=True):
            response = self.call("post", "/api/documents", self.admin, data={"file": file})
        self.assertEqual(response.status_code, 201)
        return response.json()

    def status_of(self, document_id):
        documents = self.call("get", "/api/documents", self.admin).json()
        return next(doc["status"] for doc in documents if doc["id"] == document_id)

    def ask(self, question=QUESTION):
        return self.call(
            "post", "/api/ask", self.employee,
            data={"question": question}, content_type="application/json",
        )

    def history(self):
        return self.call("get", "/api/ask/history", self.employee).json()


class SuccessfulWorkflowTests(WorkflowTestCase):
    def test_upload_ask_cite_reopen_and_open_the_file(self):
        document = self.upload()
        self.assertEqual(document["status"], "queued")
        self.assertEqual(self.status_of(document["id"]), "ready")

        response = self.ask()
        self.assertEqual(response.status_code, 200)
        answer = response.json()
        citation = answer["citations"][0]
        self.assertEqual(citation["document_id"], document["id"])
        self.assertEqual(citation["document_title"], "Remote Work Policy")
        self.assertEqual(citation["page"], 2)
        self.assertIn("two days per week", citation["text"])

        self.assertEqual([item["id"] for item in self.history()], [answer["id"]])
        saved = self.call("get", f"/api/ask/{answer['id']}", self.employee).json()
        self.assertEqual(saved["question"], QUESTION)
        self.assertEqual(saved["citations"], answer["citations"])

        file = self.call("get", f"/api/documents/{document['id']}/file", self.employee)
        self.assertEqual(file.status_code, 200)
        self.assertEqual(file["Content-Type"], "application/pdf")
        self.assertEqual(b"".join(file.streaming_content), POLICY)

    def test_question_the_documents_cant_answer(self):
        self.upload()

        with patch("core.llm.ask") as llm_ask:
            answer = self.ask("What is the office wifi password?").json()

        llm_ask.assert_not_called()
        self.assertEqual(answer["answer"], NO_ANSWER)
        self.assertEqual(answer["citations"], [])


class FailedWorkflowTests(WorkflowTestCase):
    def test_failed_answer_saves_nothing_and_the_next_one_works(self):
        self.upload()

        with patch("core.llm.ask", side_effect=LLMError("down")), self.assertLogs("ask.api", "WARNING"):
            failed = self.ask()
        self.assertEqual(failed.status_code, 502)
        self.assertEqual(self.history(), [])

        retried = self.ask()
        self.assertEqual(retried.status_code, 200)
        self.assertEqual([item["id"] for item in self.history()], [retried.json()["id"]])

    def test_document_that_fails_processing_is_never_searched(self):
        document = self.upload(pdf_with(""), name="Scanned.pdf")
        self.assertEqual(self.status_of(document["id"]), "failed")

        with patch("core.llm.ask") as llm_ask:
            answer = self.ask().json()

        llm_ask.assert_not_called()
        self.assertEqual(answer["answer"], NO_ANSWER)
