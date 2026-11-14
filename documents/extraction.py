"""Pulls the text out of a saved file, one Page at a time."""

from dataclasses import dataclass

import docx
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from documents.file_types import DOCX, PDF

NO_TEXT = "No text found in this file. Scanned PDFs (pictures of text) aren't supported yet."
BROKEN_PDF = "This PDF couldn't be read. It may be damaged."
LOCKED_PDF = "This PDF is password protected. Remove the password and upload it again."
BROKEN_DOCX = "This DOCX couldn't be read. It may be damaged."


class ExtractionError(Exception):
    """The file can't be used. The message is shown to admins."""


@dataclass
class Page:
    number: int
    text: str
    # Heading the text is under (DOCX only)
    section: str = ""


def extract_pages(file, file_type):
    """Returns a list of Pages with text. Raises ExtractionError if there's none."""
    if file_type == PDF:
        pages = extract_pdf(file)
    elif file_type == DOCX:
        pages = extract_docx(file)
    else:
        raise ExtractionError("Only PDF and DOCX files can be processed.")

    if not pages:
        raise ExtractionError(NO_TEXT)
    return pages


def extract_pdf(file):
    """One Page per PDF page, numbered from 1. Pages with no text are skipped."""
    try:
        reader = PdfReader(file)
    except PyPdfError as error:
        raise ExtractionError(BROKEN_PDF) from error
    if reader.is_encrypted:
        raise ExtractionError(LOCKED_PDF)

    pages = []
    for number, pdf_page in enumerate(reader.pages, start=1):
        text = pdf_page.extract_text()
        # Skip pages where extract_text() is only spaces
        if text.strip():
            pages.append(Page(number=number, text=text))
    return pages


def extract_docx(file):
    """DOCX has no real pages, so each heading starts a new section, numbered from 1."""
    try:
        document = docx.Document(file)
    except Exception as error:
        # python-docx raises a few different errors for broken files
        raise ExtractionError(BROKEN_DOCX) from error

    sections = []
    heading = ""
    lines = []
    # Paragraphs and tables, in the order they appear
    for block in document.iter_inner_content():
        if is_heading(block):
            sections.append((heading, lines))
            heading = block.text.strip()[:255]
            lines = []
        text = block_text(block)
        if text.strip():
            lines.append(text)
    sections.append((heading, lines))

    pages = []
    for heading, lines in sections:
        if lines:
            pages.append(Page(number=len(pages) + 1, text="\n".join(lines), section=heading))
    return pages


def is_heading(block):
    if not isinstance(block, Paragraph) or block.style is None:
        return False
    name = block.style.name or ""
    return name.startswith("Heading") or name == "Title"


def block_text(block):
    if isinstance(block, Paragraph):
        return block.text
    # A table: one line per row
    rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in block.rows]
    return "\n".join(rows)
