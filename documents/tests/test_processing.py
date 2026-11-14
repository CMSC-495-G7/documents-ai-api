from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from core.llm import EMBEDDING_DIMENSIONS, LLMError
from documents.extraction import NO_TEXT, ExtractionError
from documents.models import Chunk, Document
from documents.processing import (
    PROCESSING_LEASE,
    SOMETHING_WENT_WRONG,
    failure_message,
    process_document,
    set_status,
)
from documents.tasks import QUEUE_RECOVERY_DELAY, recover_documents
from documents.tasks import process_document as process_document_task
from documents.tests.factories import (
    TempStorageMixin,
    docx_with,
    make_chunk,
    make_document,
    make_saved_document,
    pdf_with,
    words,
)
from users.tests.factories import make_workspace

Status = Document.Status


class ProcessingTestCase(TempStorageMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.workspace = make_workspace()

    def process(self, document):
        process_document(document.id)
        document.refresh_from_db()
        return document


class SetStatusTests(TestCase):
    def setUp(self):
        self.document = make_document(make_workspace())

    def test_saves_the_new_status(self):
        set_status(self.document, Status.PROCESSING)

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Status.PROCESSING)

    def test_updates_the_object_you_passed_in_too(self):
        set_status(self.document, Status.FAILED, "Broken file.")
        self.assertEqual(self.document.status, Status.FAILED)
        self.assertEqual(self.document.error_message, "Broken file.")

    def test_saves_the_error_message(self):
        set_status(self.document, Status.FAILED, "Broken file.")

        self.document.refresh_from_db()
        self.assertEqual(self.document.error_message, "Broken file.")

    def test_a_new_status_clears_an_old_error(self):
        set_status(self.document, Status.FAILED, "Broken file.")
        set_status(self.document, Status.PROCESSING)

        self.document.refresh_from_db()
        self.assertEqual(self.document.error_message, "")

    def test_bumps_updated_at(self):
        before = self.document.updated_at
        set_status(self.document, Status.PROCESSING)

        self.document.refresh_from_db()
        self.assertGreater(self.document.updated_at, before)

    def test_logs_the_change(self):
        with self.assertLogs("documents.processing", "INFO") as logs:
            set_status(self.document, Status.PROCESSING)
        self.assertEqual(logs.output, [f"INFO:documents.processing:Document {self.document.id}: queued -> processing"])

    def test_deleted_document_is_not_an_error(self):
        Document.objects.filter(pk=self.document.pk).delete()
        set_status(self.document, Status.READY)
        self.assertFalse(Document.objects.exists())


class FailureMessageTests(TestCase):
    def test_extraction_errors_keep_their_message(self):
        self.assertEqual(failure_message(ExtractionError(NO_TEXT)), NO_TEXT)

    def test_llm_errors_keep_their_message(self):
        self.assertEqual(failure_message(LLMError("Try again later.")), "Try again later.")

    def test_other_errors_get_a_plain_message(self):
        with self.assertLogs("documents.processing", "ERROR"):
            message = failure_message(KeyError("password=secret"))
        self.assertEqual(message, SOMETHING_WENT_WRONG)
        self.assertNotIn("secret", message)

    def test_other_errors_are_logged_with_the_details(self):
        with self.assertLogs("documents.processing", "ERROR") as logs:
            failure_message(KeyError("page_tree"))
        self.assertIn("page_tree", logs.output[0])


class GoodDocumentTests(ProcessingTestCase):
    def test_pdf_ends_up_ready(self):
        document = make_saved_document(self.workspace, pdf_with("Dental is covered.", "You get 20 days."))

        document = self.process(document)
        self.assertEqual(document.status, Status.READY)
        self.assertEqual(document.error_message, "")

    def test_pdf_chunks_keep_their_pages(self):
        document = make_saved_document(self.workspace, pdf_with(words(600), "Leave policy"))
        self.process(document)

        chunks = list(document.chunks.all())
        self.assertEqual([(chunk.page, chunk.order) for chunk in chunks], [(1, 0), (1, 1), (2, 2)])
        self.assertTrue(all(chunk.workspace == self.workspace for chunk in chunks))

    def test_every_chunk_gets_an_embedding(self):
        document = make_saved_document(self.workspace, pdf_with("Dental", "Leave"))
        self.process(document)

        for chunk in document.chunks.all():
            self.assertEqual(len(chunk.embedding), EMBEDDING_DIMENSIONS)

    def test_docx_chunks_keep_their_section(self):
        content = docx_with(("heading", "Benefits"), ("paragraph", "Dental"), ("heading", "Leave"), ("paragraph", "20 days"))
        document = make_saved_document(self.workspace, content, file_type=Document.FileType.DOCX)
        document = self.process(document)

        self.assertEqual(document.status, Status.READY)
        sections = [(chunk.page, chunk.section) for chunk in document.chunks.all()]
        self.assertEqual(sections, [(1, "Benefits"), (2, "Leave")])

    def test_logs_each_status_change(self):
        document = make_saved_document(self.workspace, pdf_with("Dental"))

        with self.assertLogs("documents.processing", "INFO") as logs:
            self.process(document)
        self.assertIn(f"Document {document.id}: queued -> processing", logs.output[0])
        self.assertIn(f"Document {document.id}: processing -> ready", logs.output[1])
        self.assertIn("1 chunks in", logs.output[2])

    def test_duplicate_delivery_skips_ready_document(self):
        document = make_saved_document(self.workspace, pdf_with("Dental", "Leave"))
        self.process(document)
        with patch("core.llm.embed") as embed:
            self.process(document)
        embed.assert_not_called()
        self.assertEqual(document.chunks.count(), 2)

    def test_embeds_in_batches(self):
        document = make_saved_document(self.workspace, pdf_with(*[f"Page {n}" for n in range(5)]))
        with self.settings(EMBED_BATCH_SIZE=2), patch("core.llm.FakeProvider.embed", autospec=True) as embed:
            embed.side_effect = lambda provider, texts: [[0.1] * EMBEDDING_DIMENSIONS for _ in texts]
            self.process(document)

        self.assertEqual([len(call.args[1]) for call in embed.call_args_list], [2, 2, 1])
        self.assertEqual(document.chunks.count(), 5)


