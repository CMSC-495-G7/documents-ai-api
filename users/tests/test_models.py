from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase

from users.models import User
from users.tests.factories import make_admin, make_user, make_workspace


class UserModelTests(TestCase):
    def test_auth_user_model_is_ours(self):
        self.assertIs(get_user_model(), User)

    def test_workspace_with_a_user_of_each_role(self):
        workspace = make_workspace()
        admin = make_admin(workspace=workspace)
        employee = make_user(workspace=workspace)

        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertEqual(employee.role, User.Role.EMPLOYEE)
        self.assertEqual(set(workspace.users.all()), {admin, employee})

    def test_role_defaults_to_employee(self):
        user = User.objects.create_user(email="new@acme.example", password="x", workspace=make_workspace())
        self.assertEqual(user.role, User.Role.EMPLOYEE)
        self.assertFalse(user.is_admin)

    def test_email_is_the_login_and_is_lowercased(self):
        user = make_user(email="Someone@ACME.example")
        self.assertEqual(User.USERNAME_FIELD, "email")
        self.assertEqual(user.email, "someone@acme.example")

    def test_createsuperuser_command_takes_a_workspace_id(self):
        workspace = make_workspace()
        call_command(
            "createsuperuser",
            interactive=False,
            email="root@acme.example",
            workspace=workspace.id,
            stdout=StringIO(),
        )
        root = User.objects.get(email="root@acme.example")
        self.assertEqual(root.workspace, workspace)
        self.assertTrue(root.is_superuser)
        self.assertEqual(root.role, User.Role.ADMIN)

    def test_email_is_unique(self):
        make_user(email="dupe@acme.example")
        with self.assertRaises(IntegrityError):
            make_user(email="dupe@acme.example")
