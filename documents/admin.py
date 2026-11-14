from django.contrib import admin

from documents.models import Chunk, Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "file_type", "size", "status", "workspace", "uploaded_by", "created_at"]
    list_filter = ["status", "file_type", "workspace"]
    search_fields = ["title"]
    readonly_fields = ["file_path", "size", "created_at", "updated_at"]


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ["document", "page", "section", "order", "workspace"]
    list_filter = ["workspace"]
    search_fields = ["text", "document__title"]
    # The vector is 1536 numbers, not useful to show
    exclude = ["embedding"]