class FailedDocumentTests(ProcessingTestCase):
    def assert_failed_with(self, document, message):
        document = self.process(document)
        self.assertEqual(document.status, Status.FAILED)
        self.assertEqual(document.error_message, message)
        self.assertFalse(document.chunks.exists())

    def test_pdf_with_no_text(self):
        self.assert_failed_with(make_saved_document(self.workspace, pdf_with("")), NO_TEXT)

    def test_damaged_docx(self):
        document = make_saved_document(self.workspace, b"PK not really a zip", file_type=Document.FileType.DOCX)
        self.assert_failed_with(document, "This DOCX couldn't be read. It may be damaged.")

    def test_embedding_service_down(self):
        document = make_saved_document(self.workspace, pdf_with("Dental"))
        with patch("core.llm.embed", side_effect=LLMError("The embedding service didn't answer. Try again later.")):
            self.assert_failed_with(document, "The embedding service didn't answer. Try again later.")

    def test_missing_file(self):
        document = make_document(self.workspace, file_path="documents/gone.pdf")
        with self.assertLogs("documents.processing", "ERROR"):
            self.assert_failed_with(document, SOMETHING_WENT_WRONG)

    def test_failing_keeps_old_chunks_untouched(self):
        document = make_saved_document(self.workspace, pdf_with("Dental"))
        make_chunk(document, text="old chunk")
        with patch("core.llm.embed", side_effect=LLMError("down")):
            self.process(document)
        self.assertEqual([chunk.text for chunk in document.chunks.all()], ["old chunk"])


class DeletedDocumentTests(ProcessingTestCase):
    def test_document_deleted_before_the_job_runs(self):
        document = make_saved_document(self.workspace, pdf_with("Dental"))
        document_id = document.id
        document.delete()

        process_document(document_id)
        self.assertFalse(Chunk.objects.exists())

    def test_document_deleted_while_the_job_runs(self):
        document = make_saved_document(self.workspace, pdf_with("Dental"))

        def delete_then_embed(texts):
            Document.objects.filter(pk=document.pk).delete()
            return [[0.1] * EMBEDDING_DIMENSIONS for _ in texts]

        with patch("core.llm.embed", side_effect=delete_then_embed):
            process_document(document.id)
        self.assertFalse(Document.objects.exists())
        self.assertFalse(Chunk.objects.exists())


class TaskTests(ProcessingTestCase):
    def test_task_runs_the_job(self):
        # Tests run Huey jobs right away, no Redis needed
        document = make_saved_document(self.workspace, pdf_with("Dental"))

        process_document_task(document.id)
        document.refresh_from_db()
        self.assertEqual(document.status, Status.READY)

    def test_recovery_processes_old_queued_rows_and_expired_claims(self):
        queued = make_saved_document(self.workspace, pdf_with("Queued"))
        interrupted = make_saved_document(self.workspace, pdf_with("Interrupted"))
        active = make_saved_document(self.workspace, pdf_with("Active"))
        set_status(active, Status.PROCESSING)
        fresh = make_saved_document(self.workspace, pdf_with("Fresh"))
        now = timezone.now()
        Document.objects.filter(pk=queued.pk).update(updated_at=now - QUEUE_RECOVERY_DELAY)
        Document.objects.filter(pk=interrupted.pk).update(
            status=Status.PROCESSING, updated_at=now - PROCESSING_LEASE,
        )

        recover_documents.call_local()

        for document, expected in [
            (queued, Status.READY),
            (interrupted, Status.READY),
            (active, Status.PROCESSING),
            (fresh, Status.QUEUED),
        ]:
            document.refresh_from_db()
            self.assertEqual(document.status, expected)

    def test_expired_worker_cannot_overwrite_the_recovered_chunks(self):
        document = make_saved_document(self.workspace, pdf_with("Dental"))

        def reclaim_then_embed(texts):
            Document.objects.filter(pk=document.pk).update(
                updated_at=timezone.now() - PROCESSING_LEASE,
            )
            with patch("core.llm.embed", return_value=[[0.2] * EMBEDDING_DIMENSIONS]):
                process_document(document.pk)
            return [[0.1] * EMBEDDING_DIMENSIONS]

        with patch("core.llm.embed", side_effect=reclaim_then_embed):
            process_document(document.pk)

        document.refresh_from_db()
        self.assertEqual(document.status, Status.READY)
        self.assertAlmostEqual(document.chunks.get().embedding[0], 0.2)
