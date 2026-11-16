import django.db.models.deletion
from django.db import migrations, models


def copy_from_chunks(apps, schema_editor):
    """Fill the new fields for citations saved before this migration."""
    Citation = apps.get_model("ask", "Citation")
    for citation in Citation.objects.select_related("chunk__document"):
        chunk = citation.chunk
        citation.document = chunk.document
        citation.document_title = chunk.document.title
        citation.page = chunk.page
        citation.slide = chunk.slide
        citation.row_start = chunk.row_start
        citation.row_end = chunk.row_end
        citation.text = chunk.text
        citation.save()


class Migration(migrations.Migration):
    dependencies = [
        ("ask", "0003_alter_chunk_document"),
        ("documents", "0002_chunk"),
    ]

    operations = [
        migrations.AddField(
            model_name="citation",
            name="document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ask_citations",
                to="documents.document",
            ),
        ),
        migrations.AddField(
            model_name="citation",
            name="document_title",
            field=models.CharField(default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="citation",
            name="page",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="citation",
            name="slide",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="citation",
            name="row_start",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="citation",
            name="row_end",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="citation",
            name="text",
            field=models.TextField(default=""),
            preserve_default=False,
        ),
        migrations.RunPython(copy_from_chunks, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="citation",
            name="chunk",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="citations",
                to="ask.chunk",
            ),
        ),
    ]
