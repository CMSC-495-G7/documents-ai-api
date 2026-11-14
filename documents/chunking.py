"""Cuts pages into chunks small enough to embed."""

from documents.models import Chunk

MAX_WORDS = 500


def split_into_chunks(pages, max_words=MAX_WORDS):
    """Returns unsaved Chunks of at most max_words words.

    A chunk never crosses a page, so each one keeps its page and section.
    """
    chunks = []
    for page in pages:
        words = page.text.split()
        for start in range(0, len(words), max_words):
            text = " ".join(words[start : start + max_words])
            # order counts up from 0 across all pages, not per page
            chunks.append(
                Chunk(text=text, page=page.number, section=page.section, order=len(chunks))
            )
    return chunks
