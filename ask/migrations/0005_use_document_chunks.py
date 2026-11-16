import django.db.models.deletion
from django.db import migrations, models


def forget_old_chunks(apps, schema_editor):
    """Old citations point at ask_chunk rows, which are going away. Their text is already copied."""
    Citation = apps.get_model("ask", "Citation")
    Citation.objects.update(chunk=None)


class Migration(migrations.Migration):
    dependencies = [
        ("ask", "0004_citation_copy_source"),
        ("documents", "0002_chunk"),
    ]

    operations = [
        migrations.RunPython(forget_old_chunks, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="citation",
            name="chunk",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="citations",
                to="documents.chunk",
            ),
        ),
        migrations.RemoveField(model_name="citation", name="slide"),
        migrations.RemoveField(model_name="citation", name="row_start"),
        migrations.RemoveField(model_name="citation", name="row_end"),
        migrations.AddField(
            model_name="citation",
            name="section",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.DeleteModel(name="Chunk"),
    ]
