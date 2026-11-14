import logging

from django.conf import settings
from django.test.runner import DiscoverRunner
from huey.contrib.djhuey import HUEY


class TestRunner(DiscoverRunner):
    """Tests never call a real LLM or need Redis, even if .env says otherwise."""

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        settings.LLM_PROVIDER = "fake"
        settings.OPENAI_API_KEY = ""
        HUEY.immediate = True

        # Keep the test output clean. assertLogs still sees everything.
        for name in ["documents", "core"]:
            for handler in logging.getLogger(name).handlers:
                handler.setLevel(logging.CRITICAL)
        logging.getLogger("pypdf").setLevel(logging.CRITICAL)
