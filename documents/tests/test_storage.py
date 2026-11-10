from django.core.files.base import ContentFile
from django.test import SimpleTestCase

from documents.storage import delete_file, save_file
from documents.tests.factories import TempStorageMixin


class SaveFileTests(TempStorageMixin, SimpleTestCase):
    def test_saves_the_bytes_and_returns_the_path(self):
        path = save_file(ContentFile(b"hello"), "pdf")

        self.assertTrue(path.startswith("documents/"))
        self.assertTrue(path.endswith(".pdf"))
        self.assertEqual((self.storage_root / path).read_bytes(), b"hello")

    def test_same_name_twice_gets_two_files(self):
        first = save_file(ContentFile(b"one", name="report.pdf"), "pdf")
        second = save_file(ContentFile(b"two", name="report.pdf"), "pdf")

        self.assertNotEqual(first, second)
        self.assertEqual(len(self.stored_files()), 2)


class DeleteFileTests(TempStorageMixin, SimpleTestCase):
    def test_deletes_a_saved_file(self):
        path = save_file(ContentFile(b"bye"), "docx")

        delete_file(path)
        self.assertEqual(self.stored_files(), [])

    def test_only_deletes_that_file(self):
        keep = save_file(ContentFile(b"keep"), "pdf")
        remove = save_file(ContentFile(b"remove"), "pdf")

        delete_file(remove)
        self.assertEqual(self.stored_files(), [keep])

    def test_missing_file_is_not_an_error(self):
        delete_file("documents/not-there.pdf")
