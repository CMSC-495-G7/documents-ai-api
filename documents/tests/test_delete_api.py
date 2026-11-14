from unittest.mock import patch

from django.test import TestCase

from documents.models import Chunk, Document
from documents.tests.factories import (
    TempStorageMixin,
    make_chunk,
    make_document,
    make_saved_document,
    pdf_upload,
    pdf_with,
)
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

    @patch("documents.api.delete_file", side_effect=PermissionError("read-only volume"))
    def test_file_that_cannot_be_deleted_still_returns_204(self, delete_file):
        document = make_document(self.admin.workspace)

        with self.assertLogs(level="ERROR"), self.captureOnCommitCallbacks(execute=True):
            response = self.delete_as(document.pk)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Document.objects.filter(pk=document.pk).exists())
        delete_file.assert_called_once_with(document.file_path)

    def test_leaves_no_chunks_or_file_behind(self):
        document = make_saved_document(self.admin.workspace, pdf_with("Dental"))
        make_chunk(document, order=0, embedding=[0.1] * 1536)
        make_chunk(document, order=1, embedding=[0.2] * 1536)
        # Another document's chunks and file stay
        other = make_saved_document(self.admin.workspace, pdf_with("Leave"), title="Other")
        other_chunk = make_chunk(other)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.delete_as(document.pk)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(list(Chunk.objects.all()), [other_chunk])
        self.assertEqual(self.stored_files(), [other.file_path])
