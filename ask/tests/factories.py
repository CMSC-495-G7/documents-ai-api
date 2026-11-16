from core.llm import EMBEDDING_DIMENSIONS
from documents.models import Document
from documents.tests.factories import make_chunk as make_document_chunk
from documents.tests.factories import make_document


def vector(index=0):
    """A unit vector, so two different indexes have cosine similarity 0."""
    values = [0.0] * EMBEDDING_DIMENSIONS
    values[index] = 1.0
    return values


def make_ready_document(workspace, title="Handbook", **fields):
    fields.setdefault("status", Document.Status.READY)
    return make_document(workspace, title=title, **fields)


def make_chunk(document, text="Document text.", order=0, embedding=None, **fields):
    """A chunk with an embedding, vector(0) unless told otherwise."""
    return make_document_chunk(
        document,
        text=text,
        order=order,
        embedding=embedding if embedding is not None else vector(),
        **fields,
    )
