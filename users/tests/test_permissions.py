from django.test import TestCase
from ninja import Router
from ninja.testing import TestClient

from users.models import User
from users.permissions import IsAdmin, IsEmployeeOrAdmin, workspace_queryset
from users.tests.factories import auth_header, make_admin, make_user, make_workspace
from users.tokens import create_access_token

# Fake routes just for these tests, not part of the real API.
router = Router()


@router.get("/admin-only", auth=IsAdmin())
def admin_only(request):
    return {"ok": True}


@router.get("/any-member", auth=IsEmployeeOrAdmin())
def any_member(request):
    return {"ok": True}


client = TestClient(router)


def get(path, user=None):
    headers = auth_header(create_access_token(user)) if user else {}
    return client.get(path, headers=headers)


class RoleCheckTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.employee = make_user()

    def test_employee_gets_403_on_admin_only(self):
        response = get("/admin-only", self.employee)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "You don't have access to this."})

    def test_admin_gets_200_on_admin_only(self):
        self.assertEqual(get("/admin-only", self.admin).status_code, 200)

    def test_no_token_gets_401_not_403(self):
        self.assertEqual(get("/admin-only").status_code, 401)

    def test_both_roles_can_use_member_routes(self):
        self.assertEqual(get("/any-member", self.employee).status_code, 200)
        self.assertEqual(get("/any-member", self.admin).status_code, 200)


class WorkspaceQuerysetTests(TestCase):
    def test_only_returns_rows_from_the_users_workspace(self):
        engineering = make_workspace()
        sales = make_workspace(slug="sales", name="Sales")
        me = make_user(workspace=engineering)
        teammate = make_admin(workspace=engineering)
        make_user(email="outsider@acme.example", workspace=sales)

        self.assertEqual(set(workspace_queryset(User, me)), {me, teammate})
