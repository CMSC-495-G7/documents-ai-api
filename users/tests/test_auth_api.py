from django.test import TestCase, override_settings

from users.tests.factories import PASSWORD, auth_header, make_admin, make_user
from users.tokens import create_access_token, create_refresh_token


class LoginTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def login(self, email, password):
        return self.client.post(
            "/api/auth/login", {"email": email, "password": password}, content_type="application/json"
        )

    def test_good_login_returns_both_tokens(self):
        response = self.login(self.user.email, PASSWORD)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"access", "refresh"})

    def test_login_ignores_email_case_and_spaces(self):
        response = self.login("  EMPLOYEE@acme.example ", PASSWORD)
        self.assertEqual(response.status_code, 200)

    def test_wrong_password(self):
        response = self.login(self.user.email, "wrong")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Incorrect email or password."})

    def test_unknown_email_gets_the_same_message(self):
        response = self.login("nobody@acme.example", PASSWORD)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Incorrect email or password."})

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.login(self.user.email, PASSWORD).status_code, 401)


class RefreshTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def refresh(self, token):
        return self.client.post("/api/auth/refresh", {"refresh": token}, content_type="application/json")

    def test_refresh_returns_a_working_access_token(self):
        response = self.refresh(create_refresh_token(self.user))
        self.assertEqual(response.status_code, 200)

        access = response.json()["access"]
        me = self.client.get("/api/auth/me", headers=auth_header(access))
        self.assertEqual(me.status_code, 200)

    def test_access_token_cannot_be_used_to_refresh(self):
        response = self.refresh(create_access_token(self.user))
        self.assertEqual(response.status_code, 401)

    def test_expired_refresh_token(self):
        with override_settings(JWT_REFRESH_TOKEN_DAYS=-1):
            token = create_refresh_token(self.user)
        self.assertEqual(self.refresh(token).status_code, 401)

    def test_garbage_token(self):
        self.assertEqual(self.refresh("not-a-token").status_code, 401)

    def test_deactivated_user_cannot_refresh(self):
        token = create_refresh_token(self.user)
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.refresh(token).status_code, 401)


class MeTests(TestCase):
    def test_me_with_a_token(self):
        admin = make_admin()
        response = self.client.get("/api/auth/me", headers=auth_header(create_access_token(admin)))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": admin.id,
                "email": "admin@acme.example",
                "role": "admin",
                "workspace": {"id": admin.workspace.id, "name": "Engineering", "slug": "engineering"},
            },
        )

    def test_me_without_a_token(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_me_with_an_expired_token(self):
        user = make_user()
        with override_settings(JWT_ACCESS_TOKEN_MINUTES=-1):
            token = create_access_token(user)
        self.assertEqual(self.client.get("/api/auth/me", headers=auth_header(token)).status_code, 401)

    def test_refresh_token_cannot_be_used_as_access_token(self):
        token = create_refresh_token(make_user())
        self.assertEqual(self.client.get("/api/auth/me", headers=auth_header(token)).status_code, 401)
