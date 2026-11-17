from django.test import TestCase, override_settings

from users.models import Workspace
from users.tests.factories import auth_header, make_admin, make_user, make_workspace
from users.tokens import create_access_token

BOTH_KEYS = {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "sk-test", "GEMINI_API_KEY": "gm-test"}


class AskSettingsTestCase(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.workspace = self.admin.workspace

    def get_settings(self, user=None):
        token = create_access_token(user or self.admin)
        return self.client.get("/api/ask/settings", headers=auth_header(token))

    def update_settings(self, provider, user=None):
        token = create_access_token(user or self.admin)
        return self.client.patch(
            "/api/ask/settings",
            {"answer_provider": provider},
            content_type="application/json",
            headers=auth_header(token),
        )


class GetSettingsTests(AskSettingsTestCase):
    @override_settings(**BOTH_KEYS)
    def test_openai_is_the_default(self):
        response = self.get_settings()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "answer_provider": "openai",
                "providers": [
                    {"id": "openai", "label": "OpenAI", "available": True},
                    {"id": "gemini", "label": "Gemini", "available": True},
                ],
            },
        )

    @override_settings(LLM_PROVIDER="openai", OPENAI_API_KEY="sk-test", GEMINI_API_KEY="")
    def test_provider_without_a_key_is_not_available(self):
        providers = self.get_settings().json()["providers"]
        self.assertEqual([p["available"] for p in providers], [True, False])

    def test_employees_can_read_it(self):
        self.assertEqual(self.get_settings(user=make_user()).status_code, 200)

    def test_no_token_gets_401(self):
        self.assertEqual(self.client.get("/api/ask/settings").status_code, 401)


@override_settings(**BOTH_KEYS)
class UpdateSettingsTests(AskSettingsTestCase):
    def test_admin_switches_to_gemini(self):
        response = self.update_settings("gemini")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer_provider"], "gemini")
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.answer_provider, "gemini")

    def test_only_changes_your_workspace(self):
        other = make_workspace(slug="sales", name="Sales")

        self.update_settings("gemini")

        other.refresh_from_db()
        self.assertEqual(other.answer_provider, Workspace.AnswerProvider.OPENAI)

    def test_employee_gets_403(self):
        response = self.update_settings("gemini", user=make_user())

        self.assertEqual(response.status_code, 403)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.answer_provider, "openai")

    def test_unknown_provider_gets_422(self):
        response = self.update_settings("carrier-pigeon")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "Pick OpenAI or Gemini."})

    @override_settings(GEMINI_API_KEY="")
    def test_provider_without_a_key_gets_422(self):
        response = self.update_settings("gemini")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "Gemini has no API key on the server."})
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.answer_provider, "openai")
