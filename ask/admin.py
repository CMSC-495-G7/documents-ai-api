from django.contrib import admin

from ask.models import Answer, Chunk, Citation


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "chunk_index", "page", "slide", "row_start", "row_end")
    list_filter = ("document__file_type", "document__status")
    search_fields = ("text", "document__title")


class CitationInline(admin.TabularInline):
    model = Citation
    extra = 0
    readonly_fields = ("chunk", "rank", "score")


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "question", "model_name", "used_llm", "user", "workspace", "created_at")
    list_filter = ("used_llm", "workspace")
    search_fields = ("question", "answer")
    inlines = [CitationInline]


@admin.register(Citation)
class CitationAdmin(admin.ModelAdmin):
    list_display = ("id", "answer", "chunk", "rank", "score")
