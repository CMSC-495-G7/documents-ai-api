from django.contrib import admin

from documents.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "file_type", "size", "status", "workspace", "uploaded_by", "created_at"]
    list_filter = ["status", "file_type", "workspace"]
    search_fields = ["title"]
    readonly_fields = ["file_path", "size", "created_at", "updated_at"]
