from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("ask", "0002_alter_chunk_embedding"),
    ]

    operations = [
        migrations.AlterField(
            model_name="chunk",
            name="document",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ask_chunks",
                to="documents.document",
            ),
        ),
    ]
