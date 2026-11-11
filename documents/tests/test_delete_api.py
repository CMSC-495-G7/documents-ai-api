
from django.test import TestCase

from documents.models import Document
from documents.tests.factories import TempStorageMixin, make_document, pdf_upload
from users.tests.factories import auth_header, make_admin, make_user, make_workspace
from users.tokens import create_access_token


class DeleteDocumentTests(TempStorageMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_admin()

    def delete_as(self, document_id, user=None):
        token = create_access_token(user or self.admin)
        return self.client.delete(
            f"/api/documents/{document_id}",
            headers=auth_header(token),
        )

    def test_admin_deletes_database_record_and_stored_file(self):
        upload_response = self.client.post(
            "/api/documents",
            {"file": pdf_upload()},
            headers=auth_header(create_access_token(self.admin)),
        )
        self.assertEqual(upload_response.status_code, 201)
        document = Document.objects.get(pk=upload_response.json()["id"])
        self.assertEqual(self.stored_files(), [document.file_path])

        # TestCase wraps tests in a transaction. Execute commit callbacks explicitly.
        with self.captureOnCommitCallbacks(execute=True):
            response = self.delete_as(document.pk)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Document.objects.filter(pk=document.pk).exists())
        self.assertEqual(self.stored_files(), [])

    def test_employee_cannot_delete(self):
        document = make_document(self.admin.workspace)
        employee = make_user()
        response = self.delete_as(document.pk, user=employee)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())

    def test_cannot_delete_document_from_another_workspace(self):
        other_workspace = make_workspace(slug="sales", name="Sales")
        document = make_document(other_workspace)
        response = self.delete_as(document.pk)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())

    def test_missing_document_returns_404(self):
        response = self.delete_as(999999)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Document not found."})

    def test_unauthenticated_request_returns_401(self):
        document = make_document(self.admin.workspace)
        response = self.client.delete(f"/api/documents/{document.pk}")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())
