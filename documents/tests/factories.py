import io
import tempfile
import zipfile
from pathlib import Path

import docx
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from documents.models import Chunk, Document
from documents.storage import save_file

PDF_BYTES = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"


def pdf_bytes(size=None):
    if size is None:
        return PDF_BYTES
    return PDF_BYTES + b"0" * (size - len(PDF_BYTES))


def zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def docx_bytes():
    return zip_bytes(
        {
            "[Content_Types].xml": "<Types/>",
            "word/document.xml": "<w:document/>",
        }
    )


def pdf_with(*pages):
    """A real PDF with one page per string. Use \n for new lines, "" for a blank page."""
    font = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", font]
    kids = []
    for text in pages:
        text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        lines = " ".join(f"({line}) Tj T*" for line in text.split("\n"))
        stream = f"BT /F1 11 Tf 14 TL 72 760 Td {lines} ET".encode("latin-1")
        page_number = len(objects) + 1
        kids.append(f"{page_number} 0 R")
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (page_number + 1)
        )
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()

    # The xref table at the end lists where each object starts
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def docx_with(*blocks):
    """A real DOCX. Blocks are ("heading", text), ("paragraph", text) or ("table", rows)."""
    document = docx.Document()
    for kind, value in blocks:
        if kind == "heading":
            document.add_heading(value, level=1)
        elif kind == "table":
            table = document.add_table(rows=len(value), cols=len(value[0]))
            for row, cells in zip(table.rows, value):
                for cell, text in zip(row.cells, cells):
                    cell.text = text
        else:
            document.add_paragraph(value)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def words(count, word="word"):
    """ "word0 word1 word2 ..." """
    return " ".join(f"{word}{n}" for n in range(count))


def pdf_upload(name="Handbook.pdf", size=None):
    return SimpleUploadedFile(name, pdf_bytes(size), content_type="application/pdf")


def docx_upload(name="Handbook.docx"):
    return SimpleUploadedFile(name, docx_bytes(), content_type="application/octet-stream")


def text_upload(name="notes.txt"):
    return SimpleUploadedFile(name, b"just some text", content_type="text/plain")


def make_document(workspace, title="Handbook", uploaded_by=None, **fields):
    fields.setdefault("file_path", f"documents/{title}.pdf")
    fields.setdefault("file_type", Document.FileType.PDF)
    fields.setdefault("size", 1024)
    return Document.objects.create(workspace=workspace, title=title, uploaded_by=uploaded_by, **fields)


def make_saved_document(workspace, content, file_type=Document.FileType.PDF, **fields):
    """A queued document with its file really saved. Use with TempStorageMixin."""
    path = save_file(ContentFile(content), file_type)
    return make_document(workspace, file_path=path, file_type=file_type, size=len(content), **fields)


def make_chunk(document, text="Some text", page=1, order=0, embedding=None, **fields):
    return Chunk.objects.create(
        document=document,
        workspace=document.workspace,
        text=text,
        page=page,
        order=order,
        embedding=embedding,
        **fields,
    )


class TempStorageMixin:
    """Saves files in a temp folder"""

    def setUp(self):
        super().setUp()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.storage_root = Path(folder.name)

        temp_settings = override_settings(MEDIA_ROOT=folder.name)
        temp_settings.enable()
        self.addCleanup(temp_settings.disable)

    def stored_files(self):
        files = self.storage_root.rglob("*")
        return sorted(f.relative_to(self.storage_root).as_posix() for f in files if f.is_file())
