"""Background jobs. Huey finds this file by its name.

Calling process_document(id) puts it on the Redis queue, the worker runs it.
"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task

from documents import processing
from documents.models import Document

QUEUE_RECOVERY_DELAY = timedelta(minutes=1)
RECOVERY_BATCH_SIZE = 100


@db_task()
def process_document(document_id):
    processing.process_document(document_id)


@db_periodic_task(crontab(minute="*"))
def recover_documents():
    """Reschedule uploads lost before or after the worker took the task."""
    now = timezone.now()
    document_ids = Document.objects.filter(
        Q(status=Document.Status.QUEUED, updated_at__lte=now - QUEUE_RECOVERY_DELAY)
        | processing.expired_processing(now)
    ).order_by("updated_at", "pk").values_list("pk", flat=True)[:RECOVERY_BATCH_SIZE]
    for document_id in document_ids:
        process_document(document_id)
