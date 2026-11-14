"""Background jobs. Huey finds this file by its name.

Calling process_document(id) puts it on the Redis queue, the worker runs it.
"""

from huey.contrib.djhuey import db_task

from documents import processing


@db_task()
def process_document(document_id):
    processing.process_document(document_id)
