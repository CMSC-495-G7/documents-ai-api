import math
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import openai
from django.test import SimpleTestCase, override_settings

from core import llm
from core.llm import EMBEDDING_DIMENSIONS, FakeProvider, LLMError, OpenAIProvider, ask, embed, fake_vector


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))


class FakeVectorTests(SimpleTestCase):
    def test_has_the_right_length(self):
        self.assertEqual(len(fake_vector("hello world")), EMBEDDING_DIMENSIONS)

    def test_same_text_same_vector(self):
        self.assertEqual(fake_vector("Dental plan"), fake_vector("Dental plan"))

    def test_has_length_1(self):
        length = math.sqrt(sum(n * n for n in fake_vector("a few words here")))
        self.assertAlmostEqual(length, 1.0)

    def test_texts_that_share_words_are_closer(self):
        question = fake_vector("dental plan")
        self.assertGreater(
            cosine(question, fake_vector("our dental plan covers cleanings")),
            cosine(question, fake_vector("parking is in the north garage")),
        )

    def test_empty_text_still_works(self):
        self.assertEqual(len(fake_vector("")), EMBEDDING_DIMENSIONS)


class EmbedTests(SimpleTestCase):
    def test_tests_use_the_fake_provider(self):
        self.assertIsInstance(llm.get_provider(), FakeProvider)

    def test_one_vector_per_text_in_order(self):
        vectors = embed(["one", "two", "three"])
        self.assertEqual(vectors, [fake_vector("one"), fake_vector("two"), fake_vector("three")])

    def test_no_texts_no_vectors(self):
        self.assertEqual(embed([]), [])

    @override_settings(EMBED_BATCH_SIZE=2)
    def test_sends_batches_of_embed_batch_size(self):
        with patch.object(FakeProvider, "embed", autospec=True) as fake_embed:
            fake_embed.side_effect = lambda provider, texts: [fake_vector(text) for text in texts]
            vectors = embed(["a", "b", "c", "d", "e"])

        batches = [call.args[1] for call in fake_embed.call_args_list]
        self.assertEqual(batches, [["a", "b"], ["c", "d"], ["e"]])
        self.assertEqual(vectors, [fake_vector(text) for text in "abcde"])

    @override_settings(EMBED_BATCH_SIZE=100)
    def test_small_lists_are_one_batch(self):
        with patch.object(FakeProvider, "embed", autospec=True) as fake_embed:
            fake_embed.side_effect = lambda provider, texts: [fake_vector(text) for text in texts]
            embed(["a", "b", "c"])
        self.assertEqual(fake_embed.call_count, 1)


class AskTests(SimpleTestCase):
    def test_fake_answer(self):
        self.assertEqual(ask("What is the dental plan?"), "Fake answer to: What is the dental plan?")


class ProviderSettingTests(SimpleTestCase):
    @override_settings(LLM_PROVIDER="carrier-pigeon")
    def test_unknown_provider(self):
        with self.assertRaisesMessage(LLMError, "Unknown LLM_PROVIDER: carrier-pigeon"):
            embed(["hello"])

    @override_settings(LLM_PROVIDER="openai", OPENAI_API_KEY="")
    def test_openai_needs_a_key(self):
        with self.assertRaisesMessage(LLMError, "OPENAI_API_KEY is not set."):
            embed(["hello"])


@override_settings(
    LLM_PROVIDER="openai",
    OPENAI_API_KEY="sk-test",
    EMBEDDING_MODEL="text-embedding-3-small",
    CHAT_MODEL="gpt-test",
    LLM_TIMEOUT_SECONDS=50,
)
@patch("core.llm.openai.OpenAI")
class OpenAIProviderTests(SimpleTestCase):
    """The real client is replaced, these never reach the network."""

    def test_client_has_the_50_second_timeout(self, client_class):
        OpenAIProvider()
        client_class.assert_called_once_with(api_key="sk-test", timeout=50)

    def test_embed_sends_the_model_and_size(self, client_class):
        client = client_class.return_value
        client.embeddings.create.return_value = SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2]), SimpleNamespace(embedding=[0.3, 0.4])]
        )

        self.assertEqual(embed(["one", "two"]), [[0.1, 0.2], [0.3, 0.4]])
        client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input=["one", "two"],
            dimensions=EMBEDDING_DIMENSIONS,
        )

    def test_ask_returns_the_text(self, client_class):
        client = client_class.return_value
        client.responses.create.return_value = SimpleNamespace(output_text="Two cleanings a year.")

        self.assertEqual(ask("How many cleanings?"), "Two cleanings a year.")
        client.responses.create.assert_called_once_with(model="gpt-test", input="How many cleanings?")

    def test_timeout_becomes_llm_error(self, client_class):
        request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
        client_class.return_value.embeddings.create.side_effect = openai.APITimeoutError(request=request)

        with self.assertLogs("core.llm", "WARNING"), self.assertRaisesMessage(LLMError, "Try again later."):
            embed(["hello"])

    def test_bad_key_becomes_llm_error_without_details(self, client_class):
        request = httpx.Request("POST", "https://api.openai.com/v1/responses")
        response = httpx.Response(401, request=request)
        error = openai.AuthenticationError("Incorrect API key provided: sk-test", response=response, body=None)
        client_class.return_value.responses.create.side_effect = error

        with self.assertLogs("core.llm", "WARNING"), self.assertRaises(LLMError) as raised:
            ask("hello")
        self.assertNotIn("sk-test", str(raised.exception))
