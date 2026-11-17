from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="workspace",
            name="answer_provider",
            field=models.CharField(
                choices=[("openai", "OpenAI"), ("gemini", "Gemini")],
                default="openai",
                max_length=20,
            ),
        ),
    ]
