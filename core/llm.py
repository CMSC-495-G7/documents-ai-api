"""
All LLM and embedding calls go through here.

Embeddings always use OpenAI. Answers use OpenAI or Gemini, picked per workspace.
LLM_PROVIDER=fake swaps every call for a fake one (tests, no key).
"""

import hashlib
import logging
import math
import re

import openai
from django.conf import settings

logger = logging.getLogger(__name__)

# Chunk.embedding has this many numbers. Changing it needs a migration.
EMBEDDING_DIMENSIONS = 1536


class LLMError(Exception):
    """The provider failed. The message is safe to show people."""


def embed(texts):
    """Returns one vector per text, in the same order. Sends them in batches."""
    provider = get_provider()
    batch_size = settings.EMBED_BATCH_SIZE
    vectors = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start: start + batch_size]
        vectors.extend(provider.embed(batch))
    return vectors


def ask(prompt, instructions="", provider="openai"):
    """Sends one prompt and returns the answer text. provider is "openai" or "gemini"."""
    return get_answer_provider(provider).ask(prompt, instructions)


def get_provider():
    """The one used for embeddings."""
    name = settings.LLM_PROVIDER
    if name == "fake":
        return FakeProvider()
    if name == "openai":
        return OpenAIProvider()
    raise LLMError(f"Unknown LLM_PROVIDER: {name}")


# Who can write answers. The keys match Workspace.AnswerProvider.
ANSWER_PROVIDERS = {"openai": "OpenAI", "gemini": "Gemini"}


def get_answer_provider(name):
    if name not in ANSWER_PROVIDERS:
        raise LLMError(f"Unknown answer provider: {name}")
    if settings.LLM_PROVIDER == "fake":
        return FakeProvider()
    if name == "gemini":
        return GeminiProvider()
    return OpenAIProvider()


def has_key(name):
    """True if the server can use this answer provider."""
    if settings.LLM_PROVIDER == "fake":
        return True
    if name == "gemini":
        return bool(settings.GEMINI_API_KEY)
    return bool(settings.OPENAI_API_KEY)


def answer_model(name):
    """The model name we save with each answer."""
    if settings.LLM_PROVIDER == "fake":
        return "fake"
    if name == "gemini":
        return settings.GEMINI_CHAT_MODEL
    return settings.CHAT_MODEL


class FakeProvider:
    """For tests and for running without a key. No network."""

    def embed(self, texts):
        return [fake_vector(text) for text in texts]

    def ask(self, prompt, instructions=""):
        return f"Fake answer to: {prompt[:200]}"


def fake_vector(text):
    """Same text, same vector. Texts that share words get close vectors."""
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for word in re.findall(r"\w+", text.lower()):
        # md5, not hash(), so the API and the worker get the same number
        spot = int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBEDDING_DIMENSIONS
        vector[spot] += 1
    length = math.sqrt(sum(n * n for n in vector))
    if length == 0:
        vector[0] = 1.0
        return vector
    return [n / length for n in vector]


class OpenAIProvider:
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise LLMError("OPENAI_API_KEY is not set.")
        self.client = openai.OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )

    def embed(self, texts):
        try:
            response = self.client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=texts,
                dimensions=EMBEDDING_DIMENSIONS,
            )
        except openai.OpenAIError as error:
            logger.warning("OpenAI embeddings failed: %r", error)
            raise LLMError("The embedding service didn't answer. Try again later.") from error
        return [item.embedding for item in response.data]

    def ask(self, prompt, instructions=""):
        # Only send instructions when there are some
        extra = {"instructions": instructions} if instructions else {}
        try:
            response = self.client.responses.create(
                model=settings.CHAT_MODEL, input=prompt, **extra
            )
        except openai.OpenAIError as error:
            logger.warning("OpenAI answer failed: %r", error)
            raise LLMError("The AI service didn't answer. Try again later.") from error
        return response.output_text


class GeminiProvider:
    """Answers only. Gemini has an OpenAI-compatible endpoint, so it's the same client."""

    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise LLMError("GEMINI_API_KEY is not set.")
        self.client = openai.OpenAI(
            api_key=settings.GEMINI_API_KEY,
            base_url=settings.GEMINI_BASE_URL,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )

    def ask(self, prompt, instructions=""):
        messages = [{"role": "user", "content": prompt}]
        if instructions:
            messages.insert(0, {"role": "system", "content": instructions})
        try:
            response = self.client.chat.completions.create(
                model=settings.GEMINI_CHAT_MODEL, messages=messages
            )
        except openai.OpenAIError as error:
            logger.warning("Gemini answer failed: %r", error)
            raise LLMError("The AI service didn't answer. Try again later.") from error
        choices = getattr(response, "choices", None)
        message = getattr(choices[0], "message", None) if choices else None
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise LLMError("The AI service didn't answer. Try again later.")
        return content
