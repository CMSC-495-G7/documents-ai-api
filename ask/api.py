import logging
import time

from ninja import Router
from ninja.errors import HttpError
from ask.models import Answer
from ask.schemas import AskHistoryOut, AskIn, AskOut, AskSettingsIn, AskSettingsOut
from ask.services import ask_question
from core import llm
from users.permissions import IsAdmin, IsEmployeeOrAdmin
from users.schemas import ErrorOut

logger = logging.getLogger(__name__)

router = Router(tags=["Ask"])

UNAVAILABLE = "The answer service is unavailable. Please try again."


@router.post(
    "",
    auth=IsEmployeeOrAdmin(),
    response={200: AskOut, 422: ErrorOut, 502: ErrorOut},
)
def ask(request, payload: AskIn):
    question = payload.question.strip()
    if not question:
        raise HttpError(422, "Ask a question.")

    started = time.monotonic()
    try:
        answer = ask_question(request.auth, question)
    except llm.LLMError:
        raise HttpError(502, UNAVAILABLE)
    seconds = time.monotonic() - started
    logger.info(
        "Answer %s: %.1f s (%s)",
        answer.id,
        seconds,
        answer.model_name or "no LLM",
    )

    return {
        "id": answer.id,
        "answer": answer.answer,
        "model": answer.model_name,
        "citations": list(answer.citations.all()),
    }


@router.get("/history", auth=IsEmployeeOrAdmin(), response=list[AskHistoryOut])
def get_history(request):
    answers = Answer.objects.filter(
        user=request.auth,
        workspace=request.auth.workspace,
    ).order_by("-created_at", "-id")[:50]

    return [
        {
            "id": answer.id,
            "question": answer.question,
            "answer": answer.answer,
            "model": answer.model_name,
            "created_at": answer.created_at,
        }
        for answer in answers
    ]


@router.post("/stream", auth=IsEmployeeOrAdmin(), response={501: ErrorOut})
def ask_stream(request, payload: AskIn):
    # TODO: Placeholder. Will stream the answer word by word, OpenAI only
    raise HttpError(501, "Streaming answers aren't available yet.")


def settings_for(workspace):
    providers = [
        {"id": name, "label": label, "available": llm.has_key(name)}
        for name, label in llm.ANSWER_PROVIDERS.items()
    ]
    return {"answer_provider": workspace.answer_provider, "providers": providers}


@router.get("/settings", auth=IsEmployeeOrAdmin(), response=AskSettingsOut)
def get_settings(request):
    return settings_for(request.auth.workspace)


@router.patch("/settings", auth=IsAdmin(), response={200: AskSettingsOut, 422: ErrorOut})
def update_settings(request, payload: AskSettingsIn):
    provider = payload.answer_provider
    if provider not in llm.ANSWER_PROVIDERS:
        raise HttpError(422, "Pick OpenAI or Gemini.")
    if not llm.has_key(provider):
        raise HttpError(422, f"{llm.ANSWER_PROVIDERS[provider]} has no API key on the server.")

    workspace = request.auth.workspace
    workspace.answer_provider = provider
    workspace.save(update_fields=["answer_provider"])
    return settings_for(workspace)

@router.get(
    "/{int:answer_id}",
    auth=IsEmployeeOrAdmin(),
    response={200: AskOut, 404: ErrorOut},
)
def get_answer(request, answer_id: int):
    answer = Answer.objects.filter(
        pk=answer_id,
        user=request.auth,
        workspace=request.auth.workspace,
    ).prefetch_related("citations").first()

    if answer is None:
        raise HttpError(404, "Answer not found.")

    return {
        "id": answer.id,
        "answer": answer.answer,
        "model": answer.model_name,
        "citations": list(answer.citations.all()),
    }
