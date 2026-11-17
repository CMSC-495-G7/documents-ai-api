
from django.test import TestCase

from documents.models import Document
from documents.tests.factories import (
    TempStorageMixin,
    docx_with,
    make_document,
    make_saved_document,
    pdf_with,
)
from users.tests.factories import (
    auth_header,
    make_admin,
    make_user,
    make_workspace,
)
from users.tokens import create_access_token


class DocumentFileTests(TempStorageMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_admin()

    def get_file(self, document_id, user=None):
        token = create_access_token(user or self.admin)
        return self.client.get(
            f"/api/documents/{document_id}/file",
            headers=auth_header(token),
        )

    def test_employee_can_open_pdf(self):
        content = pdf_with("Hello")
        document = make_saved_document(self.admin.workspace, content)
        employee = make_user(workspace=self.admin.workspace)

        response = self.get_file(document.pk, employee)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(b"".join(response.streaming_content), content)


    def test_admin_can_open_pdf(self):
        document = make_saved_document(
            self.admin.workspace, pdf_with("Hello")
        )

        response = self.get_file(document.pk)

        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)

    def test_docx_content_type(self):
        content = docx_with(("paragraph", "Hello"))
        document = make_saved_document(
            self.admin.workspace,
            content,
            file_type=Document.FileType.DOCX,
        )

        response = self.get_file(document.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual(b"".join(response.streaming_content), content)


    def test_other_workspace_returns_404(self):
        other_workspace = make_workspace(
            slug="sales", name="Sales"
        )
        document = make_saved_document(
            other_workspace, pdf_with("Hello")
        )

        response = self.get_file(document.pk)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(), {"detail": "Document not found."}
        )

    def test_missing_document_returns_404(self):
        response = self.get_file(999999)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(), {"detail": "Document not found."}
        )

    def test_missing_stored_file_returns_404(self):
        document = make_document(
            self.admin.workspace,
            file_path="documents/missing.pdf",
        )

        response = self.get_file(document.pk)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(), {"detail": "Document not found."}
        )

    def test_unauthenticated_request_returns_401(self):
        document = make_saved_document(
            self.admin.workspace, pdf_with("Hello")
        )

        response = self.client.get(
            f"/api/documents/{document.pk}/file"
        )

        self.assertEqual(response.status_code, 401)
