from ninja import Router
from ninja.errors import HttpError

from ask.providers import ProviderError
from ask.schemas import AskIn, AskOut
from ask.services import ask_question
from users.permissions import IsEmployeeOrAdmin
from users.schemas import ErrorOut

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

    try:
        answer = ask_question(request.auth, question)
    except ProviderError:
        raise HttpError(502, UNAVAILABLE)

    return {
        "id": answer.id,
        "answer": answer.answer,
        "model": answer.model_name,
        "citations": list(
            answer.citations.select_related("chunk__document")
        ),
    }
