from pathlib import PurePath

from django.conf import settings
from django.db import transaction
from ninja import File, Router
from ninja.errors import HttpError
from ninja.files import UploadedFile

from documents.file_types import detect_file_type
from documents.models import Document
from documents.schemas import DocumentOut
from documents.storage import delete_file, save_file
from documents.tasks import process_document
from users.permissions import IsAdmin, workspace_queryset
from users.schemas import ErrorOut

router = Router(tags=["Documents"])

WRONG_TYPE = "Only PDF and DOCX files can be uploaded."


@router.post(
    "",
    auth=IsAdmin(),
    response={201: DocumentOut, 403: ErrorOut, 413: ErrorOut, 415: ErrorOut},
)
def upload_document(request, file: File[UploadedFile]):
    max_mb = settings.DOCUMENT_MAX_UPLOAD_MB
    if file.size > max_mb * 1024 * 1024:
        raise HttpError(413, f"The file is too big. The limit is {max_mb} MB.")

    # Check the bytes, then make sure the name agrees
    file_type = detect_file_type(file)
    extension = PurePath(file.name).suffix.lower().lstrip(".")
    if file_type is None or extension != file_type:
        raise HttpError(415, WRONG_TYPE)

    path = save_file(file, file_type)
    try:
        document = Document.objects.create(
            workspace=request.auth.workspace,
            title=PurePath(file.name).stem[:255],
            file_path=path,
            file_type=file_type,
            size=file.size,
            uploaded_by=request.auth,
        )
    except Exception:
        # Don't leave a file with no row
        delete_file(path)
        raise

    # The worker's recovery task picks up queued rows if this enqueue fails.
    transaction.on_commit(lambda: process_document(document.id), robust=True)
    return 201, document


@router.get("", response=list[DocumentOut])
def list_documents(request):
    return workspace_queryset(Document, request.auth).select_related("uploaded_by")


@router.delete("/{document_id}", auth=IsAdmin(), response={204: None, 404: ErrorOut})
def delete_document(request, document_id: int):
    document = workspace_queryset(Document, request.auth).filter(
        pk=document_id
    ).first()

    if document is None:
        raise HttpError(404, "Document not found.")

    path = document.file_path

    with transaction.atomic():
        # Chunks go too (CASCADE)
        document.delete()
        # Only once the row is gone. A file that can't be deleted is logged, still 204
        transaction.on_commit(lambda: delete_file(path), robust=True)

    return 204, None
