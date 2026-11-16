"""
All LLM and embedding calls go through here. To add a provider, add a class
with embed() and ask() and pick it in get_provider().
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
        batch = texts[start : start + batch_size]
        vectors.extend(provider.embed(batch))
    return vectors


def ask(prompt):
    """Sends one prompt and returns the answer text."""
    return get_provider().ask(prompt)


def get_provider():
    name = settings.LLM_PROVIDER
    if name == "fake":
        return FakeProvider()
    if name == "openai":
        return OpenAIProvider()
    raise LLMError(f"Unknown LLM_PROVIDER: {name}")


class FakeProvider:
    """For tests and for running without a key. No network."""

    def embed(self, texts):
        return [fake_vector(text) for text in texts]

    def ask(self, prompt):
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

    def ask(self, prompt):
        try:
            response = self.client.responses.create(model=settings.CHAT_MODEL, input=prompt)
        except openai.OpenAIError as error:
            logger.warning("OpenAI answer failed: %r", error)
            raise LLMError("The AI service didn't answer. Try again later.") from error
        return response.output_text
