from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.llm import fake_vector
from documents.tests.factories import make_chunk, make_document
from users.tests.factories import make_workspace


def search(question, **options):
    out = StringIO()
    call_command("search_chunks", question, stdout=out, **options)
    return out.getvalue().splitlines()


class SearchChunksCommandTests(TestCase):
    def setUp(self):
        self.engineering = make_workspace()
        self.handbook = make_document(self.engineering, title="Handbook")

    def add(self, text, page, document=None):
        document = document or self.handbook
        order = document.chunks.count()
        return make_chunk(document, text=text, page=page, order=order, embedding=fake_vector(text))

    def test_closest_chunk_comes_first_with_its_page(self):
        self.add("Our dental plan covers two cleanings a year", page=3)
        self.add("Parking is free in the north garage", page=7)

        lines = search("How many dental cleanings are covered?")
        self.assertIn("Handbook, page 3: Our dental plan", lines[0])
        self.assertIn("page 7", lines[1])

    def test_returns_at_most_5(self):
        for page in range(1, 9):
            self.add(f"Policy number {page}", page=page)
        self.assertEqual(len(search("policy")), 5)

    def test_only_searches_one_workspace(self):
        sales = make_workspace(slug="sales", name="Sales")
        self.add("Dental plan for sales", page=1, document=make_document(sales, title="Sales handbook"))
        self.add("Dental plan for engineers", page=2)

        lines = search("dental plan")
        self.assertEqual(len(lines), 1)
        self.assertIn("Handbook, page 2", lines[0])

    def test_skips_chunks_without_an_embedding(self):
        make_chunk(self.handbook, text="Not embedded yet", page=1)
        self.assertEqual(search("embedded"), ["No chunks yet. Upload a document and wait for it to be ready."])
