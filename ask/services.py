from django.conf import settings
from django.db import transaction
from pgvector import Vector
from pgvector.django import CosineDistance

from ask.models import Answer, Chunk, Citation
from ask.providers import Source, embed_question, generate_answer
from documents.models import Document

NO_ANSWER = "I couldn't find this in the documents"


def _source_label(chunk):
    parts = [chunk.document.title]
    if chunk.page is not None:
        parts.append(f"page {chunk.page}")
    if chunk.slide is not None:
        parts.append(f"slide {chunk.slide}")
    if chunk.row_start is not None and chunk.row_end is not None:
        parts.append(f"rows {chunk.row_start}-{chunk.row_end}")
    elif chunk.row_start is not None:
        parts.append(f"row {chunk.row_start}")
    elif chunk.row_end is not None:
        parts.append(f"through row {chunk.row_end}")
    parts.append(f"chunk {chunk.id}")
    return ", ".join(parts)


def _searchable_chunks(user):
    return Chunk.objects.filter(
        document__workspace=user.workspace,
        document__status=Document.Status.READY,
    ).select_related("document")


def _retrieve(chunks, question):
    query_embedding = embed_question(question)
    candidates = (
        chunks.annotate(distance=CosineDistance("embedding", Vector(query_embedding)))
        .order_by("distance")[: settings.ASK_MAX_CONTEXT_CHUNKS]
    )

    cutoff = settings.ASK_SIMILARITY_CUTOFF
    matches = []
    for chunk in candidates:
        score = max(0.0, min(1.0, 1.0 - float(chunk.distance)))
        if score >= cutoff:
            matches.append((chunk, score))
    return matches


def _save(user, question, answer, model_name, used_llm, matches):
    with transaction.atomic():
        record = Answer.objects.create(
            workspace=user.workspace,
            user=user,
            question=question,
            answer=answer,
            model_name=model_name,
            used_llm=used_llm,
        )
        Citation.objects.bulk_create(
            [
                Citation(answer=record, chunk=chunk, rank=rank, score=score)
                for rank, (chunk, score) in enumerate(matches, start=1)
            ]
        )
    return record


def ask_question(user, question):
    chunks = _searchable_chunks(user)
    if not chunks.exists():
        return _save(user, question, NO_ANSWER, "", False, [])

    matches = _retrieve(chunks, question)
    if not matches:
        return _save(user, question, NO_ANSWER, "", False, [])

    sources = [Source(label=_source_label(chunk), text=chunk.text) for chunk, _ in matches]
    answer = generate_answer(question, sources)
    return _save(user, question, answer, settings.ASK_LLM_MODEL, True, matches)
