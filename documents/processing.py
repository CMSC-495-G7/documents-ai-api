"""The process_document job: file -> pages -> chunks -> embeddings -> ready.

tasks.py queues it. Tests call process_document() straight.
"""

import logging
import time

from django.db import transaction
from django.utils import timezone

from core import llm
from documents.chunking import split_into_chunks
from documents.extraction import ExtractionError, extract_pages
from documents.models import Chunk, Document
from documents.storage import open_file

logger = logging.getLogger(__name__)

SOMETHING_WENT_WRONG = "Something went wrong while processing this file. Try uploading it again."


def process_document(document_id):
    document = Document.objects.filter(pk=document_id).first()
    if document is None:
        logger.info("Document %s was deleted before it was processed", document_id)
        return

    started = time.monotonic()
    set_status(document, Document.Status.PROCESSING)
    try:
        with open_file(document.file_path) as file:
            pages = extract_pages(file, document.file_type)
        chunks = split_into_chunks(pages)
        vectors = llm.embed([chunk.text for chunk in chunks])
        save_chunks(document, chunks, vectors)
    except Exception as error:
        set_status(document, Document.Status.FAILED, failure_message(error))
        return

    set_status(document, Document.Status.READY)
    seconds = time.monotonic() - started
    logger.info("Document %s: %s chunks in %.1f s", document.pk, len(chunks), seconds)


def set_status(document, status, error_message=""):
    """Saves the new status and logs the change.

    Uses update() so a document deleted mid-job is skipped.
    """
    old_status = document.status
    document.status = status
    document.error_message = error_message
    Document.objects.filter(pk=document.pk).update(
        status=status,
        error_message=error_message,
        updated_at=timezone.now(),
    )
    logger.info("Document %s: %s -> %s", document.pk, old_status, status)


def failure_message(error):
    """What admins see when a document fails."""
    if isinstance(error, (ExtractionError, llm.LLMError)):
        return str(error)
    logger.exception("Processing failed", exc_info=error)
    return SOMETHING_WENT_WRONG


def save_chunks(document, chunks, vectors):
    """Replaces the document's chunks, all or nothing."""
    for chunk, vector in zip(chunks, vectors, strict=True):
        chunk.document = document
        chunk.workspace_id = document.workspace_id
        chunk.embedding = vector
    with transaction.atomic():
        # Lock the row so a delete waits until we're done. Deleted already? Skip.
        if Document.objects.select_for_update().filter(pk=document.pk).first() is None:
            return
        Chunk.objects.filter(document=document).delete()
        Chunk.objects.bulk_create(chunks)
