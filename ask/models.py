from django.conf import settings
from django.db import models
from pgvector.django import VectorField

from documents.models import Document
from users.models import User, Workspace


class Chunk(models.Model):
    """A piece of a document, with its location and embedding, that answers can cite."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.PositiveIntegerField()
    text = models.TextField()
    page = models.PositiveIntegerField(null=True, blank=True)
    slide = models.PositiveIntegerField(null=True, blank=True)
    row_start = models.PositiveIntegerField(null=True, blank=True)
    row_end = models.PositiveIntegerField(null=True, blank=True)
    embedding = VectorField(dimensions=settings.ASK_EMBEDDING_DIMENSIONS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document_id", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "chunk_index"],
                name="unique_chunk_index_per_document",
            )
        ]

    def __str__(self):
        return f"{self.document.title} chunk {self.chunk_index}"


class Answer(models.Model):
    """A saved question and the answer the API returned for it."""

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="answers")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="answers",
    )
    question = models.TextField()
    answer = models.TextField()
    model_name = models.CharField(max_length=100, blank=True)
    used_llm = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.question[:80]


class Citation(models.Model):
    """A chunk the answer used, kept so the citation can be checked later."""

    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, related_name="citations")
    chunk = models.ForeignKey(Chunk, on_delete=models.CASCADE, related_name="citations")
    rank = models.PositiveIntegerField()
    score = models.FloatField()

    class Meta:
        ordering = ["rank"]
        constraints = [
            models.UniqueConstraint(
                fields=["answer", "rank"],
                name="unique_citation_rank_per_answer",
            )
        ]

    def __str__(self):
        return f"Citation {self.rank} for answer {self.answer_id}"
