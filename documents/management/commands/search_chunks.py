"""Prints the 5 chunks closest to a question, with their page numbers.

For checking the embeddings by hand. Stage 4 does the real search.
"""

from django.core.management.base import BaseCommand
from pgvector.django import CosineDistance

from core import llm
from documents.models import Chunk


class Command(BaseCommand):
    help = "Show the 5 chunks closest to a question."

    def add_arguments(self, parser):
        parser.add_argument("question")
        parser.add_argument("--workspace", default="engineering", help="Workspace slug")

    def handle(self, *args, question, workspace, **options):
        vector = llm.embed([question])[0]
        chunks = (
            Chunk.objects.filter(workspace__slug=workspace, embedding__isnull=False)
            .select_related("document")
            .annotate(distance=CosineDistance("embedding", vector))
            .order_by("distance")[:5]
        )
        for chunk in chunks:
            # 1 = same meaning, 0 = unrelated
            score = 1 - chunk.distance
            preview = chunk.text[:80].replace("\n", " ")
            self.stdout.write(f"{score:.3f}  {chunk.document.title}, page {chunk.page}: {preview}")
        if not chunks:
            self.stdout.write("No chunks yet. Upload a document and wait for it to be ready.")
