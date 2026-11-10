"""Works out the real file type from the bytes, not the name."""

import zipfile

PDF = "pdf"
DOCX = "docx"

PDF_START = b"%PDF-"


def detect_file_type(file):
    """Returns "pdf", "docx", or None if it's neither."""
    start = file.read(len(PDF_START))
    file.seek(0)
    if start == PDF_START:
        return PDF

    try:
        with zipfile.ZipFile(file) as document:  # file can be a file object
            names = document.namelist()
    except zipfile.BadZipFile:
        return None
    finally:
        file.seek(0)

    if "word/document.xml" in names:
        return DOCX
    return None
