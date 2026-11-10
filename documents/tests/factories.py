import io
import tempfile
import zipfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from documents.models import Document

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
