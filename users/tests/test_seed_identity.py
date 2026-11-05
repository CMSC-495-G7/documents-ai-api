from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from users.models import User, Workspace

SEED_SETTINGS = {
    "SEED_ADMIN_EMAIL": "admin@acme.example",
    "SEED_ADMIN_PASSWORD": "admin-pass",
    "SEED_EMPLOYEE_EMAIL": "employee@acme.example",
    "SEED_EMPLOYEE_PASSWORD": "employee-pass",
}


def seed():
    call_command("seed_identity", stdout=StringIO())


@override_settings(**SEED_SETTINGS)
class SeedIdentityTests(TestCase):
    def test_creates_workspace_admin_and_employee(self):
        seed()

        workspace = Workspace.objects.get(slug="engineering")
        admin = User.objects.get(email="admin@acme.example")
        employee = User.objects.get(email="employee@acme.example")

        self.assertEqual((admin.role, admin.workspace), (User.Role.ADMIN, workspace))
        self.assertEqual((employee.role, employee.workspace), (User.Role.EMPLOYEE, workspace))
        self.assertTrue(admin.check_password("admin-pass"))
        self.assertTrue(employee.check_password("employee-pass"))

    def test_running_twice_makes_no_duplicates(self):
        seed()
        seed()
        self.assertEqual(Workspace.objects.count(), 1)
        self.assertEqual(User.objects.count(), 2)

    def test_password_changes_in_env_are_picked_up(self):
        seed()
        with self.settings(SEED_ADMIN_PASSWORD="new-pass"):
            seed()
        self.assertTrue(User.objects.get(email="admin@acme.example").check_password("new-pass"))

    def test_missing_password_fails_clearly(self):
        with self.settings(SEED_EMPLOYEE_PASSWORD=""):
            with self.assertRaisesMessage(CommandError, "employee@acme.example"):
                seed()
