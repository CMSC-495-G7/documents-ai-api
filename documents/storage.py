"""
Files go in MEDIA_ROOT (the uploads volume in Docker). To move to S3 later.
"""

from pathlib import PurePosixPath
from uuid import uuid4

from django.core.files.storage import default_storage

FOLDER = "documents"


def save_file(file, extension):
    """Saves the upload and returns its path, like documents/3f2a...9c.pdf."""
    # Random name
    name = str(PurePosixPath(FOLDER) / f"{uuid4().hex}.{extension}")
    return default_storage.save(name, file)


def open_file(path):
    """Opens a saved file for reading. Use it in a with block."""
    return default_storage.open(path, "rb")


def delete_file(path):
    """Deletes a saved file, if it exists."""
    default_storage.delete(path)
