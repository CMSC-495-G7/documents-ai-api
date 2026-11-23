from unittest.mock import patch

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from ask.models import Citation
from ask.services import search
from ask.tests.factories import make_chunk, make_ready_document, vector
from documents.models import Document
from users.tests.factories import auth_header, make_user
from users.tokens import create_access_token

# Before ask.0005 (drops the old ask_chunk table) and documents.0003 (queues
# ready documents that have no chunks)
BEFORE = [("ask", "0004_citation_copy_source"), ("documents", "0002_chunk")]


def migrate(targets):
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


def migrate_to_latest():
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


class LegacyChunkMigrationTests(TransactionTestCase):
    """Upgrading a database that still has the old ask_chunk rows."""

    def setUp(self):
        old_apps = migrate(BEFORE)
        # users and documents keep their current tables, only ask goes back
        self.user = make_user()
        workspace = self.user.workspace

        # Indexed the current way: its chunks are in documents_chunk
        self.indexed = make_ready_document(workspace, title="Leave Policy")
        make_chunk(self.indexed, text="Employees get 20 vacation days.", page=3)
        # Only indexed in the old table, which is about to be dropped
        self.legacy_only = make_ready_document(workspace, title="Old Handbook")

        OldChunk = old_apps.get_model("ask", "Chunk")
        OldAnswer = old_apps.get_model("ask", "Answer")
        OldCitation = old_apps.get_model("ask", "Citation")
        old_chunk = OldChunk.objects.create(
            document_id=self.legacy_only.pk,
            chunk_index=0,
            text="Parking is in the north garage.",
            page=7,
            embedding=[0.0] * 3072,
        )
        answer = OldAnswer.objects.create(
            workspace_id=workspace.pk,
            user_id=self.user.pk,
            question="Where do I park?",
            answer="In the north garage [1].",
            model_name="gpt-5-mini",
        )
        OldCitation.objects.create(
            answer=answer,
            chunk=old_chunk,
            document_id=self.legacy_only.pk,
            document_title="Old Handbook",
            page=7,
            text="Parking is in the north garage.",
            rank=1,
            score=0.8,
        )
        self.answer_id = answer.pk

        migrate_to_latest()

    def test_documents_with_chunks_stay_searchable(self):
        self.indexed.refresh_from_db()
        self.assertEqual(self.indexed.status, Document.Status.READY)

        with patch("core.llm.embed", return_value=[vector(0)]):
            matches = search("How many vacation days?", self.user)

        self.assertEqual([chunk.document_id for chunk, _ in matches], [self.indexed.pk])

    def test_documents_only_in_the_old_table_are_queued_again(self):
        self.legacy_only.refresh_from_db()
        self.assertEqual(self.legacy_only.status, Document.Status.QUEUED)

    def test_old_citations_keep_their_copied_source(self):
        citation = Citation.objects.get(answer_id=self.answer_id)

        self.assertIsNone(citation.chunk_id)
        self.assertEqual(citation.document_title, "Old Handbook")
        self.assertEqual(citation.page, 7)
        self.assertEqual(citation.text, "Parking is in the north garage.")

    def test_old_answers_still_open_from_history(self):
        token = create_access_token(self.user)
        response = self.client.get(f"/api/ask/{self.answer_id}", headers=auth_header(token))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["citations"][0]["text"], "Parking is in the north garage.")
