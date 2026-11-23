from django.db import migrations
from django.utils import timezone


def requeue_documents_without_chunks(apps, schema_editor):
    """A ready document with no chunks can't be searched, so queue it to be processed again."""

    Document = apps.get_model("documents", "Document")
    Document.objects.filter(status="ready", chunks__isnull=True).update(
        status="queued",
        error_message="",
        updated_at=timezone.now(),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0002_chunk"),
        ("ask", "0005_use_document_chunks"),
    ]

    operations = [
        migrations.RunPython(requeue_documents_without_chunks, migrations.RunPython.noop),
    ]
