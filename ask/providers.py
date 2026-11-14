"""OpenAI-compatible embeddings and chat completions, using only the standard library.

Set the ASK_* settings in .env to point at a provider. If no key is configured,
the API returns a clear 502 instead of calling out.
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings


class ProviderError(Exception):
    """The embedding or language model is unavailable or returned an unusable reply."""


@dataclass(frozen=True)
class Source:
    label: str
    text: str


SYSTEM_PROMPT = (
    "You are a workplace assistant. Answer the question using only the numbered "
    "document excerpts provided. Cite every excerpt you use with its bracketed "
    "number, like [1]. If the excerpts do not contain the answer, say you couldn't "
    "find it in the documents. Do not use outside knowledge."
)


def _post_json(url, api_key, payload, timeout):
    if not api_key:
        raise ProviderError("No API key is configured for the answer service.")

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError("The answer service is unavailable. Please try again.") from exc

    try:
        return json.loads(body)
    except (TypeError, ValueError) as exc:
        raise ProviderError("The answer service returned an unreadable response.") from exc


def embed_question(question):
    data = _post_json(
        f"{settings.ASK_EMBEDDING_BASE_URL.rstrip('/')}/embeddings",
        settings.ASK_EMBEDDING_API_KEY,
        {
            "model": settings.ASK_EMBEDDING_MODEL,
            "input": question,
            "dimensions": settings.ASK_EMBEDDING_DIMENSIONS,
        },
        settings.ASK_EMBEDDING_TIMEOUT_SECONDS,
    )

    try:
        embedding = data["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("The answer service returned an unreadable response.") from exc

    if not isinstance(embedding, list) or len(embedding) != settings.ASK_EMBEDDING_DIMENSIONS:
        raise ProviderError("The answer service returned an unexpected embedding.")

    return embedding


def _user_prompt(question, sources):
    lines = [f"Question: {question}", "", "Document excerpts:"]
    for number, source in enumerate(sources, start=1):
        lines.append(f"[{number}] {source.label}\n{source.text}")
    return "\n\n".join(lines)


def generate_answer(question, sources):
    data = _post_json(
        f"{settings.ASK_LLM_BASE_URL.rstrip('/')}/chat/completions",
        settings.ASK_LLM_API_KEY,
        {
            "model": settings.ASK_LLM_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(question, sources)},
            ],
            "temperature": 0,
            "max_tokens": settings.ASK_MAX_ANSWER_TOKENS,
        },
        settings.ASK_LLM_TIMEOUT_SECONDS,
    )

    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("The answer service returned an unreadable response.") from exc

    if not isinstance(answer, str) or not answer.strip():
        raise ProviderError("The answer service returned an empty answer.")

    return answer.strip()
