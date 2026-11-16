from django.conf import settings
from django.db import models
from pgvector.django import HnswIndex, VectorField

from core.llm import EMBEDDING_DIMENSIONS
from users.models import Workspace


class Document(models.Model):

    class FileType(models.TextChoices):
        PDF = "pdf", "PDF"
        DOCX = "docx", "Word (DOCX)"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=255)
    # Only storage.py uses this
    file_path = models.CharField(max_length=500)
    file_type = models.CharField(max_length=10, choices=FileType)
    # In bytes
    size = models.PositiveBigIntegerField()
    status = models.CharField(max_length=20, choices=Status, default=Status.QUEUED)
    error_message = models.TextField(blank=True)
    # Keep the document if the uploader is deleted
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="documents",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.title


class Chunk(models.Model):
    """A piece of a document's text, about 500 words, with its embedding."""

    # Deleting a document deletes its chunks too
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    # Copied from the document so search can filter without a join
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="chunks")
    text = models.TextField()
    # PDF page, or DOCX section number
    page = models.PositiveIntegerField()
    # DOCX heading, empty for PDFs
    section = models.CharField(max_length=255, blank=True)
    # Position in the document, from 0
    order = models.PositiveIntegerField()
    # Filled by the job
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True)

    class Meta:
        ordering = ["document", "order"]
        constraints = [
            models.UniqueConstraint(fields=["document", "order"], name="unique_chunk_order"),
        ]
        indexes = [
            # Makes "closest chunks" searches fast
            HnswIndex(
                name="chunk_embedding_index",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self):
        return f"{self.document} p.{self.page} #{self.order}"
