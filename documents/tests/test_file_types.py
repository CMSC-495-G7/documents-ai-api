import io

from django.test import SimpleTestCase

from documents.file_types import detect_file_type
from documents.tests.factories import docx_bytes, pdf_bytes, zip_bytes


def detect(data):
    return detect_file_type(io.BytesIO(data))


class DetectFileTypeTests(SimpleTestCase):
    def test_pdf(self):
        self.assertEqual(detect(pdf_bytes()), "pdf")

    def test_docx(self):
        self.assertEqual(detect(docx_bytes()), "docx")

    def test_plain_text(self):
        self.assertIsNone(detect(b"just some text"))

    def test_empty_file(self):
        self.assertIsNone(detect(b""))

    def test_zip_that_is_not_a_word_file(self):
        # Excel files are zips too.
        self.assertIsNone(detect(zip_bytes({"xl/workbook.xml": "<workbook/>"})))

    def test_broken_zip(self):
        self.assertIsNone(detect(b"PK\x03\x04 not really a zip"))

    def test_pdf_text_later_in_the_file_does_not_count(self):
        self.assertIsNone(detect(b"hello %PDF-1.4"))

    def test_rewinds_the_file_so_it_can_be_saved_after(self):
        for data in (pdf_bytes(), docx_bytes(), b"just some text"):
            with self.subTest(data=data[:8]):
                file = io.BytesIO(data)
                detect_file_type(file)
                self.assertEqual(file.tell(), 0)
