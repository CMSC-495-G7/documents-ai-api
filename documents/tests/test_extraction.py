import io
from unittest.mock import patch

from django.test import SimpleTestCase
from pypdf import PdfWriter

from documents.extraction import (
    BROKEN_DOCX,
    BROKEN_PDF,
    LOCKED_PDF,
    NO_TEXT,
    OVERSIZED_DOCX,
    ExtractionError,
    extract_pages,
)
from documents.tests.factories import PDF_BYTES, docx_bytes, docx_with, pdf_with


def extract(content, file_type):
    return extract_pages(io.BytesIO(content), file_type)


class PdfPageTests(SimpleTestCase):
    def test_one_page_per_pdf_page_numbered_from_1(self):
        pages = extract(pdf_with("Welcome to the team", "Vacation policy"), "pdf")

        self.assertEqual([page.number for page in pages], [1, 2])
        self.assertIn("Welcome to the team", pages[0].text)
        self.assertIn("Vacation policy", pages[1].text)

    def test_blank_pages_are_skipped_but_keep_the_real_numbers(self):
        pages = extract(pdf_with("Cover", "", "Page three"), "pdf")

        self.assertEqual([page.number for page in pages], [1, 3])
        self.assertIn("Page three", pages[1].text)

    def test_keeps_every_line(self):
        pages = extract(pdf_with("first line\nsecond line"), "pdf")
        self.assertIn("first line", pages[0].text)
        self.assertIn("second line", pages[0].text)

    def test_pdfs_have_no_section(self):
        self.assertEqual(extract(pdf_with("Hello"), "pdf")[0].section, "")


class PdfProblemTests(SimpleTestCase):
    def assert_fails_with(self, content, message):
        with self.assertRaisesMessage(ExtractionError, message):
            extract(content, "pdf")

    def test_pdf_with_no_text(self):
        self.assert_fails_with(pdf_with("", ""), NO_TEXT)

    def test_damaged_pdf(self):
        self.assert_fails_with(PDF_BYTES, BROKEN_PDF)

    def test_cut_off_pdf(self):
        self.assert_fails_with(pdf_with("Hello")[:40], BROKEN_PDF)

    def test_password_protected_pdf(self):
        writer = PdfWriter(clone_from=io.BytesIO(pdf_with("Secret")))
        writer.encrypt("hunter2", algorithm="RC4-128")
        locked = io.BytesIO()
        writer.write(locked)

        self.assert_fails_with(locked.getvalue(), LOCKED_PDF)


class DocxSectionTests(SimpleTestCase):
    def test_each_heading_starts_a_new_section(self):
        pages = extract(
            docx_with(
                ("heading", "Benefits"),
                ("paragraph", "Dental is covered."),
                ("heading", "Leave"),
                ("paragraph", "You get 20 days."),
            ),
            "docx",
        )

        self.assertEqual([page.number for page in pages], [1, 2])
        self.assertEqual([page.section for page in pages], ["Benefits", "Leave"])
        self.assertIn("Dental is covered.", pages[0].text)
        self.assertIn("You get 20 days.", pages[1].text)

    def test_text_before_the_first_heading_is_section_1(self):
        pages = extract(
            docx_with(("paragraph", "Read this first."), ("heading", "Benefits"), ("paragraph", "Dental.")),
            "docx",
        )
        self.assertEqual([(page.number, page.section) for page in pages], [(1, ""), (2, "Benefits")])

    def test_heading_text_is_part_of_the_section(self):
        pages = extract(docx_with(("heading", "Benefits"), ("paragraph", "Dental.")), "docx")
        self.assertIn("Benefits", pages[0].text)

    def test_tables_are_included(self):
        pages = extract(docx_with(("table", [["Plan", "Cost"], ["Basic", "$10"]])), "docx")
        self.assertIn("Basic | $10", pages[0].text)

    def test_empty_docx(self):
        with self.assertRaisesMessage(ExtractionError, NO_TEXT):
            extract(docx_with(("paragraph", "   ")), "docx")

    def test_damaged_docx(self):
        with self.assertRaisesMessage(ExtractionError, BROKEN_DOCX):
            extract(docx_bytes(), "docx")

    def test_docx_archive_limits_are_checked_before_parsing(self):
        content = docx_with(("paragraph", "Dental"))
        for limit in ("MAX_DOCX_ENTRIES", "MAX_DOCX_UNCOMPRESSED_BYTES"):
            with self.subTest(limit=limit), patch(f"documents.extraction.{limit}", 1):
                with patch("documents.extraction.docx.Document") as parse:
                    with self.assertRaisesMessage(ExtractionError, OVERSIZED_DOCX):
                        extract(content, "docx")
                parse.assert_not_called()


class OtherTypeTests(SimpleTestCase):
    def test_unknown_type(self):
        with self.assertRaises(ExtractionError):
            extract(b"hello", "txt")
