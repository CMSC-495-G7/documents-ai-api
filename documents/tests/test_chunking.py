from django.test import SimpleTestCase

from documents.chunking import MAX_WORDS, split_into_chunks
from documents.extraction import Page
from documents.tests.factories import words


def word_counts(chunks):
    return [len(chunk.text.split()) for chunk in chunks]


class ChunkSizeTests(SimpleTestCase):
    def test_limit_is_500_words(self):
        self.assertEqual(MAX_WORDS, 500)

    def test_no_chunk_is_over_the_limit(self):
        chunks = split_into_chunks([Page(number=1, text=words(1234))])
        self.assertEqual(word_counts(chunks), [500, 500, 234])

    def test_short_page_is_one_chunk(self):
        chunks = split_into_chunks([Page(number=1, text="Dental is covered.")])
        self.assertEqual([chunk.text for chunk in chunks], ["Dental is covered."])

    def test_exactly_the_limit_is_one_chunk(self):
        self.assertEqual(word_counts(split_into_chunks([Page(number=1, text=words(500))])), [500])

    def test_one_word_over_makes_a_second_chunk(self):
        self.assertEqual(word_counts(split_into_chunks([Page(number=1, text=words(501))])), [500, 1])

    def test_max_words_can_be_changed(self):
        chunks = split_into_chunks([Page(number=1, text=words(7))], max_words=3)
        self.assertEqual(word_counts(chunks), [3, 3, 1])

    def test_no_words_are_lost_or_reordered(self):
        text = words(1100)
        chunks = split_into_chunks([Page(number=1, text=text)])
        self.assertEqual(" ".join(chunk.text for chunk in chunks), text)

    def test_blank_page_makes_no_chunks(self):
        self.assertEqual(split_into_chunks([Page(number=1, text="  \n ")]), [])


class ChunkPageTests(SimpleTestCase):
    def test_each_chunk_keeps_its_page_and_section(self):
        pages = [
            Page(number=1, text=words(600, "a"), section="Intro"),
            Page(number=4, text="short page", section="Leave"),
        ]
        chunks = split_into_chunks(pages)

        self.assertEqual([chunk.page for chunk in chunks], [1, 1, 4])
        self.assertEqual([chunk.section for chunk in chunks], ["Intro", "Intro", "Leave"])

    def test_a_chunk_never_mixes_two_pages(self):
        chunks = split_into_chunks([Page(number=1, text="end of one"), Page(number=2, text="start of two")])
        self.assertEqual([chunk.text for chunk in chunks], ["end of one", "start of two"])

    def test_order_counts_up_across_pages(self):
        pages = [Page(number=1, text=words(700)), Page(number=2, text=words(10))]
        self.assertEqual([chunk.order for chunk in split_into_chunks(pages)], [0, 1, 2])

    def test_chunks_are_not_saved_yet(self):
        chunk = split_into_chunks([Page(number=1, text="hello")])[0]
        self.assertIsNone(chunk.pk)
