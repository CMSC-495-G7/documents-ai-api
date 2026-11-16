from typing import Annotated

from ninja import Schema
from pydantic import Field


class AskIn(Schema):
    question: Annotated[str, Field(min_length=1, max_length=2000)]


class CitationOut(Schema):
    # Both are null once the chunk or document is gone
    chunk_id: int | None
    document_id: int | None
    document_title: str
    page: int | None
    # DOCX heading, empty for PDFs
    section: str
    text: str
    score: float


class AskOut(Schema):
    id: int
    answer: str
    model: str
    citations: list[CitationOut]


class ProviderOut(Schema):
    id: str
    label: str
    # False when the server has no key for it
    available: bool


class AskSettingsOut(Schema):
    answer_provider: str
    providers: list[ProviderOut]


class AskSettingsIn(Schema):
    answer_provider: str
