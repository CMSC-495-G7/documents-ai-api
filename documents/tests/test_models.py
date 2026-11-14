from django.db import IntegrityError
from django.test import TestCase

from documents.models import Chunk, Document
from documents.tests.factories import make_chunk, make_document
from users.tests.factories import make_admin, make_workspace


class DocumentModelTests(TestCase):
    def test_new_documents_start_queued_with_no_error(self):
        workspace = make_workspace()
        document = make_document(workspace, uploaded_by=make_admin(workspace=workspace))

        self.assertEqual(document.status, Document.Status.QUEUED)
        self.assertEqual(document.error_message, "")
        self.assertEqual(list(workspace.documents.all()), [document])

    def test_has_the_four_statuses_from_the_plan(self):
        self.assertEqual(set(Document.Status.values), {"queued", "processing", "ready", "failed"})

    def test_newest_comes_first(self):
        workspace = make_workspace()
        older = make_document(workspace, title="Older")
        newer = make_document(workspace, title="Newer")
        self.assertEqual(list(Document.objects.all()), [newer, older])

    def test_deleting_the_uploader_keeps_the_document(self):
        workspace = make_workspace()
        admin = make_admin(workspace=workspace)
        document = make_document(workspace, uploaded_by=admin)

        admin.delete()
        document.refresh_from_db()
        self.assertIsNone(document.uploaded_by)


class ChunkModelTests(TestCase):
    def setUp(self):
        self.workspace = make_workspace()
        self.document = make_document(self.workspace)

    def test_chunks_come_back_in_order(self):
        second = make_chunk(self.document, order=1)
        first = make_chunk(self.document, order=0)
        self.assertEqual(list(self.document.chunks.all()), [first, second])

    def test_deleting_a_document_deletes_its_chunks(self):
        make_chunk(self.document, order=0, embedding=[0.1] * 1536)
        make_chunk(self.document, order=1)
        other = make_chunk(make_document(self.workspace, title="Other"))

        self.document.delete()
        self.assertEqual(list(Chunk.objects.all()), [other])

    def test_order_is_unique_per_document(self):
        make_chunk(self.document, order=0)
        with self.assertRaises(IntegrityError):
            make_chunk(self.document, order=0)

    def test_embedding_has_1536_numbers(self):
        chunk = make_chunk(self.document, embedding=[0.5] * 1536)
        chunk.refresh_from_db()
        self.assertEqual(len(chunk.embedding), 1536)
