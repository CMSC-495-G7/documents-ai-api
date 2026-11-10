from django.test import TestCase

from documents.models import Document
from documents.tests.factories import make_document
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
