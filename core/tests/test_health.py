from unittest.mock import patch

from django.db import OperationalError, connection
from django.test import SimpleTestCase, TestCase


class HealthTests(SimpleTestCase):
    def test_health_does_not_need_a_database(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "documents-ai-api"})

    def test_docs_and_openapi_are_available(self):
        self.assertEqual(self.client.get("/api/docs").status_code, 200)
        response = self.client.get("/api/openapi.json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/api/ready", response.json()["paths"])

    @patch("core.api.connection")
    def test_database_outage_returns_503_without_leaking_details(self, database):
        database.cursor.side_effect = OperationalError("private connection details")
        response = self.client.get("/api/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"status": "error", "database": "unavailable", "pgvector": "unknown"},
        )

    @patch("core.api.connection")
    def test_missing_extension_returns_503(self, database):
        database.cursor.return_value.__enter__.return_value.fetchone.return_value = None
        response = self.client.get("/api/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "error", "database": "ok", "pgvector": "missing"})


class PostgresTests(TestCase):
    """Use real Postgres so migrations and vector operations are verified together."""

    def test_readiness_with_postgres_and_pgvector(self):
        response = self.client.get("/api/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok", "pgvector": "ok"})

    def test_vector_distance_operation(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT '[1,2,3]'::vector <-> '[1,2,6]'::vector")
            self.assertAlmostEqual(cursor.fetchone()[0], 3.0)
