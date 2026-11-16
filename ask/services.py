"""Search the workspace's chunks and answer from them."""

from django.conf import settings
from django.db import transaction
from pgvector.django import CosineDistance

from ask.models import Answer, Citation
from core import llm
from documents.models import Chunk, Document
from users.permissions import workspace_queryset

NO_ANSWER = "I couldn't find this in the documents"

INSTRUCTIONS = (
    "You are a workplace assistant. Answer the question using only the numbered "
    "document excerpts provided. Cite every excerpt you use with its bracketed "
    "number, like [1]. If the excerpts do not contain the answer, say you couldn't "
    "find it in the documents. Do not use outside knowledge."
)


def searchable_chunks(user):
    """Chunks from the user's workspace that are ready to search."""
    return workspace_queryset(Chunk, user).filter(
        document__status=Document.Status.READY,
        embedding__isnull=False,
    )


def search(question, user):
    """The closest chunks to the question, best first, as (chunk, score) pairs."""
    vector = llm.embed([question])[0]
    chunks = (
        searchable_chunks(user)
        .select_related("document")
        .annotate(distance=CosineDistance("embedding", vector))
        .order_by("distance")[: settings.ASK_MAX_CONTEXT_CHUNKS]
    )
    return [(chunk, max(0.0, 1 - chunk.distance)) for chunk in chunks]


def ask_question(user, question):
    if not searchable_chunks(user).exists():
        return save_answer(user, question, NO_ANSWER, "", False, [])

    matches = [
        (chunk, score)
        for chunk, score in search(question, user)
        if score >= settings.ASK_SIMILARITY_CUTOFF
    ]
    if not matches:
        return save_answer(user, question, NO_ANSWER, "", False, [])

    provider = user.workspace.answer_provider
    answer = llm.ask(build_prompt(question, matches), INSTRUCTIONS, provider)
    return save_answer(user, question, answer, llm.answer_model(provider), True, matches)


def build_prompt(question, matches):
    lines = [f"Question: {question}", "", "Document excerpts:"]
    for number, (chunk, _) in enumerate(matches, start=1):
        lines.append(f"[{number}] {source_label(chunk)}\n{chunk.text}")
    return "\n\n".join(lines)


def source_label(chunk):
    if chunk.section:
        return f"{chunk.document.title}, {chunk.section}"
    return f"{chunk.document.title}, page {chunk.page}"


def save_answer(user, question, answer, model_name, used_llm, matches):
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
                Citation(
                    answer=record,
                    chunk=chunk,
                    document=chunk.document,
                    document_title=chunk.document.title,
                    page=chunk.page,
                    section=chunk.section,
                    text=chunk.text,
                    rank=rank,
                    score=score,
                )
                for rank, (chunk, score) in enumerate(matches, start=1)
            ]
        )
    return record
