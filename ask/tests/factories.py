from django.conf import settings

from ask.models import Chunk
from documents.models import Document
from documents.tests.factories import make_document


def vector(index=0):
    """A unit vector, so two different indexes have cosine similarity 0."""
    values = [0.0] * settings.ASK_EMBEDDING_DIMENSIONS
    values[index] = 1.0
    return values


def make_ready_document(workspace, title="Handbook", **fields):
    fields.setdefault("status", Document.Status.READY)
    return make_document(workspace, title=title, **fields)


def make_chunk(document, text="Document text.", chunk_index=0, embedding=None, **fields):
    return Chunk.objects.create(
        document=document,
        chunk_index=chunk_index,
        text=text,
        embedding=embedding if embedding is not None else vector(),
        **fields,
    )
