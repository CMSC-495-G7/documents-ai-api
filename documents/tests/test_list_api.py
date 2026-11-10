from django.test import TestCase

from documents.tests.factories import make_document
from users.tests.factories import auth_header, make_admin, make_user, make_workspace
from users.tokens import create_access_token


class ListDocumentsTests(TestCase):
    def setUp(self):
        self.engineering = make_workspace()
        self.sales = make_workspace(slug="sales", name="Sales")
        self.admin = make_admin(workspace=self.engineering)
        self.employee = make_user(workspace=self.engineering)

    def list_as(self, user):
        return self.client.get("/api/documents", headers=auth_header(create_access_token(user)))

    def titles(self, response):
        return [document["title"] for document in response.json()]

    def test_only_lists_my_workspace(self):
        make_document(self.engineering, title="Handbook")
        make_document(self.sales, title="Sales playbook")

        response = self.list_as(self.admin)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.titles(response), ["Handbook"])

    def test_newest_first(self):
        make_document(self.engineering, title="Older")
        make_document(self.engineering, title="Newer")
        self.assertEqual(self.titles(self.list_as(self.admin)), ["Newer", "Older"])

    def test_employees_can_list_too(self):
        make_document(self.engineering, title="Handbook")
        self.assertEqual(self.titles(self.list_as(self.employee)), ["Handbook"])

    def test_empty_workspace_gets_an_empty_list(self):
        make_document(self.sales, title="Sales playbook")
        response = self.list_as(self.admin)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_shows_the_fields_the_ui_needs(self):
        make_document(self.engineering, title="Handbook", uploaded_by=self.admin, size=2048)
        document = self.list_as(self.employee).json()[0]

        self.assertEqual(document["title"], "Handbook")
        self.assertEqual(document["size"], 2048)
        self.assertEqual(document["status"], "queued")
        self.assertEqual(document["uploaded_by"], "admin@acme.example")
        self.assertNotIn("file_path", document)

    def test_no_token_gets_401(self):
        self.assertEqual(self.client.get("/api/documents").status_code, 401)
