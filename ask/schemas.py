from typing import Annotated

from ninja import Schema
from pydantic import Field


class AskIn(Schema):
    question: Annotated[str, Field(min_length=1, max_length=2000)]


class CitationOut(Schema):
    chunk_id: int
    document_id: int
    document_title: str
    page: int | None
    slide: int | None
    row_start: int | None
    row_end: int | None
    text: str
    score: float

    @staticmethod
    def resolve_document_id(citation):
        return citation.chunk.document_id

    @staticmethod
    def resolve_document_title(citation):
        return citation.chunk.document.title

    @staticmethod
    def resolve_page(citation):
        return citation.chunk.page

    @staticmethod
    def resolve_slide(citation):
        return citation.chunk.slide

    @staticmethod
    def resolve_row_start(citation):
        return citation.chunk.row_start

    @staticmethod
    def resolve_row_end(citation):
        return citation.chunk.row_end

    @staticmethod
    def resolve_text(citation):
        return citation.chunk.text


class AskOut(Schema):
    id: int
    answer: str
    model: str
    citations: list[CitationOut]
