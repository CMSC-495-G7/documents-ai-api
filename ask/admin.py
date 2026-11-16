from django.contrib import admin

from ask.models import Answer, Citation


class CitationInline(admin.TabularInline):
    model = Citation
    extra = 0
    fields = ("rank", "score", "document_title", "page", "section", "chunk")
    readonly_fields = fields


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "question", "model_name", "used_llm", "user", "workspace", "created_at")
    list_filter = ("used_llm", "workspace")
    search_fields = ("question", "answer")
    inlines = [CitationInline]


@admin.register(Citation)
class CitationAdmin(admin.ModelAdmin):
    list_display = ("id", "answer", "rank", "document_title", "page", "score")
