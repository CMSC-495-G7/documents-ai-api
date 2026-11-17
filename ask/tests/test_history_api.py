
from django.test import TestCase

from ask.models import Answer, Citation
from users.tests.factories import auth_header, make_user, make_workspace
from users.tokens import create_access_token


class AskHistoryTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.workspace = self.user.workspace

    def get(self, path, user=None):
        token = create_access_token(user or self.user)
        return self.client.get(path, headers=auth_header(token))

    def make_answer(self, question="What is the policy?", user=None, workspace=None):
        return Answer.objects.create(
            user=user or self.user,
            workspace=workspace or self.workspace,
            question=question,
            answer="The policy is explained here.",
            model_name="fake",
        )

    def test_empty_history(self):
        response = self.get("/api/ask/history")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_history_returns_saved_answers(self):
        answer = self.make_answer()

        response = self.get("/api/ask/history")

        self.assertEqual(response.status_code, 200)
        history = response.json()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["id"], answer.id)
        self.assertEqual(history[0]["question"], answer.question)
        self.assertEqual(history[0]["answer"], answer.answer)
        self.assertEqual(history[0]["model"], "fake")
        self.assertIn("created_at", history[0])

    def test_history_only_shows_own_answers(self):
        own_answer = self.make_answer("My question")
        other_user = make_user(
            email="other@example.com",
            workspace=self.workspace,
        )
        self.make_answer("Someone else's question", user=other_user)

        response = self.get("/api/ask/history")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()],
            [own_answer.id],
        )

    def test_history_returns_latest_50(self):
        answers = [
            self.make_answer(f"Question {i}")
            for i in range(52)
        ]

        response = self.get("/api/ask/history")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()],
            [answer.id for answer in reversed(answers[-50:])],
        )

    def test_get_answer_with_citations(self):
        answer = self.make_answer()
        Citation.objects.create(
            answer=answer,
            document_title="Employee Handbook",
            page=12,
            section="",
            text="Employees receive 20 vacation days.",
            rank=1,
            score=0.95,
        )

        response = self.get(f"/api/ask/{answer.id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], answer.id)
        self.assertEqual(body["answer"], answer.answer)
        self.assertEqual(body["model"], "fake")
        self.assertEqual(len(body["citations"]), 1)
        self.assertEqual(
            body["citations"][0]["document_title"],
            "Employee Handbook",
        )
        self.assertEqual(body["citations"][0]["page"], 12)

    def test_cannot_view_another_users_answer(self):
        other_user = make_user(
            email="other@example.com",
            workspace=self.workspace,
        )
        answer = self.make_answer(user=other_user)

        response = self.get(f"/api/ask/{answer.id}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(), {"detail": "Answer not found."}
        )

    def test_cannot_view_other_workspace_answer(self):
        other_workspace = make_workspace(
            slug="sales", name="Sales"
        )
        answer = self.make_answer(workspace=other_workspace)

        response = self.get(f"/api/ask/{answer.id}")

        self.assertEqual(response.status_code, 404)

    def test_missing_answer_returns_404(self):
        response = self.get("/api/ask/999999")

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_requests_return_401(self):
        answer = self.make_answer()

        for path in (
            "/api/ask/history",
            f"/api/ask/{answer.id}",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 401)
