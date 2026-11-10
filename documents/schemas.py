from datetime import datetime

from ninja import Schema


class DocumentOut(Schema):
    id: int
    title: str
    file_type: str
    size: int
    status: str
    error_message: str
    uploaded_by: str | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def resolve_uploaded_by(document):
        return document.uploaded_by.email if document.uploaded_by else None
