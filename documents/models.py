from django.conf import settings
from django.db import models

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
