from django.conf import settings
from django.db import models

from documents.models import Chunk, Document
from users.models import Workspace


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
    """A chunk the answer used. Its source is copied so history still shows it later."""

    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, related_name="citations")
    # Empty once the chunk is replaced (reprocessing) or its document is deleted
    chunk = models.ForeignKey(
        Chunk, on_delete=models.SET_NULL, null=True, blank=True, related_name="citations"
    )
    # Empty once the document is deleted
    document = models.ForeignKey(
        Document, on_delete=models.SET_NULL, null=True, blank=True, related_name="ask_citations"
    )
    # Copied from the chunk when the answer is saved
    document_title = models.CharField(max_length=255)
    page = models.PositiveIntegerField(null=True, blank=True)
    section = models.CharField(max_length=255, blank=True)
    text = models.TextField()
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
