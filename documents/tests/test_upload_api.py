from django.test import TestCase, override_settings

from documents.models import Document
from documents.tests.factories import TempStorageMixin, docx_upload, pdf_upload, text_upload
from users.tests.factories import auth_header, make_admin, make_user
from users.tokens import create_access_token


class UploadTestCase(TempStorageMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_admin()

    def upload(self, file, user=None):
        token = create_access_token(user or self.admin)
        return self.client.post("/api/documents", {"file": file}, headers=auth_header(token))

    def assert_nothing_saved(self):
        self.assertFalse(Document.objects.exists())
        self.assertEqual(self.stored_files(), [])


class GoodUploadTests(UploadTestCase):
    def test_pdf_upload_is_saved_and_queued(self):
        response = self.upload(pdf_upload("Employee Handbook.pdf"))

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["title"], "Employee Handbook")
        self.assertEqual(body["file_type"], "pdf")
        self.assertEqual(body["status"], "queued")
        self.assertEqual(body["uploaded_by"], "admin@acme.example")

        document = Document.objects.get(pk=body["id"])
        self.assertEqual(document.workspace, self.admin.workspace)
        self.assertEqual(document.uploaded_by, self.admin)
        self.assertEqual(self.stored_files(), [document.file_path])

    def test_docx_upload(self):
        response = self.upload(docx_upload())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["file_type"], "docx")

    def test_extension_case_does_not_matter(self):
        self.assertEqual(self.upload(pdf_upload("SCAN.PDF")).status_code, 201)

    def test_size_is_saved_in_bytes(self):
        response = self.upload(pdf_upload(size=5000))
        self.assertEqual(response.json()["size"], 5000)

    def test_file_path_is_not_sent_to_the_browser(self):
        response = self.upload(pdf_upload())
        self.assertNotIn("file_path", response.json())


@override_settings(DOCUMENT_MAX_UPLOAD_MB=1)
class SizeLimitTests(UploadTestCase):
    def test_too_big_file_gets_413(self):
        response = self.upload(pdf_upload(size=1024 * 1024 + 1))

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json(), {"detail": "The file is too big. The limit is 1 MB."})
        self.assert_nothing_saved()

    def test_file_right_at_the_limit_is_ok(self):
        self.assertEqual(self.upload(pdf_upload(size=1024 * 1024)).status_code, 201)


class WrongTypeTests(UploadTestCase):
    def assert_rejected(self, response):
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.json(), {"detail": "Only PDF and DOCX files can be uploaded."})
        self.assert_nothing_saved()

    def test_text_file(self):
        self.assert_rejected(self.upload(text_upload()))

    def test_text_file_renamed_to_pdf(self):
        self.assert_rejected(self.upload(text_upload("sneaky.pdf")))

    def test_pdf_renamed_to_docx(self):
        self.assert_rejected(self.upload(pdf_upload("handbook.docx")))

    def test_pdf_with_no_extension(self):
        self.assert_rejected(self.upload(pdf_upload("handbook")))


class UploadPermissionTests(UploadTestCase):
    def test_employee_gets_403(self):
        response = self.upload(pdf_upload(), user=make_user())

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "You don't have access to this."})
        self.assert_nothing_saved()

    def test_no_token_gets_401(self):
        response = self.client.post("/api/documents", {"file": pdf_upload()})
        self.assertEqual(response.status_code, 401)

    def test_missing_file_gets_422(self):
        token = create_access_token(self.admin)
        response = self.client.post("/api/documents", {}, headers=auth_header(token))
        self.assertEqual(response.status_code, 422)
