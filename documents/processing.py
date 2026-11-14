"""The process_document job: file -> pages -> chunks -> embeddings -> ready.

tasks.py queues it. Tests call process_document() straight.
"""

import logging
import time
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core import llm
from documents.chunking import split_into_chunks
from documents.extraction import ExtractionError, extract_pages
from documents.models import Chunk, Document
from documents.storage import open_file

logger = logging.getLogger(__name__)

SOMETHING_WENT_WRONG = "Something went wrong while processing this file. Try uploading it again."
PROCESSING_LEASE = timedelta(minutes=30)


def expired_processing(now):
    return Q(status=Document.Status.PROCESSING, updated_at__lte=now - PROCESSING_LEASE)


def process_document(document_id):
    document = Document.objects.filter(
        Q(status=Document.Status.QUEUED) | expired_processing(timezone.now()),
        pk=document_id,
    ).first()
    if document is None:
        return

    started = time.monotonic()
    if not set_status(document, Document.Status.PROCESSING):
        return
    try:
        with open_file(document.file_path) as file:
            pages = extract_pages(file, document.file_type)
        chunks = split_into_chunks(pages)
        vectors = llm.embed([chunk.text for chunk in chunks])
        if not save_chunks(document, chunks, vectors):
            return
    except Exception as error:
        set_status(document, Document.Status.FAILED, failure_message(error))
        return

    seconds = time.monotonic() - started
    logger.info("Document %s: %s chunks in %.1f s", document.pk, len(chunks), seconds)


def set_status(document, status, error_message=""):
    """Compare and update the status using the timestamp of the current claim."""
    old_status = document.status
    updated_at = timezone.now()
    updated = Document.objects.filter(
        pk=document.pk, status=old_status, updated_at=document.updated_at,
    ).update(
        status=status,
        error_message=error_message,
        updated_at=updated_at,
    )
    if not updated:
        return False
    document.status = status
    document.error_message = error_message
    document.updated_at = updated_at
    logger.info("Document %s: %s -> %s", document.pk, old_status, status)
    return True


def failure_message(error):
    """What admins see when a document fails."""
    if isinstance(error, (ExtractionError, llm.LLMError)):
        return str(error)
    logger.exception("Processing failed", exc_info=error)
    return SOMETHING_WENT_WRONG


def save_chunks(document, chunks, vectors):
    """Publish the chunks and ready status together while the worker owns the claim."""
    for chunk, vector in zip(chunks, vectors, strict=True):
        chunk.document = document
        chunk.workspace_id = document.workspace_id
        chunk.embedding = vector
    with transaction.atomic():
        if not Document.objects.select_for_update().filter(
            pk=document.pk, status=Document.Status.PROCESSING, updated_at=document.updated_at,
        ).first():
            return False
        Chunk.objects.filter(document=document).delete()
        Chunk.objects.bulk_create(chunks)
        return set_status(document, Document.Status.READY)
